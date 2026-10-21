import 'dart:typed_data';

import 'package:flutter/foundation.dart';
import 'package:image_picker/image_picker.dart';

import '../data/component_2_inference_service.dart';
import '../domain/component_2_detection.dart';

class Component2Controller extends ChangeNotifier {
  Component2Controller({Component2InferenceService? inference, ImagePicker? picker})
      : _inference = inference ?? Component2InferenceService(),
        _picker = picker ?? ImagePicker();

  final Component2InferenceService _inference;
  final ImagePicker _picker;
  Uint8List? displayImage;
  Component2PhotoResult? result;
  Object? error;
  bool isAnalyzing = false;
  bool _disposed = false;

  Future<void> selectPhoto(ImageSource source) async {
    if (isAnalyzing || _disposed) return;
    error = null;
    result = null;
    displayImage = null;
    notifyListeners();
    try {
      final file = await _picker.pickImage(
        source: source,
        maxWidth: 2048,
        maxHeight: 2048,
        requestFullMetadata: false,
      );
      if (file == null || _disposed) return;
      isAnalyzing = true;
      notifyListeners();
      final analysis = await _inference.analyze(await file.readAsBytes());
      if (_disposed) return;
      displayImage = analysis.displayImage;
      result = analysis.result;
    } catch (exception) {
      if (_disposed) return;
      error = exception;
    } finally {
      isAnalyzing = false;
      if (!_disposed) notifyListeners();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _inference.dispose();
    super.dispose();
  }
}
