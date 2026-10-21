import 'package:flutter_litert/native.dart';

class TFLiteTerrainDataSource {
  TFLiteTerrainDataSource({this.modelAssetPath = 'assets/models/terrain_model_quant.tflite'});

  final String modelAssetPath;
  Future<Interpreter>? _interpreterFuture;

  Future<int> classifyTerrain(List<List<double>> imuWindow) async {
    if (imuWindow.length != 128 || imuWindow.any((s) => s.length != 6)) {
      throw ArgumentError('Expected an IMU window with shape [128, 6].');
    }

    final interpreter = await _getInterpreter();
    final inputTensor = interpreter.getInputTensor(0);
    final outputTensor = interpreter.getOutputTensor(0);

    final input = _buildInput(imuWindow, inputTensor);
    final output = _createTensor(outputTensor.shape, 0);

    interpreter.run(input, output);

    final values = <Object?>[];
    _flatten(output, values);

    final result = (values.single! as num).toDouble();
    return result.toInt();
  }

  Future<Interpreter> _getInterpreter() {
    return _interpreterFuture ??= Interpreter.fromAsset(modelAssetPath);
  }

  dynamic _buildInput(List<List<double>> window, Tensor tensor) {
    final shape = tensor.shape;
    final values = <num>[];
    for (final sample in window) {
      for (final value in sample) values.add(value); // Simplified for float32/float16 inference
    }

    var index = 0;
    dynamic buildDimension(int dimension) {
      if (dimension == shape.length) return values[index++];
      return List<dynamic>.generate(shape[dimension], (_) => buildDimension(dimension + 1));
    }
    return buildDimension(0);
  }

  dynamic _createTensor(List<int> shape, num value) {
    var index = 0;
    dynamic buildDimension(int dimension) {
      if (dimension == shape.length) { index++; return value; }
      return List<dynamic>.generate(shape[dimension], (_) => buildDimension(dimension + 1));
    }
    return buildDimension(0);
  }

  void _flatten(Object? value, List<Object?> output) {
    if (value is List) {
      for (final e in value) _flatten(e, output);
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
