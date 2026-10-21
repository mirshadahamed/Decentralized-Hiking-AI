import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:intl/intl.dart' show DateFormat;

import '../data/component_2_demo_photo_repository.dart';
import '../data/component_2_incident_report_repository.dart';
import '../domain/component_2_demo_photo.dart';
import '../domain/component_2_detection.dart';
import '../domain/component_2_incident_report.dart';
import 'component_2_controller.dart';

class Component2Home extends StatefulWidget {
  const Component2Home({
    super.key,
    this.controller,
    this.demoPhotoRepository,
    this.reportRepository,
  });

  final Component2Controller? controller;
  final Component2DemoPhotoRepository? demoPhotoRepository;
  final Component2IncidentReportRepository? reportRepository;

  @override
  State<Component2Home> createState() => _Component2HomeState();
}

class _Component2HomeState extends State<Component2Home> {
  late final Component2Controller _controller;
  late final Component2DemoPhotoRepository _demoPhotos;
  late final Component2IncidentReportRepository _reports;
  late final Future<List<Component2DemoPhoto>> _samples;
  late final bool _ownsController;

  @override
  void initState() {
    super.initState();
    _ownsController = widget.controller == null;
    _controller =
        widget.controller ??
        Component2Controller(
          demoPhotos: widget.demoPhotoRepository,
          reports: widget.reportRepository,
        );
    _demoPhotos = widget.demoPhotoRepository ?? _controller.demoPhotos;
    _reports = widget.reportRepository ?? _controller.reports;
    _samples = _demoPhotos.samples();
  }

