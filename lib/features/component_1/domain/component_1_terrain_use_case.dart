import 'component_1_terrain_repository.dart';
import 'component_1_terrain_service.dart';
import 'component_1_terrain_state.dart';

/// Coordinates component 1 data acquisition, inference, and domain assessment.
class Component1TerrainUseCase {
  const Component1TerrainUseCase({
    required Component1TerrainRepository repository,
    required Component1TerrainService service,
  })  : _repository = repository,
        _service = service;

  final Component1TerrainRepository _repository;
  final Component1TerrainService _service;

  /// Fetches current sensor values, classifies terrain, then computes the
  /// component 1 assessment. Failures are returned as a failure state.
  Future<Component1TerrainState> execute({required double bodyWeightKg}) async {
    try {
      final sensorData = await _repository.fetchCurrentSensorData();
      final terrainIndex = await _repository.inferTerrainIndex(sensorData);
      final snapshot = _service.assessCurrentState(
        terrainIndex: terrainIndex,
        bodyWeightKg: bodyWeightKg,
        speedMps: sensorData.speedMps,
        slopePercent: sensorData.slopePercent,
        lastX: sensorData.lastX,
        lastY: sensorData.lastY,
        headingRad: sensorData.headingRad,
        stepLengthMeters: sensorData.stepLengthMeters,
      );
      return Component1TerrainState.success(snapshot);
    } on Object catch (error) {
      return Component1TerrainState.failure(error);
    }
  }
}