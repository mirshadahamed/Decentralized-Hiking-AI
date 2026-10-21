import 'pandolf_exertion_model.dart';
import 'terrain_profile.dart';

class Component1TerrainService {
  const Component1TerrainService();

  TerrainAssessmentSnapshot assessCurrentState({
    required int terrainIndex,
    required double bodyWeightKg,
    double loadKg = 0,
    required double speedMps,
    required double slopePercent,
    required double lastX,
    required double lastY,
    required double headingRad,
    required int stepCount,
    required double accelerometerX,
    required double accelerometerY,
    required double accelerometerZ,
    required double gyroscopeX,
    required double gyroscopeY,
    required double gyroscopeZ,
    required String inferenceMode,
  }) {
    final terrain = TerrainProfile.fromAiIndex(terrainIndex);
    final eta = terrain.terrainCoefficient;

    final metabolicCost = PandolfExertionModel(
      bodyWeightKg: bodyWeightKg,
      speedMps: speedMps,
      slopePercent: slopePercent,
      terrainCoefficient: eta,
      loadKg: loadKg,
    ).calculateMetabolicCostW();

    return TerrainAssessmentSnapshot(
      terrainProfile: terrain,
      terrainCoefficient: eta,
      loadKg: loadKg,
      metabolicCostW: metabolicCost,
      currentX: lastX,
      currentY: lastY,
      headingRad: headingRad,
      stepCount: stepCount,
      speedMps: speedMps,
      slopePercent: slopePercent,
      accelerometerX: accelerometerX,
      accelerometerY: accelerometerY,
      accelerometerZ: accelerometerZ,
      gyroscopeX: gyroscopeX,
      gyroscopeY: gyroscopeY,
      gyroscopeZ: gyroscopeZ,
      inferenceMode: inferenceMode,
    );
  }
}

class TerrainAssessmentSnapshot {
  const TerrainAssessmentSnapshot({
    required this.terrainProfile,
    required this.terrainCoefficient,
    required this.loadKg,
    required this.metabolicCostW,
    required this.currentX,
    required this.currentY,
    required this.headingRad,
    required this.stepCount,
    required this.speedMps,
    required this.slopePercent,
    required this.accelerometerX,
    required this.accelerometerY,
    required this.accelerometerZ,
    required this.gyroscopeX,
    required this.gyroscopeY,
    required this.gyroscopeZ,
    required this.inferenceMode,
  });

  final TerrainProfile terrainProfile;
  final double terrainCoefficient;
  final double loadKg;
  final double metabolicCostW;
  final double currentX;
  final double currentY;
  final double headingRad;
  final int stepCount;
  final double speedMps;
  final double slopePercent;
  final double accelerometerX;
  final double accelerometerY;
  final double accelerometerZ;
  final double gyroscopeX;
  final double gyroscopeY;
  final double gyroscopeZ;
  final String inferenceMode;
}