  @override
  void dispose() {
    if (_ownsController) _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(
      title: Text(
        'Litter & Trail Monitoring',
        style: Theme.of(context).textTheme.titleMedium
            ?.copyWith(fontWeight: FontWeight.w600),
      ),
      actions: [
        IconButton(
          tooltip: 'About prototype AI',
          onPressed: _showPrototypeInfo,
          icon: const Icon(Icons.info_outline),
        ),
        IconButton(
          tooltip: 'Saved reports',
          onPressed: _openSavedReports,
          icon: const Icon(Icons.assignment_outlined),
        ),
      ],
    ),
    body: AnimatedBuilder(
      animation: _controller,
      builder: (context, _) => ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
        children: [
          _Header(
            busy: _controller.isBusy,
            isAnalyzing: _controller.isAnalyzing,
          ),
          const SizedBox(height: 18),
          _AnalysisPhotoCard(
            image: _controller.displayImage,
            result: _controller.result,
            description: _controller.selectedPhotoDescription,
            busy: _controller.isBusy,
            progressLabel: _progressLabel,
            onChoosePhoto: () =>
                _perform(() => _controller.selectPhoto(ImageSource.gallery)),
            onTakePhoto: () =>
                _perform(() => _controller.selectPhoto(ImageSource.camera)),
            onUseSample: () => _useFirstAvailableSample(),
          ),
          const SizedBox(height: 22),
          _sectionHeading(context, 'Try a sample'),
          const SizedBox(height: 10),
          _SampleCarousel(samples: _samples, onTap: _onSampleTapped),
          if (_controller.result case final result?) ...[
            const SizedBox(height: 22),
            _sectionHeading(context, 'Analysis results'),
            const SizedBox(height: 10),
            _ResultSummary(result: result),
          ],
          if (_controller.displayImage != null) ...[
            const SizedBox(height: 12),
            OutlinedButton.icon(
              onPressed: _openIncidentReport,
              icon: const Icon(Icons.add_location_alt_outlined),
              label: const Text('Create incident report'),
            ),
          ],
          const SizedBox(height: 16),
          TextButton.icon(
            onPressed: _openSavedReports,
            icon: const Icon(Icons.folder_open_outlined),
            label: const Text('Saved reports'),
          ),
        ],
      ),
    ),
  );

  String get _progressLabel {
    if (_controller.isPickingPhoto) return 'Opening photo picker…';
    if (_controller.isLoadingSample) return 'Loading sample offline…';
    return 'Analyzing photo offline…';
  }

  Widget _sectionHeading(BuildContext context, String title) => Text(
    title,
    style: Theme.of(context).textTheme.titleMedium
        ?.copyWith(fontWeight: FontWeight.w700),
  );

  Future<void> _perform(Future<void> Function() action) async {
    await action();
    if (!mounted) return;
    final error = _controller.error;
    if (error != null) {
      _showMessage(_messageForError(error));
      _controller.clearError();
    }
  }

  String _messageForError(Object error) {
    if (error is PlatformException) {
      switch (error.code) {
        case 'no_available_camera':
          return 'Camera unavailable on this device. Use Choose photo or a sample image.';
        case 'camera_access_denied':
          return 'Camera permission was denied. Allow camera access in Android settings, or choose a photo or sample.';
        case 'photo_access_denied':
        case 'permission_denied':
          return 'Photo access was denied. You can retry or use a sample image.';
      }
      return 'The photo action failed. Please try again or use a sample image.';
    }
    if (error is FormatException) {
      return 'This photo could not be read. Choose another image.';
    }
    if (error is StateError &&
        error.message.startsWith('Demo photo is not installed:')) {
      return 'Add the named demo photo under assets/demo/component_2/ and rebuild the app.';
    }
    return 'Offline analysis could not finish. Try another photo or sample.';
  }

  Future<void> _onSampleTapped(Component2DemoPhoto sample) async {
    if (!sample.isAvailable) {
      _showMessage(
        'Copy ${sample.assetPath.split('/').last} into assets/demo/component_2/ to enable this sample.',
      );
      return;
    }
    await _perform(() => _controller.selectSample(sample));
  }

  Future<void> _useFirstAvailableSample() async {
    try {
      final samples = await _samples;
      if (!mounted) return;
      final available = samples.where((sample) => sample.isAvailable);
      if (available.isEmpty) {
        _showMessage(
          'Add a reviewed demo photo to assets/demo/component_2/ to use a sample.',
        );
        return;
      }
      await _perform(() => _controller.selectSample(available.first));
    } catch (_) {
      if (mounted) _showMessage('The sample-photo list could not be loaded.');
    }
  }

  void _showPrototypeInfo() {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => const SafeArea(
        child: Padding(
          padding: EdgeInsets.fromLTRB(24, 8, 24, 32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Prototype observations',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700),
              ),
              SizedBox(height: 10),
              Text(
                'AI results are prototype observations for environmental monitoring. Trail safety and route blockage are not assessed by the current model.',
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _openSavedReports() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => Component2SavedReportsPage(repository: _reports),
      ),
    );
  }

  Future<void> _openIncidentReport() async {
    final image = _controller.displayImage;
    final result = _controller.result;
    if (image == null) return;
    final saved = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (_) => _IncidentReportSheet(
        image: image,
        result: result,
        onSave: (incidentType, notes, location) async {
          await _controller.saveIncidentReport(
            incidentType: incidentType,
            notes: notes,
            location: location,
          );
        },
      ),
    );
    if (saved == true && mounted) _showMessage('Saved offline');
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.busy, required this.isAnalyzing});

  final bool busy;
  final bool isAnalyzing;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Observe the trail around you',
          style: Theme.of(context).textTheme.titleLarge
              ?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 4),
        Text(
          'Photo analysis runs locally on this device.',
          style: Theme.of(context).textTheme.bodyMedium
              ?.copyWith(color: scheme.onSurfaceVariant),
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 6,
          children: [
            _StatusChip(
              icon: Icons.offline_bolt_outlined,
              label: 'Offline AI',
              foreground: scheme.primary,
              background: scheme.primaryContainer,
            ),
            _StatusChip(
              icon: Icons.science_outlined,
              label: 'Prototype',
              foreground: scheme.tertiary,
              background: scheme.tertiaryContainer,
            ),
            if (busy)
              _StatusChip(
                icon: isAnalyzing ? Icons.auto_awesome : Icons.hourglass_top,
                label: isAnalyzing ? 'Analyzing' : 'Loading',
                foreground: scheme.onSurfaceVariant,
                background: scheme.surfaceContainerHighest,
              ),
          ],
        ),
      ],
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({
    required this.icon,
    required this.label,
    required this.foreground,
    required this.background,
  });

  final IconData icon;
  final String label;
  final Color foreground;
  final Color background;

  @override
  Widget build(BuildContext context) => Chip(
    avatar: Icon(icon, size: 16, color: foreground),
    label: Text(label),
    backgroundColor: background,
    labelStyle: TextStyle(
      color: foreground,
      fontSize: 12,
      fontWeight: FontWeight.w600,
    ),
    visualDensity: VisualDensity.compact,
    side: BorderSide.none,
    padding: const EdgeInsets.symmetric(horizontal: 4),
  );
}

