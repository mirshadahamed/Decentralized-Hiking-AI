import 'dart:math' as math;

class MotionPdrTracker {
  MotionPdrTracker({
    this.stepLengthMeters = 0.7,
    this.gravityTimeConstantSeconds = 0.25,
    this.minimumPeakAcceleration = 3.0,
    this.troughAcceleration = 1.0,
    this.minimumStepInterval = const Duration(milliseconds: 300),
    this.maximumStepInterval = const Duration(milliseconds: 1200),
  }) {
    if (!stepLengthMeters.isFinite || stepLengthMeters <= 0) {
      throw ArgumentError.value(
        stepLengthMeters,
        'stepLengthMeters',
        'Must be finite and greater than zero.',
      );
    }
    if (!gravityTimeConstantSeconds.isFinite ||
        gravityTimeConstantSeconds <= 0) {
      throw ArgumentError.value(
        gravityTimeConstantSeconds,
        'gravityTimeConstantSeconds',
        'Must be finite and greater than zero.',
      );
    }
    if (!minimumPeakAcceleration.isFinite || minimumPeakAcceleration <= 0) {
      throw ArgumentError.value(
        minimumPeakAcceleration,
        'minimumPeakAcceleration',
        'Must be finite and greater than zero.',
      );
    }
    if (!troughAcceleration.isFinite ||
        troughAcceleration < 0 ||
        troughAcceleration >= minimumPeakAcceleration) {
      throw ArgumentError.value(
        troughAcceleration,
        'troughAcceleration',
        'Must be finite, non-negative, and lower than the peak threshold.',
      );
    }
    if (minimumStepInterval.isNegative ||
        maximumStepInterval <= minimumStepInterval) {
      throw ArgumentError(
        'Cadence bounds must be non-negative and maximum must exceed minimum.',
      );
    }
  }

  final double stepLengthMeters;
  final double gravityTimeConstantSeconds;
  final double minimumPeakAcceleration;
  final double troughAcceleration;
  final Duration minimumStepInterval;
  final Duration maximumStepInterval;

  double? _gravityX, _gravityY, _gravityZ;
  double _headingRad = 0;
  double _positionX = 0, _positionY = 0;
  int _stepCount = 0;
  double _speedMps = 0;
  bool _peakArmed = true;
  double _candidatePeakMagnitude = 0;
  DateTime? _candidatePeakAt;
  double _candidatePeakHeading = 0;
  DateTime? _lastSampleAt;
  DateTime? _lastStepAt;
  DateTime? _lastCadencePeakAt;

