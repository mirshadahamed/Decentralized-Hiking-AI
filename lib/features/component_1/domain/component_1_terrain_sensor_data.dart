/// Sensor and step-tracking values consumed by the terrain assessment flow.
class Component1TerrainSensorData {
  const Component1TerrainSensorData({
    required this.speedMps,
    required this.slopePercent,
    required this.lastX,
    required this.lastY,
    required this.headingRad,
    required this.stepLengthMeters,
  });

  final double speedMps;
  final double slopePercent;
  final double lastX;
  final double lastY;
  final double headingRad;
  final double stepLengthMeters;
}