class _AnalysisPhotoCard extends StatelessWidget {
  const _AnalysisPhotoCard({
    required this.image,
    required this.result,
    required this.description,
    required this.busy,
    required this.progressLabel,
    required this.onChoosePhoto,
    required this.onTakePhoto,
    required this.onUseSample,
  });

  final Uint8List? image;
  final Component2PhotoResult? result;
  final String description;
  final bool busy;
  final String progressLabel;
  final VoidCallback onChoosePhoto;
  final VoidCallback onTakePhoto;
  final VoidCallback onUseSample;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            height: 316,
            child: image == null
                ? ColoredBox(
                    color: scheme.surfaceContainerLow,
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.add_photo_alternate_outlined,
                          size: 52,
                          color: scheme.primary,
                        ),
                        const SizedBox(height: 12),
                        Text(
                          'Upload a trail photo',
                          style: Theme.of(context).textTheme.titleMedium
                              ?.copyWith(fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: 5),
                        Text(
                          'Choose a photo, take one, or try a sample below.',
                          textAlign: TextAlign.center,
                          style: Theme.of(context).textTheme.bodySmall
                              ?.copyWith(color: scheme.onSurfaceVariant),
                        ),
                      ],
                    ),
                  )
                : Stack(
                    fit: StackFit.expand,
                    children: [
                      Image.memory(
                        image!,
                        fit: BoxFit.contain,
                        errorBuilder: (context, error, stackTrace) => Center(
                          child: Text(
                            'Photo preview unavailable',
                            style: TextStyle(color: scheme.onSurfaceVariant),
                          ),
                        ),
                      ),
                      if (result != null)
                        CustomPaint(
                          painter: _DetectionPainter(
                            result!.detections,
                            result!.imageWidth,
                            result!.imageHeight,
                            Directionality.of(context),
                          ),
                        ),
                      if (busy)
                        ColoredBox(
                          color: Colors.black.withValues(alpha: 0.35),
                          child: Center(
                            child: Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 18,
                                vertical: 12,
                              ),
                              decoration: BoxDecoration(
                                color: scheme.surface,
                                borderRadius: BorderRadius.circular(16),
                              ),
                              child: const Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  SizedBox(
                                    width: 18,
                                    height: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  ),
                                  SizedBox(width: 12),
                                  Text('Analyzing photo offline...'),
                                ],
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
          ),
          if (image != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
              child: Text(
                description,
                style: Theme.of(context).textTheme.labelMedium
                    ?.copyWith(color: scheme.onSurfaceVariant),
              ),
            ),
          Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: FilledButton.icon(
                        onPressed: busy ? null : onChoosePhoto,
                        icon: const Icon(Icons.photo_library_outlined),
                        label: const Text('Choose photo'),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: busy ? null : onTakePhoto,
                        icon: const Icon(Icons.camera_alt_outlined),
                        label: const Text('Take photo'),
                      ),
                    ),
                  ],
                ),
                TextButton.icon(
                  onPressed: busy ? null : onUseSample,
                  icon: const Icon(Icons.landscape_outlined),
                  label: const Text('Use sample'),
                ),
                if (busy) ...[
                  LinearProgressIndicator(
                    minHeight: 3,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    progressLabel,
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _DetectionPainter extends CustomPainter {
  const _DetectionPainter(
    this.detections,
    this.imageWidth,
    this.imageHeight,
    this.textDirection,
  );

  final List<Component2Detection> detections;
  final int imageWidth;
  final int imageHeight;
  final TextDirection textDirection;

  @override
  void paint(Canvas canvas, Size size) {
    final imageSize = Size(imageWidth.toDouble(), imageHeight.toDouble());
    final fittedSize = applyBoxFit(BoxFit.contain, imageSize, size).destination;
    final imageRect = Alignment.center.inscribe(fittedSize, Offset.zero & size);
    canvas.save();
    canvas.clipRect(imageRect);
    for (final detection in detections) {
      final color = switch (detection.label) {
        'litter' => const Color(0xFFFFB74D),
        'rock_region' => const Color(0xFF4DB6AC),
        _ => const Color(0xFFAED581),
      };
      final box = detection.box;
      final rect = Rect.fromLTRB(
        imageRect.left + box.left * imageRect.width,
        imageRect.top + box.top * imageRect.height,
        imageRect.left + box.right * imageRect.width,
        imageRect.top + box.bottom * imageRect.height,
      );
      final mask = detection.mask;
      if (mask != null) {
        final cellWidth = rect.width / mask.width;
        final cellHeight = rect.height / mask.height;
        final fill = Paint()..color = color.withValues(alpha: 0.30);
        final outline = Paint()
          ..color = color
          ..strokeWidth = 1.5
          ..style = PaintingStyle.stroke;
        for (var y = 0; y < mask.height; y++) {
          for (var x = 0; x < mask.width; x++) {
            if (mask.values[y * mask.width + x] < 0.5) continue;
            canvas.drawRect(
              Rect.fromLTWH(
                rect.left + x * cellWidth,
                rect.top + y * cellHeight,
                cellWidth,
                cellHeight,
              ),
              fill,
            );
          }
        }
        canvas.drawRect(rect, outline);
      } else {
        canvas.drawRect(
          rect,
          Paint()
            ..color = color
            ..strokeWidth = 2
            ..style = PaintingStyle.stroke,
        );
      }
      _paintLabel(canvas, size, rect, detection, color);
    }
    canvas.restore();
  }

  void _paintLabel(
    Canvas canvas,
    Size size,
    Rect box,
    Component2Detection detection,
    Color color,
  ) {
    final label =
        '${detection.label} ${(detection.confidence * 100).toStringAsFixed(0)}%';
    final text = TextPainter(
      text: TextSpan(
        text: label,
        style: const TextStyle(
          color: Colors.black,
          fontSize: 11,
          fontWeight: FontWeight.bold,
        ),
      ),
      textDirection: textDirection,
    )..layout(maxWidth: size.width);
    final top = math.max(0.0, box.top - text.height - 4);
    final labelRect = Rect.fromLTWH(
      box.left,
      top,
      text.width + 8,
      text.height + 4,
    );
    canvas.drawRRect(
      RRect.fromRectAndRadius(labelRect, const Radius.circular(4)),
      Paint()..color = color,
    );
    text.paint(canvas, Offset(labelRect.left + 4, labelRect.top + 2));
  }

  @override
  bool shouldRepaint(covariant _DetectionPainter oldDelegate) =>
      oldDelegate.detections != detections ||
      oldDelegate.imageWidth != imageWidth ||
      oldDelegate.imageHeight != imageHeight ||
      oldDelegate.textDirection != textDirection;
}

class _SampleCarousel extends StatelessWidget {
  const _SampleCarousel({required this.samples, required this.onTap});

  final Future<List<Component2DemoPhoto>> samples;
  final ValueChanged<Component2DemoPhoto> onTap;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: 174,
    child: FutureBuilder<List<Component2DemoPhoto>>(
      future: samples,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return const Center(child: Text('Sample list is unavailable.'));
        }
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator.adaptive());
        }
        return ListView.separated(
          scrollDirection: Axis.horizontal,
          itemCount: snapshot.data!.length,
          separatorBuilder: (context, index) => const SizedBox(width: 10),
          itemBuilder: (context, index) {
            final sample = snapshot.data![index];
            return SizedBox(
              width: 158,
              child: Card(
                clipBehavior: Clip.antiAlias,
                child: InkWell(
                  onTap: () => onTap(sample),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Expanded(
                        child: sample.isAvailable
                            ? Image.asset(
                                sample.assetPath,
                                fit: BoxFit.cover,
                                errorBuilder: (context, error, stackTrace) =>
                                    _SamplePlaceholder(sample: sample),
                              )
                            : _SamplePlaceholder(sample: sample),
                      ),
                      Padding(
                        padding: const EdgeInsets.fromLTRB(10, 8, 10, 9),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              sample.title,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: Theme.of(context).textTheme.labelLarge,
                            ),
                            Text(
                              sample.category,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: Theme.of(context).textTheme.labelSmall,
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        );
      },
    ),
  );
}

class _SamplePlaceholder extends StatelessWidget {
  const _SamplePlaceholder({required this.sample});

  final Component2DemoPhoto sample;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return ColoredBox(
      color: scheme.surfaceContainerLow,
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.add_a_photo_outlined, color: scheme.primary, size: 26),
            const SizedBox(height: 5),
            Text(
              sample.isAvailable ? 'Demo photo' : 'Photo not installed',
              textAlign: TextAlign.center,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.labelSmall,
            ),
            if (!sample.isAvailable)
              Text(
                'development only',
                style: Theme.of(context).textTheme.labelSmall
                    ?.copyWith(color: scheme.onSurfaceVariant),
              ),
          ],
        ),
      ),
    );
  }
}

