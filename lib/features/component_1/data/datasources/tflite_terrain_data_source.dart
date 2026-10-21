import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:tflite_flutter/tflite_flutter.dart';

class TFLiteTerrainDataSource {
  TFLiteTerrainDataSource({
    this.modelAssetPath = 'assets/models/terrain_model_quant.tflite',
  });

  final String modelAssetPath;
  Future<Interpreter>? _interpreterFuture;
  bool _useRuleBasedInference = false;

  bool get isUsingRuleBasedInference => _useRuleBasedInference;
  String get inferenceMode =>
      _useRuleBasedInference ? 'Rule-based IMU fallback' : 'TFLite model';

  Future<int> classifyTerrain(List<List<double>> imuWindow) async {
    if (imuWindow.length != 128 || imuWindow.any((s) => s.length != 6)) {
      throw ArgumentError('Expected an IMU window with shape [128, 6].');
    }

    if (_useRuleBasedInference) return classifyFromMotionVariance(imuWindow);

    try {
      final interpreter = await _getInterpreter();
      final inputTensor = interpreter.getInputTensor(0);
      final outputTensor = interpreter.getOutputTensor(0);

      final input = _buildInput(imuWindow, inputTensor);
      final output = _createTensor(outputTensor.shape, 0);
      interpreter.run(input, output);

      final values = <Object?>[];
      _flatten(output, values);
      if (values.isEmpty) {
        throw StateError('Terrain model returned an empty prediction.');
      }

      if (values.length == 1) return (values.single! as num).toInt();
      var bestIndex = 0;
      var bestScore = (values.first! as num).toDouble();
      for (var index = 1; index < values.length; index++) {
        final score = (values[index]! as num).toDouble();
        if (score > bestScore) {
          bestIndex = index;
          bestScore = score;
        }
      }
      return bestIndex;
    } on Object catch (error, stackTrace) {
      _useRuleBasedInference = true;
      _interpreterFuture = null;
      debugPrint(
        'Terrain TFLite model unavailable; using live IMU rule-based '
        'inference. Error: $error\n$stackTrace',
      );
      return classifyFromMotionVariance(imuWindow);
    }
  }

  static int classifyFromMotionVariance(List<List<double>> imuWindow) {
    if (imuWindow.length != 128 || imuWindow.any((s) => s.length != 6)) {
      throw ArgumentError('Expected an IMU window with shape [128, 6].');
    }

    final magnitudes = imuWindow
        .map((sample) {
          final x = sample[0];
          final y = sample[1];
          final z = sample[2];
          return (x * x + y * y + z * z);
        })
        .toList(growable: false);
    final meanMagnitude =
        magnitudes.map(math.sqrt).reduce((sum, value) => sum + value) /
        magnitudes.length;
    final variance =
        magnitudes
            .map(
              (value) =>
                  (math.sqrt(value) - meanMagnitude) *
                  (math.sqrt(value) - meanMagnitude),
            )
            .reduce((sum, value) => sum + value) /
        magnitudes.length;
    final standardDeviation = math.sqrt(variance);

    if (standardDeviation < 0.25) return 0;
    if (standardDeviation < 1.2) return 3;
    return 4;
  }

  Future<Interpreter> _getInterpreter() {
    return _interpreterFuture ??= Interpreter.fromAsset(modelAssetPath);
  }

  dynamic _buildInput(List<List<double>> window, Tensor tensor) {
    final shape = tensor.shape;
    final values = <num>[];
    for (final sample in window) {
      for (final value in sample) {
        values.add(value); // Simplified for float32/float16 inference
      }
    }

    var index = 0;
    dynamic buildDimension(int dimension) {
      if (dimension == shape.length) return values[index++];
      return List<dynamic>.generate(
        shape[dimension],
        (_) => buildDimension(dimension + 1),
      );
    }

    return buildDimension(0);
  }

  dynamic _createTensor(List<int> shape, num value) {
    dynamic buildDimension(int dimension) {
      if (dimension == shape.length) return value;
      return List<dynamic>.generate(
        shape[dimension],
        (_) => buildDimension(dimension + 1),
      );
    }

    return buildDimension(0);
  }

  void _flatten(Object? value, List<Object?> output) {
    if (value is List) {
      for (final e in value) {
        _flatten(e, output);
      }
    } else {
      output.add(value);
    }
  }

  Future<void> dispose() async {
    final interpreterFuture = _interpreterFuture;
    if (interpreterFuture == null) return;
    (await interpreterFuture).close();
    _interpreterFuture = null;
  }
}
