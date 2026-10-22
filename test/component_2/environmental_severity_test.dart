import 'dart:typed_data';

import 'package:decentralized_hiking_ai/features/component_2/domain/component_2_detection.dart';
import 'package:decentralized_hiking_ai/features/component_2/domain/environmental_severity.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Component2Detection litter({
    double left = 0.1,
    double top = 0.1,
    double right = 0.2,
    double bottom = 0.2,
    List<double> maskValues = const [1],
  }) => Component2Detection(
    task: DetectionTask.litter,
    label: 'litter',
    confidence: 0.8,
    box: NormalizedBox(left, top, right, bottom),
    mask: DetectionMask(
      width: maskValues.length,
      height: 1,
      values: Float32List.fromList(maskValues),
    ),
  );

  Component2Detection obstacle({
    required String label,
    required double left,
    required double top,
    required double right,
    required double bottom,
  }) => Component2Detection(
    task: DetectionTask.obstacle,
    label: label,
    confidence: 0.7,
    box: NormalizedBox(left, top, right, bottom),
  );

  Component2PhotoResult result(List<Component2Detection> detections) =>
      Component2PhotoResult(
        detections: detections,
        imageWidth: 1000,
        imageHeight: 1000,
        inferenceDuration: Duration.zero,
        modelVersion: 'test',
        modelQualityAccepted: false,
      );

  group('litter heuristic', () {
    test('uses mask area and count thresholds', () {
      final low = EnvironmentalSeverity.fromResult(result([litter()]));
      final moderateByArea = EnvironmentalSeverity.fromResult(
        result([litter(right: 0.3, bottom: 0.3)]),
      );
      final highByArea = EnvironmentalSeverity.fromResult(
        result([litter(right: 0.4, bottom: 0.4)]),
      );
      final moderateByCount = EnvironmentalSeverity.fromResult(
        result([litter(), litter(left: 0.3, right: 0.4)]),
      );
      final highByCount = EnvironmentalSeverity.fromResult(
        result(List.generate(5, (_) => litter())),
      );

      expect(low.litterAreaRatio, closeTo(0.01, 0.0001));
      expect(low.litterLevel, ObservationLevel.low);
      expect(moderateByArea.litterAreaRatio, closeTo(0.04, 0.0001));
      expect(moderateByArea.litterLevel, ObservationLevel.moderate);
      expect(highByArea.litterLevel, ObservationLevel.high);
      expect(moderateByCount.litterLevel, ObservationLevel.moderate);
      expect(highByCount.litterLevel, ObservationLevel.high);
    });

    test('counts only mask pixels above the overlay cutoff', () {
      final severity = EnvironmentalSeverity.fromResult(
        result([
          litter(
            left: 0,
            top: 0,
            right: 0.2,
            bottom: 0.2,
            maskValues: const [1, 0.49, 0.5, 0],
          ),
        ]),
      );

      expect(severity.litterAreaRatio, closeTo(0.02, 0.0001));
      expect(severity.litterLevel, ObservationLevel.moderate);
    });
  });

  group('obstacle heuristic', () {
    test('uses summed rock and log box area thresholds', () {
      final low = EnvironmentalSeverity.fromResult(
        result([
          obstacle(
            label: 'rock_region',
            left: 0,
            top: 0,
            right: 0.1,
            bottom: 0.1,
          ),
        ]),
      );
      final moderate = EnvironmentalSeverity.fromResult(
        result([
          obstacle(
            label: 'rock_region',
            left: 0,
            top: 0,
            right: 0.25,
            bottom: 0.2,
          ),
        ]),
      );
      final high = EnvironmentalSeverity.fromResult(
        result([
          obstacle(
            label: 'log_region',
            left: 0,
            top: 0,
            right: 0.5,
            bottom: 0.3,
          ),
        ]),
      );

      expect(low.obstacleAreaRatio, closeTo(0.01, 0.0001));
      expect(low.obstacleLevel, ObservationLevel.low);
      expect(moderate.obstacleAreaRatio, closeTo(0.05, 0.0001));
      expect(moderate.obstacleLevel, ObservationLevel.moderate);
      expect(high.obstacleAreaRatio, closeTo(0.15, 0.0001));
      expect(high.obstacleLevel, ObservationLevel.high);
    });
  });

  test(
    'maps highest class level and maps no detections to normal observation',
    () {
      final none = EnvironmentalSeverity.fromResult(result(const []));
      final moderate = EnvironmentalSeverity.fromResult(
        result([
          obstacle(
            label: 'rock_region',
            left: 0,
            top: 0,
            right: 0.25,
            bottom: 0.2,
          ),
        ]),
      );

      expect(none.overallLevel, ObservationLevel.low);
      expect(none.overallLabel, 'Normal observation');
      expect(moderate.overallLabel, 'Attention recommended');
    },
  );
}
