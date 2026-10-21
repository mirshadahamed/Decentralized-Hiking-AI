import '../domain/component_1_terrain_repository.dart';
import '../domain/component_1_terrain_sensor_data.dart';
import 'datasources/sensor_data_source.dart';
import 'datasources/tflite_terrain_data_source.dart';

class Component1TerrainRepositoryImpl implements Component1TerrainRepository {
  Component1TerrainRepositoryImpl({
    required this.sensorDataSource,
    required this.terrainDataSource,
  });

  List<List<double>>? _latestSensorWindow;

  final SensorDataSource sensorDataSource;
  final TFLiteTerrainDataSource terrainDataSource;

  @override
  String get terrainInferenceMode => terrainDataSource.inferenceMode;

  Future<List<List<double>>> getLatestSensorWindow() {
    return sensorDataSource.getLatestSensorWindow();
  }

  Future<Map<String, double>> getCurrentPdrMetrics() {
    return sensorDataSource.getCurrentPdrMetrics();
  }

  Future<int> classifyTerrain(List<List<double>> imuWindow) {
    return terrainDataSource.classifyTerrain(imuWindow);
  }

  @override
  Future<Component1TerrainSensorData> fetchCurrentSensorData() async {
    final sensorWindow = await getLatestSensorWindow();
    final metrics = await getCurrentPdrMetrics();
    final sensorData = Component1TerrainSensorData(
      speedMps: _requiredMetric(metrics, 'speedMps'),
      slopePercent: _requiredMetric(metrics, 'slopePercent'),
      lastX: _requiredMetric(metrics, 'lastX'),
      lastY: _requiredMetric(metrics, 'lastY'),
      headingRad: _requiredMetric(metrics, 'headingRad'),
      stepCount: _requiredMetric(metrics, 'stepCount').round(),
      accelerometerX: _requiredMetric(metrics, 'accelerometerX'),
      accelerometerY: _requiredMetric(metrics, 'accelerometerY'),
      accelerometerZ: _requiredMetric(metrics, 'accelerometerZ'),
      gyroscopeX: _requiredMetric(metrics, 'gyroscopeX'),
      gyroscopeY: _requiredMetric(metrics, 'gyroscopeY'),
      gyroscopeZ: _requiredMetric(metrics, 'gyroscopeZ'),
    );
    _latestSensorWindow = sensorWindow;
    return sensorData;
  }

  @override
  Future<int> inferTerrainIndex(Component1TerrainSensorData sensorData) async {
    final sensorWindow = _latestSensorWindow;
    if (sensorWindow == null) {
      throw StateError('Sensor data must be fetched before terrain inference.');
    }

    _latestSensorWindow = null;
    return classifyTerrain(sensorWindow);
  }

  double _requiredMetric(Map<String, double> metrics, String key) {
    final value = metrics[key];
    if (value == null || !value.isFinite) {
      throw FormatException('PDR metrics must include a finite "$key" value.');
    }
    return value;
  }
}
