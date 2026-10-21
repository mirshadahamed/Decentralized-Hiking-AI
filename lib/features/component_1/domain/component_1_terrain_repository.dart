import 'component_1_terrain_sensor_data.dart';

/// Data-source contract for component 1's live sensor and terrain-model flow.
///
/// Implementations are responsible for obtaining phone sensor/step data and
/// preparing/running the component 1 TFLite terrain classifier.
abstract interface class Component1TerrainRepository {
  String get terrainInferenceMode;

  /// Reads the latest sensor and PDR inputs required for a terrain assessment.
  Future<Component1TerrainSensorData> fetchCurrentSensorData();

  /// Runs the component 1 TFLite model and returns its terrain class index.
  Future<int> inferTerrainIndex(Component1TerrainSensorData sensorData);
}
