import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:flutter_litert/native.dart';
import 'package:image/image.dart' as img;

import '../domain/component_2_detection.dart';
import 'letterbox_preprocessor.dart';
import 'yolo_output_decoder.dart';

class PhotoAnalysis {
  const PhotoAnalysis({required this.result, required this.displayImage});
  final Component2PhotoResult result;
  final Uint8List displayImage;
}

abstract interface class Component2PhotoAnalyzer {
  Future<PhotoAnalysis> analyze(Uint8List bytes);
  void dispose();
}

class Component2InferenceService implements Component2PhotoAnalyzer {
  static const _manifestAsset = 'assets/models/component2_manifest.json';
  static const _litterAsset = 'assets/models/component2_litter.tflite';
  static const _obstacleAsset = 'assets/models/component2_obstacle.tflite';

  Interpreter? _litter;
  Interpreter? _obstacle;
  TensorFloat32Views? _litterViews;
  TensorFloat32Views? _obstacleViews;
  Map<String, dynamic>? _manifest;
  String? _manifestHash;
  bool _disposed = false;
  final _decoder = const YoloOutputDecoder();

  Future<void> _load() async {
    if (_disposed) {
      throw StateError('Component 2 inference service has been disposed.');
    }
    if (_litter != null && _obstacle != null && _manifest != null) return;
    Interpreter? loadedLitter;
    Interpreter? loadedObstacle;
    try {
      final bytes = await rootBundle.load(_manifestAsset);
      final manifestBytes = bytes.buffer.asUint8List(
        bytes.offsetInBytes,
        bytes.lengthInBytes,
      );
      final manifest =
          jsonDecode(utf8.decode(manifestBytes)) as Map<String, dynamic>;
      final models = manifest['models'] as Map<String, dynamic>;
      final litterSpec = models['litter'] as Map<String, dynamic>;
      final obstacleSpec = models['obstacle'] as Map<String, dynamic>;
      if (manifest['quality_accepted_for_app'] != false ||
          litterSpec['asset'] != _litterAsset ||
          obstacleSpec['asset'] != _obstacleAsset ||
          litterSpec['imgsz'] != 640 ||
          obstacleSpec['imgsz'] != 416) {
        throw StateError(
          'Component 2 model manifest does not match the bundled development models.',
        );
      }
      await _verifyModelAsset(
        _litterAsset,
        litterSpec['checkpoint_sha256'] as String,
      );
      await _verifyModelAsset(
        _obstacleAsset,
        obstacleSpec['checkpoint_sha256'] as String,
      );
      loadedLitter = await Interpreter.fromAsset(
        _litterAsset,
        options: InterpreterOptions()..threads = 2,
      );
      loadedObstacle = await Interpreter.fromAsset(
        _obstacleAsset,
        options: InterpreterOptions()..threads = 2,
      );
      final litter = loadedLitter;
      final obstacle = loadedObstacle;
      if (_disposed) {
        throw StateError(
          'Component 2 inference service was disposed while loading models.',
        );
      }
      litter.allocateTensors();
      obstacle.allocateTensors();
      _requireShape(litter.getInputTensor(0).shape, const [
        1,
        640,
        640,
        3,
      ], 'litter input');
      _requireShape(obstacle.getInputTensor(0).shape, const [
        1,
        416,
        416,
        3,
      ], 'obstacle input');
      _requireFloat32(litter.getInputTensor(0).type, 'litter input');
      _requireFloat32(obstacle.getInputTensor(0).type, 'obstacle input');
      final litterOutputs = List.generate(
        litter.getOutputTensors().length,
        (i) => litter.getOutputTensor(i).shape,
      );
      if (!litterOutputs.any((s) => _sameShape(s, const [1, 160, 160, 32])) ||
          !litterOutputs.any((s) => _sameShape(s, const [1, 37, 8400]))) {
        throw StateError('Unexpected litter output tensors: $litterOutputs');
      }
      for (final tensor in litter.getOutputTensors()) {
        _requireFloat32(tensor.type, 'litter output ${tensor.name}');
      }
      final obstacleOutputs = List.generate(
        obstacle.getOutputTensors().length,
        (i) => obstacle.getOutputTensor(i).shape,
      );
      if (!obstacleOutputs.any((s) => _sameShape(s, const [1, 6, 3549]))) {
        throw StateError(
          'Unexpected obstacle output tensors: $obstacleOutputs',
        );
      }
      for (final tensor in obstacle.getOutputTensors()) {
        _requireFloat32(tensor.type, 'obstacle output ${tensor.name}');
      }
      _litter = litter;
      _obstacle = obstacle;
      _litterViews = TensorFloat32Views.capture(litter);
      _obstacleViews = TensorFloat32Views.capture(obstacle);
      _manifest = manifest;
      _manifestHash = sha256.convert(manifestBytes).toString();
    } catch (_) {
      loadedLitter?.close();
      loadedObstacle?.close();
      _litter?.close();
      _obstacle?.close();
      _litter = null;
      _obstacle = null;
      _litterViews = null;
      _obstacleViews = null;
      rethrow;
    }
  }

  Future<void> _verifyModelAsset(String path, String expectedHash) async {
    final data = await rootBundle.load(path);
    final bytes = data.buffer.asUint8List(
      data.offsetInBytes,
      data.lengthInBytes,
    );
    if (sha256.convert(bytes).toString() != expectedHash) {
      throw StateError(
        'Model file hash does not match the portable manifest: $path',
      );
    }
  }

