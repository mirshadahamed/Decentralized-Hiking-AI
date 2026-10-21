/// Sensor and step-tracking values consumed by the terrain assessment flow.
class Component1TerrainSensorData {
  const Component1TerrainSensorData({
    required this.speedMps,
    required this.slopePercent,
    required this.lastX,
    required this.lastY,
    required this.headingRad,
    this.stepCount = 0,
    this.accelerometerX = 0,
    this.accelerometerY = 0,
    this.accelerometerZ = 0,
    this.gyroscopeX = 0,
    this.gyroscopeY = 0,
    this.gyroscopeZ = 0,
  });

  final double speedMps;
  final double slopePercent;
  final double lastX;
  final double lastY;
  final double headingRad;
  final int stepCount;
  final double accelerometerX;
  final double accelerometerY;
  final double accelerometerZ;
  final double gyroscopeX;
  final double gyroscopeY;
  final double gyroscopeZ;
}