class _ResultSummary extends StatelessWidget {
  const _ResultSummary({required this.result});

  final Component2PhotoResult result;

  @override
  Widget build(BuildContext context) {
    final all = result.detections;
    final highest = all.isEmpty
        ? '—'
        : '${(all.map((item) => item.confidence).reduce(math.max) * 100).toStringAsFixed(1)}%';
    return Card(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  Icons.check_circle_outline,
                  color: Theme.of(context).colorScheme.primary,
                ),
                const SizedBox(width: 10),
                Text(
                  'Analysis complete',
                  style: Theme.of(context).textTheme.titleMedium
                      ?.copyWith(fontWeight: FontWeight.w700),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _ObservationRow(
              label: 'Litter',
              detected: result.litterDetections.isNotEmpty,
            ),
            _ObservationRow(
              label: 'Rock',
              detected: result.rockDetections.isNotEmpty,
            ),
            _ObservationRow(
              label: 'Log',
              detected: result.logDetections.isNotEmpty,
            ),
            const Divider(height: 22),
            _ValueRow(label: 'Highest confidence', value: highest),
            _ValueRow(label: 'Number of detections', value: '${all.length}'),
            _ValueRow(
              label: 'Inference time',
              value: '${result.inferenceDuration.inMilliseconds} ms',
            ),
            const _ValueRow(label: 'Processing mode', value: 'Offline'),
            const _ValueRow(label: 'Trail condition', value: 'Not assessed'),
          ],
        ),
      ),
    );
  }
}

