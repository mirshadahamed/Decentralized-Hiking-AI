import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:image/image.dart' as img;
import 'package:image_picker/image_picker.dart';

import '../data/component_2_demo_photo_repository.dart';
import '../data/component_2_inference_service.dart';
import '../data/component_2_incident_report_repository.dart';
import '../data/component_2_photo_source.dart';
import '../domain/component_2_demo_photo.dart';
import '../domain/component_2_detection.dart';
import '../domain/component_2_incident_report.dart';
import '../domain/environmental_severity.dart';

class Component2Controller extends ChangeNotifier {
  Component2Controller({
    Component2PhotoAnalyzer? inference,
    Component2PhotoSource? photoSource,
    Component2DemoPhotoRepository? demoPhotos,
    Component2IncidentReportRepository? reports,
  }) : _inference = inference ?? Component2InferenceService(),
       _photoSource = photoSource ?? ImagePickerComponent2PhotoSource(),
       demoPhotos = demoPhotos ?? AssetComponent2DemoPhotoRepository(),
       reports =
           reports ?? SharedPreferencesComponent2IncidentReportRepository();

  final Component2PhotoAnalyzer _inference;
  final Component2PhotoSource _photoSource;
  final Component2DemoPhotoRepository demoPhotos;
  final Component2IncidentReportRepository reports;

  Uint8List? displayImage;
  Component2PhotoResult? result;
  Component2DemoPhoto? selectedSample;
  String selectedPhotoDescription = '';
  Object? error;
  bool isPickingPhoto = false;
  bool isLoadingSample = false;
  bool isAnalyzing = false;
  bool _disposed = false;

  bool get isBusy => isPickingPhoto || isLoadingSample || isAnalyzing;

  Future<void> selectPhoto(ImageSource source) async {
    if (isBusy || _disposed) return;
    error = null;
    isPickingPhoto = true;
    notifyListeners();
    try {
      final bytes = await _photoSource.pick(source);
      if (bytes == null || _disposed) return;
      displayImage = bytes;
      result = null;
      selectedSample = null;
      selectedPhotoDescription = source == ImageSource.camera
          ? 'Camera photo'
          : 'Gallery photo';
      notifyListeners();
      await _analyze(bytes);
    } catch (exception) {
      if (!_disposed) error = exception;
    } finally {
      isPickingPhoto = false;
      isAnalyzing = false;
      if (!_disposed) notifyListeners();
    }
  }

  Future<void> selectSample(Component2DemoPhoto sample) async {
    if (isBusy || _disposed) return;
    error = null;
    isLoadingSample = true;
    notifyListeners();
    try {
      final bytes = await demoPhotos.load(sample);
      if (_disposed) return;
      displayImage = bytes;
      result = null;
      selectedSample = sample;
      selectedPhotoDescription = 'Demo photo · ${sample.category}';
      notifyListeners();
      isLoadingSample = false;
      await _analyze(bytes);
    } catch (exception) {
      if (!_disposed) error = exception;
    } finally {
      isLoadingSample = false;
      isAnalyzing = false;
      if (!_disposed) notifyListeners();
    }
  }

  Future<void> _analyze(Uint8List bytes) async {
    isAnalyzing = true;
    notifyListeners();
    final analysis = await _inference.analyze(bytes);
    if (_disposed) return;
    displayImage = analysis.displayImage;
    result = analysis.result;
  }

  Future<Component2IncidentReport> saveIncidentReport({
    required String incidentType,
    String notes = '',
    String location = '',
    DateTime? createdAt,
  }) async {
    final imageBytes = displayImage;
    if (imageBytes == null) {
      throw StateError('Analyze a photo before creating an incident report.');
    }
    final decoded = img.decodeImage(imageBytes);
    if (decoded == null) {
      throw StateError('The selected photo thumbnail could not be prepared.');
    }
    final scale = math.min(1.0, 320 / math.max(decoded.width, decoded.height));
    final thumbnail = img.copyResize(
      decoded,
      width: math.max(1, (decoded.width * scale).round()),
      height: math.max(1, (decoded.height * scale).round()),
      interpolation: img.Interpolation.average,
    );
    final report = Component2IncidentReport(
      id: DateTime.now().microsecondsSinceEpoch.toString(),
      incidentType: incidentType,
      detectedClasses:
          result?.detections.map((item) => item.label).toSet().toList() ??
          const [],
      createdAt: createdAt ?? DateTime.now(),
      status: 'Saved offline',
      photoThumbnail: Uint8List.fromList(img.encodeJpg(thumbnail, quality: 55)),
      notes: notes.trim(),
      location: location.trim(),
      environmentalObservationLevel: result == null
          ? ''
          : EnvironmentalSeverity.fromResult(result!).overallLabel,
      detectionCount: result?.detections.length ?? 0,
      highestConfidence: result == null || result!.detections.isEmpty
          ? null
          : result!.detections.map((item) => item.confidence).reduce(math.max),
    );
    await reports.save(report);
    return report;
  }

  void clearError() {
    error = null;
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _inference.dispose();
    super.dispose();
  }
}
