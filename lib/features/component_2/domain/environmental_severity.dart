import 'component_2_detection.dart';

enum ObservationLevel { low, moderate, high }

extension ObservationLevelPresentation on ObservationLevel {
  String get label => switch (this) {
    ObservationLevel.low => 'Low',
    ObservationLevel.moderate => 'Moderate',
    ObservationLevel.high => 'High',
  };

  int get rank => switch (this) {
    ObservationLevel.low => 0,
    ObservationLevel.moderate => 1,
    ObservationLevel.high => 2,
  };
}

/// Temporary PP1 observation heuristic derived only from current detections.
/// These values are development thresholds and do not assess route safety.
class EnvironmentalSeverity {
  const EnvironmentalSeverity({
    required this.litterAreaRatio,
    required this.obstacleAreaRatio,
    required this.litterCount,
    required this.obstacleCount,
    required this.litterLevel,
    required this.obstacleLevel,
    required this.overallLevel,
  });

  factory EnvironmentalSeverity.fromResult(Component2PhotoResult result) {
    final litter = result.litterDetections;
    final obstacles = result.detections
        .where((detection) => detection.task == DetectionTask.obstacle)
        .toList(growable: false);
    final litterAreaRatio = _litterMaskAreaRatio(
      litter,
      result.imageWidth,
      result.imageHeight,
    );
    final obstacleAreaRatio = _boxAreaRatio(obstacles);
    final litterLevel = _litterLevel(litter.length, litterAreaRatio);
    final obstacleLevel = _obstacleLevel(obstacleAreaRatio);
    final overallLevel = litterLevel.rank >= obstacleLevel.rank
        ? litterLevel
        : obstacleLevel;

    return EnvironmentalSeverity(
      litterAreaRatio: litterAreaRatio,
      obstacleAreaRatio: obstacleAreaRatio,
      litterCount: litter.length,
      obstacleCount: obstacles.length,
      litterLevel: litterLevel,
      obstacleLevel: obstacleLevel,
      overallLevel: overallLevel,
    );
  }

  final double litterAreaRatio;
  final double obstacleAreaRatio;
  final int litterCount;
  final int obstacleCount;
  final ObservationLevel litterLevel;
  final ObservationLevel obstacleLevel;
  final ObservationLevel overallLevel;

  String get overallLabel => switch (overallLevel) {
    ObservationLevel.low => 'Normal observation',
    ObservationLevel.moderate => 'Attention recommended',
    ObservationLevel.high => 'High environmental concern',
  };
}

ObservationLevel _litterLevel(int count, double areaRatio) {
  if (count >= 5 || areaRatio >= 0.08) return ObservationLevel.high;
  if ((count >= 2 && count <= 4) || areaRatio >= 0.02) {
    return ObservationLevel.moderate;
  }
  return ObservationLevel.low;
}

ObservationLevel _obstacleLevel(double areaRatio) {
  if (areaRatio >= 0.15) return ObservationLevel.high;
  if (areaRatio >= 0.05) return ObservationLevel.moderate;
  return ObservationLevel.low;
}

/// Estimates source-image pixels covered by predicted litter masks. Masks are
/// box-cropped, so each positive cell contributes its mapped source-image area.
double _litterMaskAreaRatio(
  List<Component2Detection> detections,
  int imageWidth,
  int imageHeight,
) {
  var totalMaskPixels = 0.0;
  for (final detection in detections) {
    final mask = detection.mask;
    if (mask == null) continue;
    final positiveMaskPixels = mask.values
        .where((value) => value >= 0.5)
        .length;
    final sourcePixelsPerMaskCell =
        (detection.box.right - detection.box.left) *
        imageWidth /
        mask.width *
        (detection.box.bottom - detection.box.top) *
        imageHeight /
        mask.height;
    totalMaskPixels += positiveMaskPixels * sourcePixelsPerMaskCell;
  }
  final imagePixels = imageWidth * imageHeight;
  return (totalMaskPixels / imagePixels).clamp(0.0, 1.0);
}

double _boxAreaRatio(List<Component2Detection> detections) {
  final area = detections.fold<double>(
    0,
    (sum, detection) =>
        sum +
        (detection.box.right - detection.box.left) *
            (detection.box.bottom - detection.box.top),
  );
  return area.clamp(0.0, 1.0);
}