class _ObservationRow extends StatelessWidget {
  const _ObservationRow({required this.label, required this.detected});

  final String label;
  final bool detected;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(
      children: [
        Icon(
          detected ? Icons.check_circle : Icons.remove_circle_outline,
          size: 18,
          color: detected
              ? Theme.of(context).colorScheme.primary
              : Theme.of(context).colorScheme.outline,
        ),
        const SizedBox(width: 8),
        Expanded(child: Text(label)),
        Text(detected ? 'Detected' : 'Not detected'),
      ],
    ),
  );
}

class _ValueRow extends StatelessWidget {
  const _ValueRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(
      children: [
        Expanded(child: Text(label)),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w600)),
      ],
    ),
  );
}

class _IncidentReportSheet extends StatefulWidget {
  const _IncidentReportSheet({
    required this.image,
    required this.result,
    required this.onSave,
  });

  final Uint8List image;
  final Component2PhotoResult? result;
  final Future<void> Function(String type, String notes, String location)
  onSave;

  @override
  State<_IncidentReportSheet> createState() => _IncidentReportSheetState();
}

class _IncidentReportSheetState extends State<_IncidentReportSheet> {
  static const _types = [
    'litter / waste',
    'rock / obstruction',
    'fallen log / branch',
    'other',
  ];
  final _notes = TextEditingController();
  final _location = TextEditingController();
  String _type = _types.first;
  bool _saving = false;
  String? _error;
  late final DateTime _createdAt = DateTime.now();

