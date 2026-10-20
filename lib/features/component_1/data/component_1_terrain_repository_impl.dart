import '../domain/component_1_terrain_repository.dart';
import 'datasources/sensor_data_source.dart';
import 'datasources/tflite_terrain_data_source.dart';

typedef PdrMetricsProvider = Future<Map<String, double>> Function();

class Component1TerrainRepositoryImpl implements Component1TerrainRepository {
  const Component1TerrainRepositoryImpl({
    required SensorDataSource sensorDataSource,
    required TFLiteTerrainDataSource terrainDataSource,
    required PdrMetricsProvider pdrMetricsProvider,
  })  : _sensorDataSource = sensorDataSource,
        _terrainDataSource = terrainDataSource,
        _pdrMetricsProvider = pdrMetricsProvider;

  final SensorDataSource _sensorDataSource;
  final TFLiteTerrainDataSource _terrainDataSource;
  final PdrMetricsProvider _pdrMetricsProvider;

  @override
  Future<List<List<double>>> getLatestSensorWindow() {
    return _sensorDataSource.getLatestSensorWindow();
  }

  @override
  Future<Map<String, double>> getCurrentPdrMetrics() {
    return _pdrMetricsProvider();
  }

  @override
  Future<int> classifyTerrain(List<List<double>> imuWindow) {
    return _terrainDataSource.classifyTerrain(imuWindow);
  }
}