  @override
  Future<PhotoAnalysis> analyze(Uint8List bytes) async {
    if (bytes.isEmpty) {
      throw const FormatException('The selected photo is empty.');
    }
    final decoded = img.decodeImage(bytes);
    if (decoded == null) {
      throw const FormatException(
        'This photo format is invalid or unsupported.',
      );
    }
    if (decoded.width < 2 || decoded.height < 2) {
      throw const FormatException(
        'This photo format is invalid or unsupported.',
      );
    }
    if (decoded.width * decoded.height > 24000000) {
      throw const FormatException(
        'The selected photo exceeds the 24,000,000 pixel limit.',
      );
    }
    final oriented = img.bakeOrientation(decoded);
    final displayImage = Uint8List.fromList(
      img.encodeJpg(oriented, quality: 88),
    );
    await _load();
    final models = _manifest!['models'] as Map<String, dynamic>;
    final stopwatch = Stopwatch()..start();
    final all = <Component2Detection>[];
    all.addAll(_runLitter(oriented, models['litter'] as Map<String, dynamic>));
    all.addAll(
      _runObstacle(oriented, models['obstacle'] as Map<String, dynamic>),
    );
    stopwatch.stop();
    return PhotoAnalysis(
      displayImage: displayImage,
      result: Component2PhotoResult(
        detections: List.unmodifiable(all),
        imageWidth: oriented.width,
        imageHeight: oriented.height,
        inferenceDuration: stopwatch.elapsed,
        modelVersion: _manifestHash!,
        modelQualityAccepted: _manifest!['quality_accepted_for_app'] == true,
      ),
    );
  }

  List<Component2Detection> _runLitter(
    img.Image image,
    Map<String, dynamic> spec,
  ) {
    final interpreter = _litter!;
    final views = _litterViews!;
    final inputSize = spec['imgsz'] as int;
    final prepared = prepareLetterboxedInput(image, inputSize);
    var denseIndex = -1;
    var protoIndex = -1;
    List<int>? denseShape;
    List<int>? protoShape;
    for (var i = 0; i < interpreter.getOutputTensors().length; i++) {
      final shape = interpreter.getOutputTensor(i).shape;
      if (shape.length == 3 && shape[0] == 1 && shape[1] == 37) {
        denseIndex = i;
        denseShape = shape;
      }
      if (shape.length == 4 && shape[0] == 1 && shape[3] == 32) {
        protoIndex = i;
        protoShape = shape;
      }
    }
    if (denseIndex < 0 ||
        protoIndex < 0 ||
        denseShape == null ||
        protoShape == null) {
      throw StateError('Litter model tensors changed after loading.');
    }
    views.inputs[0].setAll(0, prepared.rgbFloat32);
    interpreter.invoke();
    final denseView = views.outputs[denseIndex];
    final prototypeView = views.outputs[protoIndex];
    return _decoder.decode(
      dense: denseView,
      denseChannels: denseShape[1],
      anchors: denseShape[2],
      prototypes: prototypeView,
      prototypeHeight: protoShape[1],
      prototypeWidth: protoShape[2],
      prototypeChannels: protoShape[3],
      task: DetectionTask.litter,
      labels: _labels(spec),
      thresholds: _thresholds(spec),
      transform: prepared.transform,
    );
  }

  List<Component2Detection> _runObstacle(
    img.Image image,
    Map<String, dynamic> spec,
  ) {
    final interpreter = _obstacle!;
    final views = _obstacleViews!;
    final inputSize = spec['imgsz'] as int;
    final prepared = prepareLetterboxedInput(image, inputSize);
    final denseIndex = interpreter.getOutputTensors().indexWhere(
      (t) => t.shape.length == 3 && t.shape[0] == 1 && t.shape[1] == 6,
    );
    if (denseIndex < 0) {
      throw StateError('Obstacle model output tensor changed after loading.');
    }
    final denseShape = interpreter.getOutputTensor(denseIndex).shape;
    views.inputs[0].setAll(0, prepared.rgbFloat32);
    interpreter.invoke();
    return _decoder.decode(
      dense: views.outputs[denseIndex],
      denseChannels: denseShape[1],
      anchors: denseShape[2],
      prototypes: null,
      prototypeWidth: 0,
      prototypeHeight: 0,
      prototypeChannels: 0,
      task: DetectionTask.obstacle,
      labels: _labels(spec),
      thresholds: _thresholds(spec),
      transform: prepared.transform,
    );
  }

  Map<String, double> _thresholds(Map<String, dynamic> spec) {
    final raw = spec['class_thresholds'] as Map<String, dynamic>;
    return raw.map((key, value) => MapEntry(key, (value as num).toDouble()));
  }

  List<String> _labels(Map<String, dynamic> spec) {
    final names = (spec['names'] as Map<String, dynamic>).entries.toList()
      ..sort((a, b) => int.parse(a.key).compareTo(int.parse(b.key)));
    for (var i = 0; i < names.length; i++) {
      if (int.parse(names[i].key) != i) {
        throw StateError(
          'Class IDs in the model manifest must be contiguous from zero.',
        );
      }
    }
    return names.map((entry) => entry.value as String).toList(growable: false);
  }

  void _requireShape(List<int> actual, List<int> expected, String name) {
    if (!_sameShape(actual, expected)) {
      throw StateError(
        'Unexpected $name tensor shape $actual; expected $expected.',
      );
    }
  }

  void _requireFloat32(TensorType actual, String name) {
    if (actual != TensorType.float32) {
      throw StateError(
        'Unexpected $name tensor type $actual; expected float32.',
      );
    }
  }

  bool _sameShape(List<int> a, List<int> b) =>
      a.length == b.length &&
      List.generate(a.length, (i) => a[i] == b[i]).every((v) => v);

  @override
  void dispose() {
    _disposed = true;
    _litter?.close();
    _obstacle?.close();
    _litter = null;
    _obstacle = null;
    _litterViews = null;
    _obstacleViews = null;
  }
}