  @override
  void dispose() {
    _notes.dispose();
    _location.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final detected =
        widget.result?.detections
            .map((item) => item.label)
            .toSet()
            .join(', ') ??
        '';
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          20,
          4,
          20,
          MediaQuery.viewInsetsOf(context).bottom + 18,
        ),
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'Create incident report',
                style: Theme.of(context).textTheme.titleLarge
                    ?.copyWith(fontWeight: FontWeight.w700),
              ),
              const SizedBox(height: 14),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(12),
                    child: Image.memory(
                      widget.image,
                      width: 112,
                      height: 86,
                      fit: BoxFit.cover,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text('Detected classes'),
                        const SizedBox(height: 4),
                        Text(
                          detected.isEmpty ? 'No model observations' : detected,
                        ),
                        const SizedBox(height: 8),
                        const Text('Report status: Local draft'),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              Text(
                'Date and time: ${DateFormat('MMM d, yyyy · h:mm a').format(_createdAt)}',
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                initialValue: _type,
                decoration: const InputDecoration(
                  labelText: 'Incident type',
                  border: OutlineInputBorder(),
                ),
                items: _types
                    .map(
                      (type) =>
                          DropdownMenuItem(value: type, child: Text(type)),
                    )
                    .toList(growable: false),
                onChanged: _saving
                    ? null
                    : (value) => setState(() => _type = value ?? _type),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _notes,
                enabled: !_saving,
                maxLines: 3,
                decoration: const InputDecoration(
                  labelText: 'Notes (optional)',
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _location,
                enabled: !_saving,
                decoration: const InputDecoration(
                  labelText: 'Location (optional)',
                  hintText: 'For example, trail name or nearby landmark',
                  border: OutlineInputBorder(),
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 8),
                Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: _saving ? null : _save,
                icon: _saving
                    ? const SizedBox.square(
                        dimension: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.save_outlined),
                label: Text(
                  _saving ? 'Saving offline…' : 'Save offline report',
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await widget.onSave(_type, _notes.text, _location.text);
      if (mounted) Navigator.of(context).pop(true);
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error =
            'The report could not be saved on this device. Please try again.';
      });
    }
  }
}

class Component2SavedReportsPage extends StatefulWidget {
  const Component2SavedReportsPage({required this.repository, super.key});

  final Component2IncidentReportRepository repository;

  @override
  State<Component2SavedReportsPage> createState() =>
      _Component2SavedReportsPageState();
}

class _Component2SavedReportsPageState
    extends State<Component2SavedReportsPage> {
  late Future<List<Component2IncidentReport>> _reports;

  @override
  void initState() {
    super.initState();
    _reports = widget.repository.all();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Saved reports')),
    body: FutureBuilder<List<Component2IncidentReport>>(
      future: _reports,
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return const Center(
            child: Text('Saved reports could not be opened.'),
          );
        }
        if (!snapshot.hasData) {
          return const Center(child: CircularProgressIndicator.adaptive());
        }
        final reports = snapshot.data!;
        if (reports.isEmpty) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(32),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.folder_open_outlined, size: 44),
                  SizedBox(height: 10),
                  Text('No offline reports yet'),
                ],
              ),
            ),
          );
        }
        return ListView.separated(
          padding: const EdgeInsets.all(16),
          itemCount: reports.length,
          separatorBuilder: (context, index) => const SizedBox(height: 8),
          itemBuilder: (context, index) {
            final report = reports[index];
            return Card(
              child: ListTile(
                leading: ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: Image.memory(
                    report.photoThumbnail,
                    width: 58,
                    height: 58,
                    fit: BoxFit.cover,
                  ),
                ),
                title: Text(report.incidentType),
                subtitle: Text(
                  [
                    DateFormat('MMM d, yyyy · h:mm a').format(report.createdAt),
                    if (report.detectedClasses.isNotEmpty)
                      report.detectedClasses.join(', '),
                    if (report.location.isNotEmpty) report.location,
                    report.status,
                  ].join(' · '),
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),
                isThreeLine: true,
              ),
            );
          },
        );
      },
    ),
  );
}
