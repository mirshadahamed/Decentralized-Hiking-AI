import 'dart:async';

import 'package:decentralized_hiking_ai/features/component_2/data/component_2_demo_photo_repository.dart';
import 'package:decentralized_hiking_ai/features/component_2/data/component_2_inference_service.dart';
import 'package:decentralized_hiking_ai/features/component_2/data/component_2_incident_report_repository.dart';
import 'package:decentralized_hiking_ai/features/component_2/data/component_2_photo_source.dart';
import 'package:decentralized_hiking_ai/features/component_2/domain/component_2_demo_photo.dart';
import 'package:decentralized_hiking_ai/features/component_2/domain/component_2_detection.dart';
import 'package:decentralized_hiking_ai/features/component_2/domain/component_2_incident_report.dart';
import 'package:decentralized_hiking_ai/features/component_2/presentation/component_2_controller.dart';
import 'package:decentralized_hiking_ai/features/component_2/presentation/component_2_home.dart';
import 'package:decentralized_hiking_ai/app/app.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  final sourceImage = Uint8List.fromList(
    img.encodeJpg(img.Image(width: 24, height: 16)),
  );
  final photoResult = Component2PhotoResult(
    detections: const [
      Component2Detection(
        task: DetectionTask.litter,
        label: 'litter',
        confidence: 0.82,
        box: NormalizedBox(0.1, 0.2, 0.4, 0.6),
      ),
      Component2Detection(
        task: DetectionTask.obstacle,
        label: 'rock_region',
        confidence: 0.71,
        box: NormalizedBox(0.5, 0.2, 0.8, 0.6),
      ),
    ],
    imageWidth: 24,
    imageHeight: 16,
    inferenceDuration: const Duration(milliseconds: 84),
    modelVersion: 'test-manifest',
    modelQualityAccepted: false,
  );

  test(
    'demo catalog uses only the five planned development photo names',
    () async {
      final samples = await AssetComponent2DemoPhotoRepository().samples();

      expect(samples.map((sample) => sample.assetPath.split('/').last), [
        'litter_on_trail.jpg',
        'litter_multiple.jpg',
        'rock_on_trail.jpg',
        'fallen_log.jpg',
        'clean_trail.jpg',
      ]);
      expect(samples.every((sample) => sample.demoOnly), isTrue);
      expect(samples.every((sample) => !sample.isAvailable), isTrue);
      expect(
        samples.every((sample) => sample.sourceDatasetOrOwner == null),
        isTrue,
      );
      expect(samples.every((sample) => sample.sourceSplit == null), isTrue);
      expect(
        samples.every(
          (sample) => sample.licenseProvenanceNote.contains('Pending'),
        ),
        isTrue,
      );
    },
  );

  test(
    'sample selection runs the local analyzer and maps guarded results',
    () async {
      final completion = Completer<PhotoAnalysis>();
      final analyzer = FakeAnalyzer(() => completion.future);
      final controller = Component2Controller(
        inference: analyzer,
        demoPhotos: FakeDemoPhotos(sourceImage),
      );
      const sample = Component2DemoPhoto(
        id: 'sample_litter',
        title: 'Litter on trail',
        category: 'Litter',
        assetPath: 'assets/demo/component_2/litter_on_trail.jpg',
        isAvailable: true,
      );

      final selection = controller.selectSample(sample);
      await Future<void>.delayed(Duration.zero);
      expect(controller.isAnalyzing, isTrue);
      expect(controller.isBusy, isTrue);

      completion.complete(
        PhotoAnalysis(result: photoResult, displayImage: sourceImage),
      );
      await selection;

      expect(analyzer.receivedBytes, sourceImage);
      expect(controller.selectedSample, sample);
      expect(controller.result?.litterDetections, hasLength(1));
      expect(controller.result?.rockDetections, hasLength(1));
      expect(controller.result?.trailCondition, 'not_assessed');
      expect(controller.result?.modelQualityAccepted, isFalse);
      expect(controller.isBusy, isFalse);
      controller.dispose();
    },
  );

  test(
    'gallery permission failure is retryable and preserves the current photo',
    () async {
      final photoSource = FakePhotoSource(
        () async => throw PlatformException(code: 'photo_access_denied'),
      );
      final controller = Component2Controller(
        inference: FakeAnalyzer(
          () async =>
              PhotoAnalysis(result: photoResult, displayImage: sourceImage),
        ),
        photoSource: photoSource,
        demoPhotos: FakeDemoPhotos(sourceImage),
      );
      const sample = Component2DemoPhoto(
        id: 'sample_litter',
        title: 'Litter on trail',
        category: 'Litter',
        assetPath: 'assets/demo/component_2/litter_on_trail.jpg',
        isAvailable: true,
      );
      await controller.selectSample(sample);

      await controller.selectPhoto(ImageSource.gallery);
      expect(controller.error, isA<PlatformException>());
      expect(controller.displayImage, sourceImage);
      expect(controller.result, same(photoResult));
      expect(controller.isBusy, isFalse);

      photoSource.pickImage = () async => sourceImage;
      await controller.selectPhoto(ImageSource.gallery);
      expect(controller.error, isNull);
      expect(controller.result, same(photoResult));
      expect(controller.selectedPhotoDescription, 'Gallery photo');
      controller.dispose();
    },
  );

  test(
    'offline reports persist with compact photo, labels and local status',
    () async {
      SharedPreferences.setMockInitialValues({});
      final reports = SharedPreferencesComponent2IncidentReportRepository();
      final controller = Component2Controller(
        inference: FakeAnalyzer(
          () async =>
              PhotoAnalysis(result: photoResult, displayImage: sourceImage),
        ),
        demoPhotos: FakeDemoPhotos(sourceImage),
        reports: reports,
      );
      const sample = Component2DemoPhoto(
        id: 'sample_litter',
        title: 'Litter on trail',
        category: 'Litter',
        assetPath: 'assets/demo/component_2/litter_on_trail.jpg',
        isAvailable: true,
      );
      await controller.selectSample(sample);
      final report = await controller.saveIncidentReport(
        incidentType: 'litter / waste',
        notes: '  beside the path  ',
        location: '  north loop  ',
        createdAt: DateTime(2026, 10, 22, 10),
      );
      final restored =
          (await SharedPreferencesComponent2IncidentReportRepository().all())
              .single;

      expect(report.status, 'Saved offline');
      expect(report.notes, 'beside the path');
      expect(report.location, 'north loop');
      expect(restored.detectedClasses, ['litter', 'rock_region']);
      expect(restored.photoThumbnail, isNotEmpty);
      expect(restored.createdAt, DateTime(2026, 10, 22, 10));
      expect(restored.status, 'Saved offline');
      expect(restored.source, 'User reported');
      controller.dispose();
    },
  );

  testWidgets(
    'result card shows measurements, on-device mode and report safety guard',
    (tester) async {
      final controller =
          Component2Controller(
              inference: FakeAnalyzer(
                () async => PhotoAnalysis(
                  result: photoResult,
                  displayImage: sourceImage,
                ),
              ),
              demoPhotos: FakeDemoPhotos(sourceImage, demoSamples: const []),
              reports: MemoryReports(),
            )
            ..displayImage = sourceImage
            ..result = photoResult
            ..selectedPhotoDescription = 'Gallery photo';

      await tester.pumpWidget(
        MaterialApp(home: Component2Home(controller: controller)),
      );
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(
        find.text('Analysis results'),
        400,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();

      expect(find.text('Environmental observation level'), findsOneWidget);
      expect(find.text('Attention recommended'), findsOneWidget);
      expect(
        find.text(
          'Development-only model. Research accuracy acceptance was not met; observations are not definitive safety information.',
        ),
        findsOneWidget,
      );
      expect(find.text('Detection 1 · 82.0%'), findsOneWidget);
      expect(find.text('Detection 1 · 71.0%'), findsOneWidget);
      expect(find.text('On-device'), findsOneWidget);
      expect(
        find.text(
          'Trail safety and route blockage are not assessed by the current model.',
        ),
        findsNothing,
      );
      await tester.scrollUntilVisible(
        find.text('Not assessed in current PP1 model'),
        350,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('Not assessed'), findsNWidgets(4));
      expect(find.text('Trail condition observations'), findsOneWidget);
      expect(find.text('Erosion'), findsOneWidget);
      expect(find.text('Exposed roots'), findsOneWidget);
      expect(find.text('Debris'), findsNothing);
      expect(find.text('Trail blockage'), findsOneWidget);
      expect(find.text('Not assessed in current PP1 model'), findsOneWidget);
      await tester.scrollUntilVisible(
        find.text('Report environmental issue'),
        350,
        scrollable: find.byType(Scrollable).first,
      );
      expect(find.text('Report environmental issue'), findsOneWidget);

      await tester.ensureVisible(find.text('Report environmental issue'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Report environmental issue'));
      await tester.pumpAndSettle();
      expect(find.text('Source: AI observation'), findsOneWidget);
      expect(find.text('Save offline report'), findsOneWidget);
      expect(find.text('AI detections'), findsOneWidget);
      expect(find.text('Observation: Attention recommended'), findsOneWidget);
      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Erosion / trail damage').last);
      await tester.pumpAndSettle();
      expect(find.text('Source: User reported'), findsOneWidget);
      expect(
        find.text(
          'This category is user-reported and is not detected by the current model.',
        ),
        findsOneWidget,
      );
      await tester.ensureVisible(find.text('Save offline report'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Save offline report'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 350));
      expect(find.text('Saved offline'), findsOneWidget);
      expect((await controller.reports.all()), hasLength(1));
      final storedReport = (await controller.reports.all()).single;
      expect(storedReport.incidentType, 'Erosion / trail damage');
      expect(storedReport.source, 'User reported');
      expect(storedReport.detectedClasses, ['litter', 'rock_region']);
      expect(
        storedReport.environmentalObservationLevel,
        'Attention recommended',
      );
      expect(storedReport.detectionCount, 2);
      expect(storedReport.highestConfidence, 0.82);
      await tester.tap(find.byTooltip('Saved reports'));
      await tester.pumpAndSettle();
      expect(find.text('Saved reports'), findsOneWidget);
      expect(find.text('Erosion / trail damage'), findsOneWidget);
      expect(find.textContaining('Saved offline'), findsNWidgets(2));
      controller.dispose();
    },
  );

  testWidgets('PP1 landing page opens Component 2 and shows scoped info', (
    tester,
  ) async {
    await tester.pumpWidget(const HikingAssistantApp());
    await tester.pumpAndSettle();

    expect(
      find.text('Hiking Safety & Environmental Monitoring'),
      findsOneWidget,
    );
    expect(find.text('Trail & Environmental Monitoring'), findsOneWidget);
    expect(find.byType(Card), findsOneWidget);
    expect(find.text('Plan your visit'), findsNothing);
    expect(find.text('Terrain & effort'), findsNothing);
    expect(find.text('Hiker safety assistant'), findsNothing);
    expect(find.text('Offline AI'), findsNothing);
    expect(find.text('Prototype'), findsNothing);

    await tester.tap(find.byType(Card));
    for (var frame = 0; frame < 8; frame++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    expect(find.text('A clearer view of your surroundings'), findsOneWidget);
    expect(find.text('Trail & Environmental Monitoring'), findsOneWidget);

    await tester.tap(find.byTooltip('About this preview'));
    await tester.pump(const Duration(milliseconds: 400));
    expect(
      find.text(
        'This PP1 build demonstrates local environmental-object detection. Trail safety and route blockage are not yet certified outputs.',
      ),
      findsOneWidget,
    );
  });

  testWidgets(
    'camera unavailable shows a retryable message, not a model error',
    (tester) async {
      final photoSource = FakePhotoSource(
        () async => throw PlatformException(code: 'no_available_camera'),
      );
      final controller = Component2Controller(
        inference: FakeAnalyzer(
          () async =>
              PhotoAnalysis(result: photoResult, displayImage: sourceImage),
        ),
        photoSource: photoSource,
        demoPhotos: FakeDemoPhotos(sourceImage),
        reports: MemoryReports(),
      );

      await tester.pumpWidget(
        MaterialApp(home: Component2Home(controller: controller)),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Take photo'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 350));
      expect(
        find.text(
          'Camera unavailable on this device. Use Choose photo or a sample image.',
        ),
        findsOneWidget,
      );

      tester
          .state<ScaffoldMessengerState>(find.byType(ScaffoldMessenger))
          .hideCurrentSnackBar();
      await tester.pumpAndSettle();
      photoSource.pickImage = () async => sourceImage;
      await tester.ensureVisible(find.text('Choose photo'));
      await tester.tap(find.text('Choose photo'));
      await tester.pumpAndSettle();
      expect(controller.selectedPhotoDescription, 'Gallery photo');
      expect(controller.error, isNull);
      controller.dispose();
    },
  );
}

class FakeAnalyzer implements Component2PhotoAnalyzer {
  FakeAnalyzer(this.analyzePhoto);

  final Future<PhotoAnalysis> Function() analyzePhoto;
  Uint8List? receivedBytes;

  @override
  Future<PhotoAnalysis> analyze(Uint8List bytes) {
    receivedBytes = bytes;
    return analyzePhoto();
  }

  @override
  void dispose() {}
}

class FakePhotoSource implements Component2PhotoSource {
  FakePhotoSource(this.pickImage);

  Future<Uint8List?> Function() pickImage;

  @override
  Future<Uint8List?> pick(ImageSource source) => pickImage();
}

class FakeDemoPhotos implements Component2DemoPhotoRepository {
  FakeDemoPhotos(this.bytes, {this.demoSamples = const []});

  final Uint8List bytes;
  final List<Component2DemoPhoto> demoSamples;

  @override
  Future<Uint8List> load(Component2DemoPhoto sample) async => bytes;

  @override
  Future<List<Component2DemoPhoto>> samples() async => demoSamples;
}

class MemoryReports implements Component2IncidentReportRepository {
  final List<Component2IncidentReport> saved = [];

  @override
  Future<List<Component2IncidentReport>> all() async => List.of(saved);

  @override
  Future<void> save(Component2IncidentReport report) async {
    saved.add(report);
  }
}
