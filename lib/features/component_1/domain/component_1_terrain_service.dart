import 'pandolf_exertion_model.dart';
import 'pdr_tracker.dart';
import 'terrain_profile.dart';

class Component1TerrainService {
  const Component1TerrainService();

  TerrainAssessmentSnapshot assessCurrentState({
    required int terrainIndex,
    required double bodyWeightKg,
    required double speedMps,
    required double slopePercent,
    required double lastX,
    required double lastY,
    required double headingRad,
    required double stepLengthMeters,
  }) {
    final terrain = TerrainProfile.fromAiIndex(terrainIndex);
    final eta = terrain.terrainCoefficient;

    final metabolicCost = PandolfExertionModel(
      bodyWeightKg: bodyWeightKg,
      speedMps: speedMps,
      slopePercent: slopePercent,
      terrainCoefficient: eta,
    ).calculateMetabolicCostW();

    final pdrPosition = PdrTracker(
      lastX: lastX,
      lastY: lastY,
      lastHeadingRad: headingRad,
      stepLengthM: stepLengthMeters,
    ).updatePosition();

    return TerrainAssessmentSnapshot(
      terrainProfile: terrain,
      terrainCoefficient: eta,
      metabolicCostW: metabolicCost,
      currentX: pdrPosition.x,
      currentY: pdrPosition.y,
      headingRad: pdrPosition.headingRad,
    );
  }
}

class TerrainAssessmentSnapshot {
  const TerrainAssessmentSnapshot({
    required this.terrainProfile,
    required this.terrainCoefficient,
    required this.metabolicCostW,
    required this.currentX,
    required this.currentY,
    required this.headingRad,
  });

  final TerrainProfile terrainProfile;
  final double terrainCoefficient;
  final double metabolicCostW;
  final double currentX;
  final double currentY;
  final double headingRad;
}
