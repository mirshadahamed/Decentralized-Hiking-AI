// On-device ST-GNN forecast (objective O6): runs the trained model in plain Dart, offline, on any platform.
//
// The weights, the trail graph and the scaled inputs come from the server's "edge pack"
// (research/component_4/src/edge/pack.py, GET /edge/pack). The forward pass mirrors
// research/component_4/src/models/stgnn.py exactly:
//   h  = relu(inp(x_past))                                  per hour, per segment
//   h += relu(GCN1(h, A with columns of uncounted segments removed))
//   h += relu(GCN2(h, A))
//   h  = last state of a GRU / LSTM over the past hours, per segment
//   h += relu(GCN_out(h, A))
//   y[t] = head(cat(h, relu(fut(x_fut[t]))))                per future hour, per segment
// GCN (PyTorch Geometric DenseGCNConv): A + I, normalised D^-1/2 (A + I) D^-1/2, times (x W^T), plus bias.
// The parity test (test/component_4/edge_forecaster_test.dart) checks the result against PyTorch.
import 'dart:math' as math;

typedef Vec = List<double>;
typedef Mat = List<List<double>>;

class _W {
  _W(this.shape, this.data);

  final List<int> shape;
  final List<double> data;

  factory _W.fromJson(Map<String, dynamic> j) => _W(
        (j['shape'] as List).map((x) => (x as num).toInt()).toList(),
        (j['data'] as List).map((x) => (x as num).toDouble()).toList(),
      );

  /// Row r of a 2-D weight [rows, cols].
  double at(int r, int c) => data[r * shape[1] + c];
}

/// y = W x + b for a PyTorch Linear (W: [out, in]).
Vec _linear(Vec x, _W w, _W? b) {
  final out = w.shape[0], inp = w.shape[1];
  final y = List<double>.filled(out, 0);
  for (var o = 0; o < out; o++) {
    var s = b == null ? 0.0 : b.data[o];
    final base = o * inp;
    for (var i = 0; i < inp; i++) {
      s += w.data[base + i] * x[i];
    }
    y[o] = s;
  }
  return y;
}

double _relu(double x) => x > 0 ? x : 0;
double _sigmoid(double x) => 1 / (1 + math.exp(-x));
Vec _reluV(Vec v) => [for (final x in v) _relu(x)];

class EdgeForecast {
  EdgeForecast({required this.people, required this.millis, required this.day, this.places = const []});

  final Mat people; // [hour 0..23][segment]
  final int millis; // time to compute on this device
  final String day;
  final List<(String, String)> places; // (trail id, POI) per segment

  /// Busiest hour and its number of people on segment [s].
  (int, double) peakOf(int s) {
    var best = 0;
    for (var h = 1; h < people.length; h++) {
      if (people[h][s] > people[best][s]) best = h;
    }
    return (best, people[best][s]);
  }
}

class EdgeForecaster {
  EdgeForecaster._(this.pack, this._w, this.adj, this.rnn, this.hidden, this.scale);

  final Map<String, dynamic> pack;
  final Map<String, _W> _w;
  final Mat adj; // [N, N]
  final String rnn; // gru | lstm
  final int hidden;
  final double scale;

  static const schema = 'c4-edge-1';

  factory EdgeForecaster.fromPack(Map<String, dynamic> pack) {
    if (pack['schema'] != schema) throw FormatException('Unknown edge pack ${pack['schema']}');
    PlaceNames.remember(pack['poi_labels']);
    final m = pack['model'] as Map<String, dynamic>;
    final weights = (m['weights'] as Map<String, dynamic>).map((k, v) => MapEntry(k, _W.fromJson(v as Map<String, dynamic>)));
    final a = _W.fromJson(m['adjacency'] as Map<String, dynamic>);
    final n = a.shape[0];
    final adj = [for (var i = 0; i < n; i++) [for (var j = 0; j < n; j++) a.at(i, j)]];
    return EdgeForecaster._(pack, weights, adj, m['rnn'] as String, (m['hidden'] as num).toInt(), (pack['scale'] as num).toDouble());
  }

  int get segments => adj.length;
  String get day => pack['day'] as String? ?? '';