  MotionPdrSnapshot update({
    required DateTime timestamp,
    required double accelerometerX,
    required double accelerometerY,
    required double accelerometerZ,
    required double gyroscopeZ,
  }) {
    if (!accelerometerX.isFinite ||
        !accelerometerY.isFinite ||
        !accelerometerZ.isFinite ||
        !gyroscopeZ.isFinite) {
      throw ArgumentError('IMU readings must be finite.');
    }

    final previousSampleAt = _lastSampleAt;
    final elapsedSeconds = previousSampleAt == null
        ? 1 / 50
        : timestamp.difference(previousSampleAt).inMicroseconds / 1000000;
    _lastSampleAt = timestamp;

    if (elapsedSeconds > 0) {
      _headingRad += gyroscopeZ * elapsedSeconds;
    }

    final alpha = elapsedSeconds <= 0
        ? 0
        : elapsedSeconds / (gravityTimeConstantSeconds + elapsedSeconds);
    _gravityX ??= accelerometerX;
    _gravityY ??= accelerometerY;
    _gravityZ ??= accelerometerZ;
    _gravityX = _gravityX! + alpha * (accelerometerX - _gravityX!);
    _gravityY = _gravityY! + alpha * (accelerometerY - _gravityY!);
    _gravityZ = _gravityZ! + alpha * (accelerometerZ - _gravityZ!);

    final linearX = accelerometerX - _gravityX!;
    final linearY = accelerometerY - _gravityY!;
    final linearZ = accelerometerZ - _gravityZ!;
    final linearAccelerationMagnitude = math.sqrt(
      linearX * linearX + linearY * linearY + linearZ * linearZ,
    );
    var stepDetected = false;
    if (_peakArmed && linearAccelerationMagnitude >= minimumPeakAcceleration) {
      _peakArmed = false;
      _candidatePeakMagnitude = linearAccelerationMagnitude;
      _candidatePeakAt = timestamp;
      _candidatePeakHeading = _headingRad;
    } else if (!_peakArmed) {
      if (linearAccelerationMagnitude > _candidatePeakMagnitude) {
        _candidatePeakMagnitude = linearAccelerationMagnitude;
        _candidatePeakAt = timestamp;
        _candidatePeakHeading = _headingRad;
      }

      if (linearAccelerationMagnitude < troughAcceleration) {
        stepDetected = _completePeak();
        _peakArmed = true;
      }
    }

    final lastStepAt = _lastStepAt;
    if (lastStepAt == null || timestamp.difference(lastStepAt).inSeconds >= 2) {
      _speedMps = 0;
    }

    return MotionPdrSnapshot(
      gravityX: _gravityX!,
      gravityY: _gravityY!,
      gravityZ: _gravityZ!,
      linearAccelerationX: linearX,
      linearAccelerationY: linearY,
      linearAccelerationZ: linearZ,
      linearAccelerationMagnitude: linearAccelerationMagnitude,
      stepThreshold: minimumPeakAcceleration,
      stepDetected: stepDetected,
      stepCount: _stepCount,
      speedMps: _speedMps,
      headingRad: _headingRad,
      positionX: _positionX,
      positionY: _positionY,
    );
  }

  bool _completePeak() {
    final peakAt = _candidatePeakAt;
    if (peakAt == null) return false;

    final previousPeakAt = _lastCadencePeakAt;
    if (previousPeakAt == null) {
      _lastCadencePeakAt = peakAt;
      return false;
    }

    final interval = peakAt.difference(previousPeakAt);
    if (interval > maximumStepInterval) {
      _lastCadencePeakAt = peakAt;
      return false;
    }
    if (interval < minimumStepInterval) {
      _lastCadencePeakAt = null;
      return false;
    }

    _lastCadencePeakAt = peakAt;
    _recordStep(peakAt, _candidatePeakHeading);
    return true;
  }

  void _recordStep(DateTime timestamp, double headingRad) {
    final previousStepAt = _lastStepAt;
    _lastStepAt = timestamp;
    if (previousStepAt != null) {
      final intervalSeconds =
          timestamp.difference(previousStepAt).inMicroseconds / 1000000;
      if (intervalSeconds > 0) {
        _speedMps = stepLengthMeters / intervalSeconds;
      }
    }

    _stepCount++;
    _positionX += stepLengthMeters * math.cos(headingRad);
    _positionY += stepLengthMeters * math.sin(headingRad);
  }
}

class MotionPdrSnapshot {
  const MotionPdrSnapshot({
    required this.gravityX,
    required this.gravityY,
    required this.gravityZ,
    required this.linearAccelerationX,
    required this.linearAccelerationY,
    required this.linearAccelerationZ,
    required this.linearAccelerationMagnitude,
    required this.stepThreshold,
    required this.stepDetected,
    required this.stepCount,
    required this.speedMps,
    required this.headingRad,
    required this.positionX,
    required this.positionY,
  });

  final double gravityX;
  final double gravityY;
  final double gravityZ;
  final double linearAccelerationX;
  final double linearAccelerationY;
  final double linearAccelerationZ;
  final double linearAccelerationMagnitude;
  final double stepThreshold;
  final bool stepDetected;
  final int stepCount;
  final double speedMps;
  final double headingRad;
  final double positionX;
  final double positionY;
}
