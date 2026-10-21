import 'dart:math' as math;

class PandolfExertionModel {
  const PandolfExertionModel({
    required this.bodyWeightKg,
    required this.speedMps,
    required this.slopePercent,
    required this.terrainCoefficient,
    this.loadKg = 0,
  });

  final double bodyWeightKg;
  final double loadKg;
  final double speedMps;
  final double slopePercent;
  final double terrainCoefficient;

  double calculateMetabolicCostW() {
    final v = speedMps;
    final g = slopePercent;
    final w = bodyWeightKg;
    final eta = terrainCoefficient;

    final load = loadKg;
    if (!w.isFinite || w <= 0) {
      throw ArgumentError.value(w, 'bodyWeightKg', 'Must be finite and > 0.');
    }
    if (!load.isFinite || load < 0) {
      throw ArgumentError.value(load, 'loadKg', 'Must be finite and >= 0.');
    }
    if (!v.isFinite || v < 0 || !g.isFinite || !eta.isFinite || eta <= 0) {
      throw ArgumentError(
        'Speed, slope, and terrain coefficient must be finite.',
      );
    }

    return (1.5 * w +
            2.0 * (w + load) * math.pow(load / w, 2) +
            eta * (w + load) * (1.5 * v * v + 0.35 * v * g))
        .toDouble();
  }
}
