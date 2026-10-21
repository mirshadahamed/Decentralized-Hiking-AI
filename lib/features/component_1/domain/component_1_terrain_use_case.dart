import 'component_1_terrain_repository.dart';
import 'component_1_terrain_service.dart';
import 'component_1_terrain_state.dart';

/// Coordinates component 1 data acquisition, inference, and domain assessment.
class Component1TerrainUseCase {
  const Component1TerrainUseCase({
    required this.repository,
    required this.service,
  });

  final Component1TerrainRepository repository;
  final Component1TerrainService service;

  /// Fetches current sensor values, classifies terrain, then computes the
  /// component 1 assessment. Failures are returned as a failure state.
  Future<Component1TerrainState> execute({
    required double bodyWeightKg,
    double loadKg = 0,
  }) async {
    try {
      final sensorData = await repository.fetchCurrentSensorData();
      final terrainIndex = await repository.inferTerrainIndex(sensorData);
      final snapshot = service.assessCurrentState(
        terrainIndex: terrainIndex,
        bodyWeightKg: bodyWeightKg,
        loadKg: loadKg,
        speedMps: sensorData.speedMps,
        slopePercent: sensorData.slopePercent,
        lastX: sensorData.lastX,
        lastY: sensorData.lastY,
        headingRad: sensorData.headingRad,
        stepCount: sensorData.stepCount,
        accelerometerX: sensorData.accelerometerX,
        accelerometerY: sensorData.accelerometerY,
        accelerometerZ: sensorData.accelerometerZ,
        gyroscopeX: sensorData.gyroscopeX,
        gyroscopeY: sensorData.gyroscopeY,
        gyroscopeZ: sensorData.gyroscopeZ,
        inferenceMode: repository.terrainInferenceMode,
      );
      return Component1TerrainState.success(snapshot);
    } on Object catch (error) {
      return Component1TerrainState.failure(error);
    }
  }
}
