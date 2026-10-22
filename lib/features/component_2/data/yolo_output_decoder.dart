import 'dart:math' as math;
import 'dart:typed_data';

import '../domain/component_2_detection.dart';
import 'letterbox_preprocessor.dart';

/// Decodes the verified channel-major YOLOv8 dense output. Tensor data stays
/// flat in Float32List views to avoid allocating hundreds of thousands of
/// nested Dart numbers on a mobile device.
class YoloOutputDecoder {
  const YoloOutputDecoder();

  List<Component2Detection> decode({
    required Float32List dense,
    required int denseChannels,
    required int anchors,
    required Float32List? prototypes,
    required int prototypeWidth,
    required int prototypeHeight,
    required int prototypeChannels,
    required DetectionTask task,
    required List<String> labels,
    required Map<String, double> thresholds,
    required LetterboxTransform transform,
    double iouThreshold = 0.7,
    int maxDetections = 300,
  }) {
    final maskChannels = prototypes == null ? 0 : prototypeChannels;
    final classCount = denseChannels - 4 - maskChannels;
    if (dense.length != denseChannels * anchors ||
        classCount != labels.length ||
        (prototypes != null &&
            (prototypeChannels != 32 ||
                prototypes.length !=
                    prototypeWidth * prototypeHeight * prototypeChannels))) {
      throw StateError(
        'Model output tensor does not match its verified class and mask shapes.',
      );
    }

    final candidates = <_Candidate>[];
    for (var anchor = 0; anchor < anchors; anchor++) {
      var classId = -1;
      var score = 0.0;
      for (var c = 0; c < classCount; c++) {
        final value = dense[(4 + c) * anchors + anchor].toDouble();
        if (value > score) {
          score = value;
          classId = c;
        }
      }
      if (classId < 0 || score < (thresholds[labels[classId]] ?? 1)) continue;

      final cx = dense[anchor].toDouble() * transform.targetSize;
      final cy = dense[anchors + anchor].toDouble() * transform.targetSize;
      final width =
          dense[2 * anchors + anchor].toDouble() * transform.targetSize;
      final height =
          dense[3 * anchors + anchor].toDouble() * transform.targetSize;
      final left = (transform.sourceX(cx - width / 2) / transform.sourceWidth)
          .clamp(0.0, 1.0)
          .toDouble();
      final top = (transform.sourceY(cy - height / 2) / transform.sourceHeight)
          .clamp(0.0, 1.0)
          .toDouble();
      final right = (transform.sourceX(cx + width / 2) / transform.sourceWidth)
          .clamp(0.0, 1.0)
          .toDouble();
      final bottom =
          (transform.sourceY(cy + height / 2) / transform.sourceHeight)
              .clamp(0.0, 1.0)
              .toDouble();
      final box = NormalizedBox(left, top, right, bottom);
      if (!box.isValid) continue;
      final coefficients = prototypes == null
          ? null
          : List<double>.generate(
              maskChannels,
              (i) => dense[(4 + classCount + i) * anchors + anchor].toDouble(),
              growable: false,
            );
      candidates.add(_Candidate(classId, score, box, coefficients));
    }
    candidates.sort((a, b) => b.score.compareTo(a.score));

    final kept = <_Candidate>[];
    for (final candidate in candidates) {
      if (kept.any(
        (other) =>
            other.classId == candidate.classId &&
            _iou(other.box, candidate.box) > iouThreshold,
      )) {
        continue;
      }
      kept.add(candidate);
      if (kept.length >= maxDetections) break;
    }
    return kept
        .map(
          (candidate) => Component2Detection(
            task: task,
            label: labels[candidate.classId],
            confidence: candidate.score,
            box: candidate.box,
            mask: prototypes == null
                ? null
                : _makeMask(
                    prototypes,
                    prototypeWidth,
                    prototypeHeight,
                    prototypeChannels,
                    candidate.coefficients!,
                    candidate.box,
                    transform,
                  ),
          ),
        )
        .toList(growable: false);
  }

  DetectionMask _makeMask(
    Float32List prototypes,
    int protoWidth,
    int protoHeight,
    int protoChannels,
    List<double> coefficients,
    NormalizedBox box,
    LetterboxTransform transform,
  ) {
    const side = 32;
    final values = Float32List(side * side);
    for (var y = 0; y < side; y++) {
      final v = (y + 0.5) / side;
      final sourceY =
          (box.top + (box.bottom - box.top) * v) * transform.sourceHeight;
      final modelY =
          sourceY * transform.resizedHeight / transform.sourceHeight +
          transform.padTop;
      final py = modelY * protoHeight / transform.targetSize - 0.5;
      for (var x = 0; x < side; x++) {
        final u = (x + 0.5) / side;
        final sourceX =
            (box.left + (box.right - box.left) * u) * transform.sourceWidth;
        final modelX =
            sourceX * transform.resizedWidth / transform.sourceWidth +
            transform.padLeft;
        final px = modelX * protoWidth / transform.targetSize - 0.5;
        var logit = 0.0;
        for (var channel = 0; channel < protoChannels; channel++) {
          logit +=
              coefficients[channel] *
              _sampleProto(
                prototypes,
                protoWidth,
                protoHeight,
                protoChannels,
                px,
                py,
                channel,
              );
        }
        final clamped = logit.clamp(-80.0, 80.0);
        values[y * side + x] = 1 / (1 + math.exp(-clamped));
      }
    }
    return DetectionMask(width: side, height: side, values: values);
  }

  double _sampleProto(
    Float32List proto,
    int width,
    int height,
    int channels,
    double x,
    double y,
    int channel,
  ) {
    final boundedX = x.clamp(0.0, width - 1.0).toDouble();
    final boundedY = y.clamp(0.0, height - 1.0).toDouble();
    final x0 = boundedX.floor();
    final y0 = boundedY.floor();
    final x1 = (x0 + 1).clamp(0, width - 1).toInt();
    final y1 = (y0 + 1).clamp(0, height - 1).toInt();
    final dx = boundedX - x0;
    final dy = boundedY - y0;
    final a =
        proto[(y0 * width + x0) * channels + channel] * (1 - dx) +
        proto[(y0 * width + x1) * channels + channel] * dx;
    final b =
        proto[(y1 * width + x0) * channels + channel] * (1 - dx) +
        proto[(y1 * width + x1) * channels + channel] * dx;
    return a * (1 - dy) + b * dy;
  }

  double _iou(NormalizedBox a, NormalizedBox b) {
    final width = math.max(
      0.0,
      math.min(a.right, b.right) - math.max(a.left, b.left),
    );
    final height = math.max(
      0.0,
      math.min(a.bottom, b.bottom) - math.max(a.top, b.top),
    );
    final intersection = width * height;
    final union =
        (a.right - a.left) * (a.bottom - a.top) +
        (b.right - b.left) * (b.bottom - b.top) -
        intersection;
    return union <= 0 ? 0 : intersection / union;
  }
}

class _Candidate {
  const _Candidate(this.classId, this.score, this.box, this.coefficients);
  final int classId;
  final double score;
  final NormalizedBox box;
  final List<double>? coefficients;
}