  Map<String, dynamic> _seg(int s) => (pack['segments'] as List? ?? [])[s] as Map<String, dynamic>;

  /// Trail id and place (POI, '' if none) of segment [s].
  (String, String) placeOf(int s) => (_seg(s)['trail'] as String? ?? '', _seg(s)['poi'] as String? ?? '');

  /// D^-1/2 (A + I) D^-1/2 with the columns of [keepCols] == false removed first (no messages from them).
  Mat _norm(List<bool>? keepCols) {
    final n = adj.length;
    final a = [for (var i = 0; i < n; i++) [for (var j = 0; j < n; j++) (keepCols == null || keepCols[j]) ? adj[i][j] : 0.0]];
    for (var i = 0; i < n; i++) {
      a[i][i] = 1.0;
    }
    final d = [for (final row in a) 1 / math.sqrt(math.max(1.0, row.fold<double>(0, (s, x) => s + x)))];
    return [for (var i = 0; i < n; i++) [for (var j = 0; j < n; j++) d[i] * a[i][j] * d[j]]];
  }

  /// GCN layer on node features h [N, H].
  Mat _gcn(String name, Mat h, Mat aNorm) {
    final xw = [for (final x in h) _linear(x, _w['$name.lin.weight']!, null)];
    final b = _w['$name.bias']!.data;
    final n = h.length, k = b.length;
    return [
      for (var i = 0; i < n; i++)
        [
          for (var c = 0; c < k; c++)
            () {
              var s = b[c];
              for (var j = 0; j < n; j++) {
                final a = aNorm[i][j];
                if (a != 0) s += a * xw[j][c];
              }
              return s;
            }(),
        ],
    ];
  }

  /// Graph layer, or a per-segment linear layer when the model was trained without the graph.
  Mat _spatial(String name, Mat h, Mat aNorm) {
    if (pack['model']['use_graph'] == true) return _gcn(name, h, aNorm);
    return [for (final x in h) _linear(x, _w['$name.weight']!, _w['$name.bias'])];
  }

  /// One recurrent step for one segment. state: [h] for GRU, [h, c] for LSTM.
  List<Vec> _step(Vec x, List<Vec> state) {
    final H = hidden;
    final gi = _linear(x, _w['rnn.weight_ih_l0']!, _w['rnn.bias_ih_l0']);
    final gh = _linear(state[0], _w['rnn.weight_hh_l0']!, _w['rnn.bias_hh_l0']);
    if (rnn == 'gru') {
      final h = state[0];
      return [
        [
          for (var k = 0; k < H; k++)
            () {
              final r = _sigmoid(gi[k] + gh[k]);
              final z = _sigmoid(gi[H + k] + gh[H + k]);
              final n = _tanh(gi[2 * H + k] + r * gh[2 * H + k]);
              return (1 - z) * n + z * h[k];
            }(),
        ],
      ];
    }
    final c = state[1];
    final newC = <double>[], newH = <double>[];
    for (var k = 0; k < H; k++) {
      final i = _sigmoid(gi[k] + gh[k]);
      final f = _sigmoid(gi[H + k] + gh[H + k]);
      final g = _tanh(gi[2 * H + k] + gh[2 * H + k]);
      final o = _sigmoid(gi[3 * H + k] + gh[3 * H + k]);
      final cc = f * c[k] + i * g;
      newC.add(cc);
      newH.add(o * _tanh(cc));
    }
    return [newH, newC];
  }

  static double _tanh(double x) {
    final e = math.exp(2 * x);
    return x > 20 ? 1 : (x < -20 ? -1 : (e - 1) / (e + 1));
  }

  /// Days this pack lets the phone forecast itself: the pack's day (tomorrow) and any extra days (today).
  List<String> get forecastDays => [day, ...((pack['extra_inputs'] as Map<String, dynamic>?) ?? {}).keys];

