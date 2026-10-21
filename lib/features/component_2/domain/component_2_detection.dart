import 'dart:typed_data';

enum DetectionTask { litter, obstacle }

class NormalizedBox {
  const NormalizedBox(this.left, this.top, this.right, this.bottom)
      : assert(left >= 0 && top >= 0 && right <= 1 && bottom <= 1),
        assert(left < right && top < bottom);

  final double left;
  final double top;
  final double right;
  final double bottom;

  bool get isValid => left >= 0 && top >= 0 && right <= 1 && bottom <= 1 && left < right && top < bottom;
}

/// A low-resolution, box-cropped mask. Values are row-major probabilities in
/// the detection box's normalized coordinate frame.
class DetectionMask {
  const DetectionMask({required this.width, required this.height, required this.values})
      : assert(width > 0 && height > 0),
        assert(values.length == width * height);

  final int width;
  final int height;
  final Float32List values;
}

class Component2Detection {
  const Component2Detection({
    required this.task,
    required this.label,
    required this.confidence,
    required this.box,
    this.mask,
  })  : assert(confidence >= 0 && confidence <= 1),
        assert((task == DetectionTask.litter && label == 'litter') ||
            (task == DetectionTask.obstacle && (label == 'rock_region' || label == 'log_region')));

  final DetectionTask task;
  final String label;
  final double confidence;
  final NormalizedBox box;
  final DetectionMask? mask;
}

class Component2PhotoResult {
  const Component2PhotoResult({
    required this.detections,
    required this.imageWidth,
    required this.imageHeight,
    required this.inferenceDuration,
    required this.modelVersion,
    required this.modelQualityAccepted,
    this.trailCondition = 'not_assessed',
  })  : assert(imageWidth > 0 && imageHeight > 0),
        assert(inferenceDuration >= Duration.zero),
        assert(modelVersion != ''),
        assert(trailCondition == 'not_assessed');

  final List<Component2Detection> detections;
  final int imageWidth;
  final int imageHeight;
  final Duration inferenceDuration;
  final String modelVersion;
  final bool modelQualityAccepted;
  final String trailCondition;

  List<Component2Detection> get litterDetections =>
      detections.where((d) => d.task == DetectionTask.litter).toList(growable: false);
  List<Component2Detection> get rockDetections =>
      detections.where((d) => d.label == 'rock_region').toList(growable: false);
  List<Component2Detection> get logDetections =>
      detections.where((d) => d.label == 'log_region').toList(growable: false);
}
