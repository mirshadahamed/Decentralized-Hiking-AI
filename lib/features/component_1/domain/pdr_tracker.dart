import 'dart:math';

class PdrTracker {
  const PdrTracker({
    required this.lastX,
    required this.lastY,
    required this.lastHeadingRad,
    required this.stepLengthM,
  });

  final double lastX;
  final double lastY;
  final double lastHeadingRad;
  final double stepLengthM;

  PdrPosition updatePosition() {
    final newX = lastX + stepLengthM * cos(lastHeadingRad);
    final newY = lastY + stepLengthM * sin(lastHeadingRad);
    return PdrPosition(x: newX, y: newY, headingRad: lastHeadingRad);
  }
}

class PdrPosition {
  const PdrPosition({required this.x, required this.y, required this.headingRad});
  final double x;
  final double y;
  final double headingRad;
}
