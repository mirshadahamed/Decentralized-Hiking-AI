import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';

import '../domain/component_2_detection.dart';
import 'component_2_controller.dart';

class Component2Home extends StatefulWidget {
  const Component2Home({super.key});

  @override
  State<Component2Home> createState() => _Component2HomeState();
}

class _Component2HomeState extends State<Component2Home> {
  late final Component2Controller _controller;

  @override
  void initState() {
    super.initState();
    _controller = Component2Controller();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Litter & trail objects')),
        body: AnimatedBuilder(
          animation: _controller,
          builder: (context, _) => ListView(
            padding: const EdgeInsets.all(16),
            children: [
              const _DevelopmentNotice(),
              const SizedBox(height: 12),
              Row(children: [
                Expanded(
                  child: FilledButton.icon(
                    onPressed: _controller.isAnalyzing ? null : () => _controller.selectPhoto(ImageSource.gallery),
                    icon: const Icon(Icons.photo_library_outlined),
                    label: const Text('Choose photo'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _controller.isAnalyzing ? null : () => _controller.selectPhoto(ImageSource.camera),
                    icon: const Icon(Icons.camera_alt_outlined),
                    label: const Text('Take photo'),
                  ),
                ),
              ]),
              if (_controller.isAnalyzing) ...[
                const SizedBox(height: 22),
                const Center(child: CircularProgressIndicator()),
                const Center(child: Padding(padding: EdgeInsets.all(8), child: Text('Running locally on this device…'))),
              ],
              if (_controller.error != null) _ErrorCard(message: _errorText(_controller.error!)),
              if (_controller.displayImage != null && _controller.result != null) ...[
                const SizedBox(height: 16),
                _PhotoOverlay(image: _controller.displayImage!, result: _controller.result!),
                _Results(result: _controller.result!),
              ],
            ],
          ),
        ),
      );

  String _errorText(Object error) {
    if (error is PlatformException) {
      if (error.code == 'camera_access_denied' || error.code == 'photo_access_denied' || error.code == 'permission_denied') {
        return 'Camera or photo access was denied. Allow access in Android app settings, then try again.';
      }
      return 'The camera or photo picker could not open. Check the app permission and try again.';
    }
    if (error is FormatException) return 'This image could not be read. Choose a JPG, PNG or WebP photo.';
    if (error is StateError || error is MissingPluginException) {
      return 'The on-device model could not load or its tensor details did not match the model manifest. ${error.toString()}';
    }
    return 'Photo analysis failed. ${error.toString()}';
  }
}

class _DevelopmentNotice extends StatelessWidget {
  const _DevelopmentNotice();

  @override
  Widget build(BuildContext context) => Card(
        color: Theme.of(context).colorScheme.errorContainer,
        child: const ListTile(
          leading: Icon(Icons.warning_amber_rounded),
          title: Text('Development models only'),
          subtitle: Text(
            'These models failed research accuracy checks. Results can miss or mislabel objects and are not safety information. No route is assessed.',
          ),
        ),
      );
}

class _PhotoOverlay extends StatelessWidget {
  const _PhotoOverlay({required this.image, required this.result});
  final Uint8List image;
  final Component2PhotoResult result;

  @override
  Widget build(BuildContext context) => ClipRRect(
        borderRadius: BorderRadius.circular(12),
        child: AspectRatio(
          aspectRatio: result.imageWidth / result.imageHeight,
          child: Stack(fit: StackFit.expand, children: [
            Image.memory(image, fit: BoxFit.fill),
            CustomPaint(painter: _DetectionPainter(result.detections)),
          ]),
        ),
      );
}

class _DetectionPainter extends CustomPainter {
  const _DetectionPainter(this.detections);
  final List<Component2Detection> detections;

