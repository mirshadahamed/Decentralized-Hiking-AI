import 'package:flutter/material.dart';

import 'features/component_1/data/component_1_terrain_repository_impl.dart';
import 'features/component_1/data/datasources/sensor_data_source.dart';
import 'features/component_1/data/datasources/tflite_terrain_data_source.dart';
import 'features/component_1/domain/component_1_terrain_service.dart';
import 'features/component_1/domain/component_1_terrain_use_case.dart';
import 'features/component_1/presentation/component_1_dashboard_controller.dart';
import 'features/component_1/presentation/component_1_dashboard_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  final sensorDataSource = SensorDataSource();
  final terrainDataSource = TFLiteTerrainDataSource();
  final repository = Component1TerrainRepositoryImpl(
    sensorDataSource: sensorDataSource,
    terrainDataSource: terrainDataSource,
  );
  const service = Component1TerrainService();
  final useCase = Component1TerrainUseCase(
    repository: repository,
    service: service,
  );
  final controller = Component1DashboardController(
    loadAssessment: () async {
      final result = await useCase.execute(
        bodyWeightKg: _demoBodyWeightKg,
        loadKg: _demoLoadKg,
      );
      final snapshot = result.snapshot;
      if (snapshot == null) {
        throw result.error ??
            StateError('Terrain assessment returned no result.');
      }
      return snapshot;
    },
  );

  runApp(
    MaterialApp(
      title: 'AI Hiking Assistant',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.green),
        useMaterial3: true,
      ),
      home: Component1DashboardScreen(controller: controller),
    ),
  );
}

const double _demoBodyWeightKg = 70;
const double _demoLoadKg = 5;
