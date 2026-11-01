"""ST-GNN: GCN (space) + GRU (time) with a decoder on known future covariates (D4).

The same class with use_graph=False replaces every GCN layer with a per-node Linear layer,
so 'ST-GNN vs no-graph' is a clean ablation of the graph alone. rnn='lstm' gives the LSTM baseline.

The trail graph is small (48 nodes), so the dense form of the GCN (DenseGCNConv: D^-1/2 (A+I) D^-1/2 X W)
is faster than sparse message passing and gives the same result. Edges are weighted (road link < walking link).

Segments without counts ("unsensed", spatial CV) are fed as zeros. The first graph layer therefore only
*receives* from sensed segments, so those zeros are not averaged into their neighbours as fake empty readings.
Later layers use the full graph, so information can travel on through unsensed segments.

direction=(segment_trail, walk_position) replaces the GCN with a directed diffusion convolution (DCRNN-style,
Li et al. 2018): separate weights for what comes from behind on the trail (walkers arriving) and from ahead
(walkers coming back, queues growing backwards), K hops each way. A GCN averages both into one number, so it
cannot tell a queue spreading down from the summit from walkers arriving from below.
"""
import torch
from torch import nn
from torch_geometric.nn import DenseGCNConv
from torch_geometric.utils import to_dense_adj

SENSED_CHANNEL = 1   # x_past[..., 1] is the sensed flag (see TrailData.batch)
GRAPH_BUFFERS = ("adj", "adj_up", "adj_down")      # park-specific: never copied between parks


def directed(adj: torch.Tensor, trail, position) -> tuple:
    """(up, down) [N, N]: up[i, j] = weight of the link when j is behind i on the same trail (people walk from j
    to i), down[i, j] when j is ahead. Links between different trails, or at the same position, go in both."""
    trail = [str(t) for t in trail]
    same = torch.tensor([[a == b for b in trail] for a in trail])
    pos = torch.as_tensor(position, dtype=torch.float32)
    behind, ahead = pos[None, :] < pos[:, None], pos[None, :] > pos[:, None]
    both = ~same | (~behind & ~ahead)
    a = adj.T                                                    # a[i, j]: message from j to i
    return a * (both | behind), a * (both | ahead)


class DiffusionConv(nn.Module):
    """h_i' = W0 h_i + sum_k W_up,k (P_up^k h)_i + W_down,k (P_down^k h)_i, P = row-normalised directed adjacency."""

    def __init__(self, hidden, k=2):
        super().__init__()
        self.own = nn.Linear(hidden, hidden)
        self.up = nn.ModuleList(nn.Linear(hidden, hidden, bias=False) for _ in range(k))
        self.down = nn.ModuleList(nn.Linear(hidden, hidden, bias=False) for _ in range(k))

    def forward(self, h, adj_up, adj_down):
        out = self.own(h)
        for lins, a in ((self.up, adj_up), (self.down, adj_down)):
            p, x = a / a.sum(-1, keepdim=True).clamp(min=1e-6), h
            for lin in lins:
                x = p @ x                                        # [N, N] @ [..., N, hidden]
                out = out + lin(x)
        return out


class STGNN(nn.Module):
    def __init__(self, f_past, f_fut, edge_index, edge_weight=None, hidden=32, use_graph=True, rnn="gru",
                 direction=None, n_nodes=None):
        super().__init__()
        self.use_graph, self.directed = use_graph, use_graph and direction is not None
        self.register_buffer("adj", to_dense_adj(edge_index, edge_attr=edge_weight, max_num_nodes=n_nodes)[0])
        if self.directed:
            up, down = directed(self.adj, *direction)
            self.register_buffer("adj_up", up)
            self.register_buffer("adj_down", down)
            layer = lambda: DiffusionConv(hidden)                # noqa: E731
        else:
            layer = (lambda: DenseGCNConv(hidden, hidden)) if use_graph else (lambda: nn.Linear(hidden, hidden))
        self.inp = nn.Linear(f_past, hidden)
        self.g1, self.g2, self.g_out = layer(), layer(), layer()
        self.rnn = (nn.GRU if rnn == "gru" else nn.LSTM)(hidden, hidden, batch_first=True)
        self.fut = nn.Linear(f_fut, hidden)
        self.head = nn.Sequential(nn.Linear(2 * hidden, hidden), nn.ReLU(), nn.Linear(hidden, 1))

    def spatial(self, layer, h, adj=None, mask=None):
        """mask [N]: only these segments send messages (first layer: the segments with counts)."""
        if not self.use_graph:
            return layer(h)
        if self.directed:
            m = 1 if mask is None else mask[None, :]
            return layer(h, self.adj_up * m, self.adj_down * m)
        if mask is not None:
            adj = self.adj * mask[None, :]                       # column j = messages from j
        shape = h.shape                                          # [..., N, hidden]
        return layer(h.reshape(-1, *shape[-2:]), self.adj if adj is None else adj).reshape(shape)

    def forward(self, x_past, x_fut):
        """x_past [B, L, N, Fp], x_fut [B, H, N, Ff] -> prediction [B, H, N]."""
        B, L, N, _ = x_past.shape
        sensed = x_past[0, 0, :, SENSED_CHANNEL]                 # same for the whole batch
        h = torch.relu(self.inp(x_past))
        h = h + torch.relu(self.spatial(self.g1, h, mask=sensed))  # receive only from segments with counts
        h = h + torch.relu(self.spatial(self.g2, h))
        h = h.permute(0, 2, 1, 3).reshape(B * N, L, -1)         # one sequence per node
        _, last = self.rnn(h)
        last = last[0] if isinstance(last, tuple) else last     # LSTM returns (h, c)
        h = last[-1].reshape(B, N, -1)
        h = h + torch.relu(self.spatial(self.g_out, h))         # spread the temporal state to neighbours
        f = torch.relu(self.fut(x_fut))                          # [B, H, N, hidden]
        z = torch.cat([h[:, None].expand(-1, f.shape[1], -1, -1), f], dim=-1)
        return self.head(z).squeeze(-1)