  /// Tomorrow's forecast from the pack's inputs (or [occupancyPast] if the device has newer counts, scaled).
  /// [forDay]: another day the pack carries inputs for (see [forecastDays]), e.g. today.
  EdgeForecast forecast({Mat? occupancyPast, String? forDay}) {
    final sw = Stopwatch()..start();
    final extra = forDay == null || forDay == day ? null : (pack['extra_inputs'] as Map<String, dynamic>?)?[forDay];
    if (forDay != null && forDay != day && extra == null) throw ArgumentError('No inputs for $forDay in this pack');
    final inp = {...pack['inputs'] as Map<String, dynamic>, ...?(extra as Map<String, dynamic>?)};
    Mat m2(String k) => [for (final r in inp[k] as List) [for (final x in r as List) (x as num).toDouble()]];
    final occ = occupancyPast ?? m2('occupancy_past');
    final covP = m2('covariates_past'), covF = m2('covariates_future'), stat = m2('static');
    final sensed = [for (final s in inp['sensed'] as List) s as bool];
    final n = segments, L = occ.length, hf = covF.length;

    // x_past[t][n] = [occupancy * sensed, sensed, covariates[t], static[n]]  (TrailData.batch)
    final aIn = _norm(sensed), aFull = _norm(null);
    var h = <Mat>[
      for (var t = 0; t < L; t++)
        [
          for (var s = 0; s < n; s++)
            _reluV(_linear([sensed[s] ? occ[t][s] : 0.0, sensed[s] ? 1.0 : 0.0, ...covP[t], ...stat[s]], _w['inp.weight']!, _w['inp.bias'])),
        ],
    ];
    h = [
      for (final ht in h)
        () {
          final g = _spatial('g1', ht, aIn);
          return [for (var s = 0; s < n; s++) [for (var k = 0; k < hidden; k++) ht[s][k] + _relu(g[s][k])]];
        }(),
    ];
    h = [
      for (final ht in h)
        () {
          final g = _spatial('g2', ht, aFull);
          return [for (var s = 0; s < n; s++) [for (var k = 0; k < hidden; k++) ht[s][k] + _relu(g[s][k])]];
        }(),
    ];
    // recurrent pass per segment
    final last = <Vec>[];
    for (var s = 0; s < n; s++) {
      var state = rnn == 'gru' ? [List<double>.filled(hidden, 0)] : [List<double>.filled(hidden, 0), List<double>.filled(hidden, 0)];
      for (var t = 0; t < L; t++) {
        state = _step(h[t][s], state);
      }
      last.add(state[0]);
    }
    final gOut = _spatial('g_out', last, aFull);
    final hn = [for (var s = 0; s < n; s++) [for (var k = 0; k < hidden; k++) last[s][k] + _relu(gOut[s][k])]];
    // decoder on the known future
    final people = [
      for (var t = 0; t < hf; t++)
        [
          for (var s = 0; s < n; s++)
            () {
              final f = _reluV(_linear([...covF[t], ...stat[s]], _w['fut.weight']!, _w['fut.bias']));
              final z = _reluV(_linear([...hn[s], ...f], _w['head.0.weight']!, _w['head.0.bias']));
              final y = _linear(z, _w['head.2.weight']!, _w['head.2.bias'])[0];
              return math.max(0.0, y * scale);
            }(),
        ],
    ];
    sw.stop();
    return EdgeForecast(people: people, millis: sw.elapsedMilliseconds, day: forDay ?? day,
        places: [for (var s = 0; s < n; s++) (pack['segments'] as List?)?.isNotEmpty == true ? placeOf(s) : ('', '')]);
  }
}

/// Names of the places on the trails ("worlds_end" -> "World's End"), from the park's own config (sent in the
/// daily pack). Screens show these instead of the internal keys.
class PlaceNames {
  static final Map<String, String> _labels = {};

  static bool isKnown(String poi) => _labels.containsKey(poi);

  static void remember(Object? labels) {
    if (labels is Map) _labels.addAll(labels.map((k, v) => MapEntry('$k', '$v')));
  }

  /// The park's name for a place, or the key made readable ("katagamuwa_tank" -> "Katagamuwa tank").
  static String of(String poi) =>
      _labels[poi] ?? poi.replaceAll('_', ' ').replaceFirstMapped(RegExp(r'^\w'), (m) => m[0]!.toUpperCase());
}
