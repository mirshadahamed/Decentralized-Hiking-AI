import 'package:flutter_test/flutter_test.dart';
import 'package:decentralized_hiking_ai/features/component_2/domain/component_2_detection.dart';

void main() {
  test('result keeps classes grouped and route condition not assessed', () {
    const litter = Component2Detection(
      task: DetectionTask.litter,
      label: 'litter',
      confidence: 0.8,
      box: NormalizedBox(0.1, 0.2, 0.4, 0.5),
    );
    const rock = Component2Detection(
      task: DetectionTask.obstacle,
      label: 'rock_region',
      confidence: 0.7,
      box: NormalizedBox(0.5, 0.2, 0.8, 0.5),
    );
    final result = Component2PhotoResult(
      detections: const [litter, rock],
      imageWidth: 1200,
      imageHeight: 800,
      inferenceDuration: const Duration(milliseconds: 430),
      modelVersion: 'test-manifest-sha',
      modelQualityAccepted: false,
    );
    expect(result.litterDetections, [litter]);
    expect(result.rockDetections, [rock]);
    expect(result.logDetections, isEmpty);
    expect(result.trailCondition, 'not_assessed');
    expect(result.modelQualityAccepted, isFalse);
  });
}
