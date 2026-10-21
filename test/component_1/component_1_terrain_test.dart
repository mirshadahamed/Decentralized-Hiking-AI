import 'dart:math' as math;

import 'package:decentralized_hiking_ai/features/component_1/data/datasources/tflite_terrain_data_source.dart';
import 'package:decentralized_hiking_ai/features/component_1/domain/component_1_terrain_service.dart';
import 'package:decentralized_hiking_ai/features/component_1/domain/motion_pdr_tracker.dart';
import 'package:decentralized_hiking_ai/features/component_1/domain/pandolf_exertion_model.dart';
import 'package:decentralized_hiking_ai/features/component_1/domain/pdr_tracker.dart';
import 'package:decentralized_hiking_ai/features/component_1/domain/terrain_profile.dart';
import 'package:decentralized_hiking_ai/features/component_1/presentation/component_1_dashboard_controller.dart';
import 'package:decentralized_hiking_ai/features/component_1/presentation/component_1_dashboard_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('rule-based terrain inference', () {
    test('falls back when the TFLite model asset cannot load', () async {
      final dataSource = TFLiteTerrainDataSource();

      final terrainIndex = await dataSource.classifyTerrain(
        _window((index) => [0, 0, 9.8, 0, 0, 0]),
      );

      expect(terrainIndex, 0);
      expect(dataSource.isUsingRuleBasedInference, isTrue);
      expect(dataSource.inferenceMode, 'Rule-based IMU fallback');
    });

    test('classifies steady motion as a paved or flat path', () {
      expect(
        TFLiteTerrainDataSource.classifyFromMotionVariance(
          _window((index) => [0, 0, 9.8, 0, 0, 0]),
        ),
        0,
      );
    });

    test('classifies moderate motion variance as a gravel trail', () {
      expect(
        TFLiteTerrainDataSource.classifyFromMotionVariance(
          _window(
            (index) => [0, 0, 9.8 + (index.isEven ? 0.5 : -0.5), 0, 0, 0],
          ),
        ),
        3,
      );
    });

    test('classifies high motion variance as uneven or rocky terrain', () {
      expect(
        TFLiteTerrainDataSource.classifyFromMotionVariance(
          _window(
            (index) => [0, 0, 9.8 + (index.isEven ? 2.0 : -2.0), 0, 0, 0],
          ),
        ),
        4,
      );
    });
  });

  test(
    'Pandolf model includes body weight, load, speed, slope, and terrain',
    () {
      const model = PandolfExertionModel(
        bodyWeightKg: 100,
        loadKg: 10,
        speedMps: 2,
        slopePercent: 5,
        terrainCoefficient: 1.2,
      );

      expect(model.calculateMetabolicCostW(), closeTo(1406.2, 0.0001));
    },
  );

  test('PDR updates position using step length and heading', () {
    final position = PdrTracker(
      lastX: 2,
      lastY: -1,
      lastHeadingRad: 1.5707963267948966,
      stepLengthM: 0.75,
    ).updatePosition();

    expect(position.x, closeTo(2, 0.0001));
    expect(position.y, closeTo(-0.25, 0.0001));
  });

  test('isolates linear acceleration from gravity', () {
    final tracker = MotionPdrTracker();
    final start = DateTime.utc(2026);

    for (var index = 0; index < 100; index++) {
      tracker.update(
        timestamp: start.add(Duration(milliseconds: index * 20)),
        accelerometerX: 0,
        accelerometerY: 0,
        accelerometerZ: 9.80665,
        gyroscopeZ: 0,
      );
    }

    final motion = tracker.update(
      timestamp: start.add(const Duration(seconds: 2)),
      accelerometerX: 0,
      accelerometerY: 0,
      accelerometerZ: 10.80665,
      gyroscopeZ: 0,
    );

    expect(motion.gravityZ, closeTo(9.88, 0.02));
    expect(motion.linearAccelerationZ, closeTo(0.93, 0.02));
  });

  test('requires a realistic cadence before advancing the PDR position', () {
    final tracker = MotionPdrTracker();
    final start = DateTime.utc(2026);
    final steps = <MotionPdrSnapshot>[];
    MotionPdrSnapshot? motion;

    for (var index = 0; index <= 165; index++) {
      final inFootStrike = index == 50 || index == 90 || index == 130;
      motion = tracker.update(
        timestamp: start.add(Duration(milliseconds: index * 20)),
        accelerometerX: 0,
        accelerometerY: 0,
        accelerometerZ: 9.80665 + (inFootStrike ? 5 : 0),
        gyroscopeZ: 0.5,
      );
      if (motion.stepDetected) steps.add(motion);
    }

    expect(steps, hasLength(2));
    expect(motion!.stepCount, 2);
    expect(motion.headingRad, closeTo(1.65, 0.02));
    expect(steps[0].positionX, closeTo(0.7 * math.cos(0.91), 0.0001));
    expect(steps[0].positionY, closeTo(0.7 * math.sin(0.91), 0.0001));
    expect(
      steps[1].positionX,
      closeTo(steps[0].positionX + 0.7 * math.cos(1.31), 0.0001),
    );
    expect(
      steps[1].positionY,
      closeTo(steps[0].positionY + 0.7 * math.sin(1.31), 0.0001),
    );
  });

  test('rejects repeated peaks above 3 per second as shaking', () {
    final tracker = MotionPdrTracker(gravityTimeConstantSeconds: 0.05);
    final start = DateTime.utc(2026);
    MotionPdrSnapshot? motion;

    for (var index = 0; index <= 100; index++) {
      final inShake = index >= 30 && (index - 30) % 10 == 0;
      motion = tracker.update(
        timestamp: start.add(Duration(milliseconds: index * 20)),
        accelerometerX: 0,
        accelerometerY: 0,
        accelerometerZ: 9.80665 + (inShake ? 6 : 0),
        gyroscopeZ: 0,
      );
    }

    expect(motion!.stepCount, 0);
    expect(motion.positionX, 0);
    expect(motion.positionY, 0);
  });

  test('rejects peaks below the 3 m/s² strike threshold', () {
    final tracker = MotionPdrTracker();
    final start = DateTime.utc(2026);
    MotionPdrSnapshot? motion;

    for (var index = 0; index <= 150; index++) {
      final inWeakStrike = index == 40 || index == 80 || index == 120;
      motion = tracker.update(
        timestamp: start.add(Duration(milliseconds: index * 20)),
        accelerometerX: 0,
        accelerometerY: 0,
        accelerometerZ: 9.80665 + (inWeakStrike ? 2.5 : 0),
        gyroscopeZ: 0,
      );
    }

    expect(motion!.stepCount, 0);
    expect(motion.positionX, 0);
    expect(motion.positionY, 0);
  });

  test('requires a trough before the next peak can be considered', () {
    final tracker = MotionPdrTracker(gravityTimeConstantSeconds: 0.05);
    final start = DateTime.utc(2026);
    MotionPdrSnapshot? motion;

    for (var index = 0; index <= 100; index++) {
      final repeatedPeak = index >= 30 && index <= 70 && (index - 30) % 10 == 0;
      motion = tracker.update(
        timestamp: start.add(Duration(milliseconds: index * 20)),
        accelerometerX: 0,
        accelerometerY: 0,
        accelerometerZ: 9.80665 + (repeatedPeak ? 6 : 2),
        gyroscopeZ: 0,
      );
    }

    expect(motion!.stepCount, 0);
    expect(motion.positionX, 0);
    expect(motion.positionY, 0);
  });

  test('a gap longer than the walking cadence resets the candidate', () {
    final tracker = MotionPdrTracker();
    final start = DateTime.utc(2026);
    MotionPdrSnapshot? motion;

    for (var index = 0; index <= 190; index++) {
      final inFootStrike = index == 50 || index == 120 || index == 160;
      motion = tracker.update(
        timestamp: start.add(Duration(milliseconds: index * 20)),
        accelerometerX: 0,
        accelerometerY: 0,
        accelerometerZ: 9.80665 + (inFootStrike ? 5 : 0),
        gyroscopeZ: 0,
      );
    }

    expect(motion!.stepCount, 1);
    expect(motion.positionX, closeTo(0.7, 0.0001));
    expect(motion.positionY, closeTo(0, 0.0001));
  });

  testWidgets('dashboard renders live motion and terrain values', (
    tester,
  ) async {
    final controller = Component1DashboardController(
      loadAssessment: () async => const TerrainAssessmentSnapshot(
        terrainProfile: TerrainProfile.hikingTrail,
        terrainCoefficient: 1.18,
        loadKg: 5,
        metabolicCostW: 240,
        currentX: 1.5,
        currentY: 0.75,
        headingRad: 0.5,
        stepCount: 42,
        speedMps: 1.2,
        slopePercent: 3.4,
        accelerometerX: 0.1,
        accelerometerY: 0.2,
        accelerometerZ: 9.8,
        gyroscopeX: 0.01,
        gyroscopeY: 0.02,
        gyroscopeZ: 0.03,
        inferenceMode: 'Rule-based IMU fallback',
      ),
    );

    await tester.pumpWidget(
      MaterialApp(home: Component1DashboardScreen(controller: controller)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Gravel Trail'), findsOneWidget);
    expect(find.text('Steps  42'), findsOneWidget);
    expect(find.text('Rule-based IMU fallback'), findsOneWidget);
    expect(find.textContaining('Accelerometer'), findsOneWidget);
    expect(find.textContaining('Gyroscope'), findsOneWidget);
    expect(find.text('240.0 W'), findsOneWidget);
    expect(find.text('Pack load 5.0 kg'), findsOneWidget);
  });
}

List<List<double>> _window(List<double> Function(int index) sampleAt) {
  return List<List<double>>.generate(128, sampleAt);
}
