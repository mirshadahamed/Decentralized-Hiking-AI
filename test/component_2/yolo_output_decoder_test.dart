import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:decentralized_hiking_ai/features/component_2/data/letterbox_preprocessor.dart';
import 'package:decentralized_hiking_ai/features/component_2/data/yolo_output_decoder.dart';
import 'package:decentralized_hiking_ai/features/component_2/domain/component_2_detection.dart';

void main() {
  test('decodes normalized xywh and applies class-aware NMS', () {
    const anchors = 3;
    final dense = Float32List(6 * anchors);
    void setChannel(int channel, List<double> values) {
      for (var i = 0; i < anchors; i++) dense[channel * anchors + i] = values[i];
    }
    setChannel(0, [0.5, 0.51, 0.5]);
    setChannel(1, [0.5, 0.5, 0.5]);
    setChannel(2, [0.4, 0.4, 0.4]);
    setChannel(3, [0.2, 0.2, 0.2]);
    setChannel(4, [0.9, 0.8, 0.85]);
    setChannel(5, [0.1, 0.1, 0.9]);
    const transform = LetterboxTransform(
      sourceWidth: 100,
      sourceHeight: 100,
      targetSize: 100,
      resizedWidth: 100,
      resizedHeight: 100,
      padLeft: 0,
      padTop: 0,
    );

    final result = const YoloOutputDecoder().decode(
      dense: dense,
      denseChannels: 6,
      anchors: anchors,
      prototypes: null,
      prototypeWidth: 0,
      prototypeHeight: 0,
      prototypeChannels: 0,
      task: DetectionTask.obstacle,
      labels: const ['rock_region', 'log_region'],
      thresholds: const {'rock_region': 0.39, 'log_region': 0.03},
      transform: transform,
    );

    expect(result, hasLength(2));
    expect(result.map((d) => d.label), containsAll(['rock_region', 'log_region']));
    final rock = result.singleWhere((d) => d.label == 'rock_region');
    expect(rock.box.left, closeTo(0.3, 1e-6));
    expect(rock.box.right, closeTo(0.7, 1e-6));
    expect(rock.confidence, closeTo(0.9, 1e-6));
  });

  test('reconstructs a selected litter mask from prototype coefficients', () {
    final dense = Float32List(37);
    dense[0] = 0.5;
    dense[1] = 0.5;
    dense[2] = 0.8;
    dense[3] = 0.8;
    dense[4] = 0.9;
    dense[5] = 1;
    final prototypes = Float32List(2 * 2 * 32);
    for (var pixel = 0; pixel < 4; pixel++) prototypes[pixel * 32] = 10;
    const transform = LetterboxTransform(
      sourceWidth: 100,
      sourceHeight: 100,
      targetSize: 100,
      resizedWidth: 100,
      resizedHeight: 100,
      padLeft: 0,
      padTop: 0,
    );

    final result = const YoloOutputDecoder().decode(
      dense: dense,
      denseChannels: 37,
      anchors: 1,
      prototypes: prototypes,
      prototypeWidth: 2,
      prototypeHeight: 2,
      prototypeChannels: 32,
      task: DetectionTask.litter,
      labels: const ['litter'],
      thresholds: const {'litter': 0.3983983983983984},
      transform: transform,
    );

    expect(result, hasLength(1));
    expect(result.single.mask?.width, 32);
    expect(result.single.mask?.height, 32);
    expect(result.single.mask?.values.length, 1024);
    expect(result.single.mask!.values.first, greaterThan(0.99));
  });
}
import 'dart:typed_data';