  @override
  void paint(Canvas canvas, Size size) {
    for (final detection in detections) {
      final color = detection.task == DetectionTask.litter ? Colors.orangeAccent : Colors.lightGreenAccent;
      final rect = Rect.fromLTRB(
        detection.box.left * size.width,
        detection.box.top * size.height,
        detection.box.right * size.width,
        detection.box.bottom * size.height,
      );
      final mask = detection.mask;
      if (mask != null) {
        final cellWidth = rect.width / mask.width;
        final cellHeight = rect.height / mask.height;
        final fill = Paint()..color = color.withValues(alpha: 0.30);
        final outline = Paint()
          ..color = color
          ..strokeWidth = 1.3
          ..style = PaintingStyle.stroke;
        for (var y = 0; y < mask.height; y++) {
          for (var x = 0; x < mask.width; x++) {
            if (mask.values[y * mask.width + x] < 0.5) continue;
            final cell = Rect.fromLTWH(rect.left + x * cellWidth, rect.top + y * cellHeight, cellWidth, cellHeight);
            canvas.drawRect(cell, fill);
          }
        }
        canvas.drawRect(rect, outline);
      } else {
        canvas.drawRect(rect, Paint()
          ..color = color
          ..strokeWidth = 2
          ..style = PaintingStyle.stroke);
      }
      final label = '${detection.label} ${(detection.confidence * 100).toStringAsFixed(0)}%';
      final text = TextPainter(
        text: TextSpan(text: label, style: const TextStyle(color: Colors.black, fontSize: 11, fontWeight: FontWeight.bold)),
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: size.width);
              final labelRect = Rect.fromLTWH(
                rect.left,
                (rect.top - text.height - 4).clamp(0.0, size.height).toDouble(),
                text.width + 8,
                text.height + 4,
              );
      canvas.drawRect(labelRect, Paint()..color = color);
      text.paint(canvas, Offset(labelRect.left + 4, labelRect.top + 2));
    }
  }

  @override
  bool shouldRepaint(covariant _DetectionPainter oldDelegate) => oldDelegate.detections != detections;
}

class _Results extends StatelessWidget {
  const _Results({required this.result});
  final Component2PhotoResult result;

  @override
  Widget build(BuildContext context) => Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const SizedBox(height: 12),
        _DetectionList(title: 'Litter / garbage', detections: result.litterDetections),
        _DetectionList(title: 'Rocks', detections: result.rockDetections),
        _DetectionList(title: 'Logs', detections: result.logDetections),
        Card(child: Column(children: [
          ListTile(title: const Text('Inference time'), subtitle: Text('${result.inferenceDuration.inMilliseconds} ms')),
          ListTile(title: const Text('Photo dimensions'), subtitle: Text('${result.imageWidth} × ${result.imageHeight}')),
          ListTile(title: const Text('Trail condition'), subtitle: Text(result.trailCondition)),
          ListTile(title: const Text('Model manifest'), subtitle: Text(result.modelVersion)),
          const ListTile(
            leading: Icon(Icons.info_outline),
            title: Text('Development result'),
            subtitle: Text('Detection presence or absence does not establish whether a path is blocked, clear or safe.'),
          ),
        ])),
      ]);
}

class _DetectionList extends StatelessWidget {
  const _DetectionList({required this.title, required this.detections});
  final String title;
  final List<Component2Detection> detections;

  @override
  Widget build(BuildContext context) => Card(
        child: ExpansionTile(
          initiallyExpanded: true,
          title: Text('$title (${detections.length})'),
          children: detections.isEmpty
              ? const [ListTile(title: Text('No detections returned by this development model.'))]
              : detections.map((d) => ListTile(
                    dense: true,
                    title: Text(d.label),
                    trailing: Text('${(100 * d.confidence).toStringAsFixed(1)}% confidence'),
                  )).toList(),
        ),
      );
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard({required this.message});
  final String message;

  @override
  Widget build(BuildContext context) => Card(
        color: Theme.of(context).colorScheme.errorContainer,
        child: ListTile(leading: const Icon(Icons.error_outline), title: const Text('Could not analyze photo'), subtitle: Text(message)),
      );
}
import 'dart:typed_data';

