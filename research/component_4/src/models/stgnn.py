"""ST-GNN: GCN (space) + GRU (time) with a decoder on known future covariates (D4).

The same class with use_graph=False replaces every GCN layer with a per-node Linear layer,
so 'ST-GNN vs no-graph' is a clean ablation of the graph alone. rnn='lstm' gives the LSTM baseline.

The trail graph is small (48 nodes), so the dense form of the GCN (DenseGCNConv: D^-1/2 (A+I) D^-1/2 X W)
is faster than sparse message passing and gives the same result. Edges are weighted (road link < walking link).

Segments without counts ("unsensed", spatial CV) are fed as zeros. The first graph layer therefore only
*receives* from sensed segments, so those zeros are not averaged into their neighbours as fake empty readings.
Later layers use the full graph, so information can travel on through unsensed segments.
"""
import torch
from torch import nn
from torch_geometric.nn import DenseGCNConv
from torch_geometric.utils import to_dense_adj

SENSED_CHANNEL = 1   # x_past[..., 1] is the sensed flag (see TrailData.batch)


class STGNN(nn.Module):
    def __init__(self, f_past, f_fut, edge_index, edge_weight=None, hidden=32, use_graph=True, rnn="gru"):
        super().__init__()
        self.use_graph = use_graph
        self.register_buffer("adj", to_dense_adj(edge_index, edge_attr=edge_weight)[0])
        layer = (lambda: DenseGCNConv(hidden, hidden)) if use_graph else (lambda: nn.Linear(hidden, hidden))
        self.inp = nn.Linear(f_past, hidden)
        self.g1, self.g2, self.g_out = layer(), layer(), layer()
        self.rnn = (nn.GRU if rnn == "gru" else nn.LSTM)(hidden, hidden, batch_first=True)
        self.fut = nn.Linear(f_fut, hidden)
        self.head = nn.Sequential(nn.Linear(2 * hidden, hidden), nn.ReLU(), nn.Linear(hidden, 1))

    def spatial(self, layer, h, adj=None):
        if not self.use_graph:
            return layer(h)
        shape = h.shape                                          # [..., N, hidden]
        return layer(h.reshape(-1, *shape[-2:]), self.adj if adj is None else adj).reshape(shape)

    def forward(self, x_past, x_fut):
        """x_past [B, L, N, Fp], x_fut [B, H, N, Ff] -> prediction [B, H, N]."""
        B, L, N, _ = x_past.shape
        sensed = x_past[0, 0, :, SENSED_CHANNEL]                 # same for the whole batch
        adj_in = self.adj * sensed[None, :]                      # column j = messages from j
        h = torch.relu(self.inp(x_past))
        h = h + torch.relu(self.spatial(self.g1, h, adj_in))    # receive only from segments with counts
        h = h + torch.relu(self.spatial(self.g2, h))
        h = h.permute(0, 2, 1, 3).reshape(B * N, L, -1)         # one sequence per node
        _, last = self.rnn(h)
        last = last[0] if isinstance(last, tuple) else last     # LSTM returns (h, c)
        h = last[-1].reshape(B, N, -1)
        h = h + torch.relu(self.spatial(self.g_out, h))         # spread the temporal state to neighbours
        f = torch.relu(self.fut(x_fut))                          # [B, H, N, hidden]
        z = torch.cat([h[:, None].expand(-1, f.shape[1], -1, -1), f], dim=-1)
        return self.head(z).squeeze(-1)
