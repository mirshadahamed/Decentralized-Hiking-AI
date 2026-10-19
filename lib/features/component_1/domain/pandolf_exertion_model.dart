class PandolfExertionModel {
  const PandolfExertionModel({
    required this.bodyWeightKg,
    required this.speedMps,
    required this.slopePercent,
    required this.terrainCoefficient,
  });

  final double bodyWeightKg;
  final double speedMps;
  final double slopePercent;
  final double terrainCoefficient;

  double calculateMetabolicCostW() {
    final v = speedMps;
    final g = slopePercent;
    final w = bodyWeightKg;
    final eta = terrainCoefficient;

    final internalTerm = 3.5 + (0.025 * v * v) + (0.175 * v * g);
    return w * internalTerm * eta;
  }
}
