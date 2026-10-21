import 'dart:async';
import 'dart:math' as math;

import 'package:sensors_plus/sensors_plus.dart';

import '../../domain/motion_pdr_tracker.dart';

class SensorDataSource {
  SensorDataSource();

  static const int sampleRateHz = 50;
  static const int windowSize = 128;

  final MotionPdrTracker _motionTracker = MotionPdrTracker(
    stepLengthMeters: 0.7,
    gravityTimeConstantSeconds: 0.25,
    minimumPeakAcceleration: 3.0,
    troughAcceleration: 1.0,
    minimumStepInterval: Duration(milliseconds: 300),
    maximumStepInterval: Duration(milliseconds: 1200),
  );
  final List<List<double>> _samples = <List<double>>[];
  final List<Completer<List<List<double>>>> _waitingForWindow =
      <Completer<List<List<double>>>>[];

  StreamSubscription<AccelerometerEvent>? _accelerometerSubscription;
  StreamSubscription<GyroscopeEvent>? _gyroscopeSubscription;
  Timer? _samplingTimer;

  double? _accelerometerX, _accelerometerY, _accelerometerZ;
  double _gyroscopeX = 0, _gyroscopeY = 0, _gyroscopeZ = 0;
  double _slopePercent = 0;
  MotionPdrSnapshot? _motionSnapshot;

  Object? _sensorError;
  StackTrace? _sensorStackTrace;
  bool _started = false, _disposed = false;

  Future<List<List<double>>> getLatestSensorWindow() {
    if (_disposed) return Future.error(StateError('Disposed.'));
    if (_sensorError != null) {
      return Future.error(_sensorError!, _sensorStackTrace);
    }

    _start();
    if (_samples.isNotEmpty) return Future.value(_paddedWindow());

    final completer = Completer<List<List<double>>>();
    _waitingForWindow.add(completer);
    return completer.future;
  }

  Future<Map<String, double>> getCurrentPdrMetrics() async {
    await getLatestSensorWindow();
    final motion = _motionSnapshot;
    if (motion == null) {
      throw StateError('Motion data is unavailable before the first sample.');
    }
    return {
      'speedMps': motion.speedMps,
      'slopePercent': _slopePercent,
      'lastX': motion.positionX,
      'lastY': motion.positionY,
      'headingRad': motion.headingRad,
      'stepLengthMeters': _motionTracker.stepLengthMeters,
      'stepCount': motion.stepCount.toDouble(),
      'accelerometerX': _accelerometerX!,
      'accelerometerY': _accelerometerY!,
      'accelerometerZ': _accelerometerZ!,
      'gyroscopeX': _gyroscopeX,
      'gyroscopeY': _gyroscopeY,
      'gyroscopeZ': _gyroscopeZ,
    };
  }

  void _start() {
    if (_started) return;
    _started = true;
    _accelerometerSubscription = accelerometerEventStream().listen((event) {
      _accelerometerX = event.x;
      _accelerometerY = event.y;
      _accelerometerZ = event.z;
    }, onError: _handleSensorError);
    _gyroscopeSubscription = gyroscopeEventStream().listen((event) {
      _gyroscopeX = event.x;
      _gyroscopeY = event.y;
      _gyroscopeZ = event.z;
    }, onError: _handleSensorError);
    _samplingTimer = Timer.periodic(
      Duration(microseconds: 1000000 ~/ sampleRateHz),
      (_) => _sampleLatest(),
    );
  }

  void _sampleLatest() {
    if (_disposed || _accelerometerX == null) return;

    final now = DateTime.now();
    final motion = _motionTracker.update(
      timestamp: now,
      accelerometerX: _accelerometerX!,
      accelerometerY: _accelerometerY!,
      accelerometerZ: _accelerometerZ!,
      gyroscopeZ: _gyroscopeZ,
    );
    _motionSnapshot = motion;
    _slopePercent =
        100 *
        motion.gravityX /
        math.max(
          0.001,
          math.sqrt(
            motion.gravityY * motion.gravityY +
                motion.gravityZ * motion.gravityZ,
          ),
        );

    _samples.add([
      _accelerometerX!,
      _accelerometerY!,
      _accelerometerZ!,
      _gyroscopeX,
      _gyroscopeY,
      _gyroscopeZ,
    ]);
    if (_samples.length > windowSize) _samples.removeAt(0);

    if (_waitingForWindow.isNotEmpty) {
      final window = _paddedWindow();
      final waiting = List<Completer<List<List<double>>>>.from(
        _waitingForWindow,
      );
      _waitingForWindow.clear();
      for (final c in waiting) {
        if (!c.isCompleted) c.complete(window);
      }
    }
  }

  List<List<double>> _paddedWindow() {
    final firstSample = _samples.first;
    final padding = List<List<double>>.generate(
      windowSize - _samples.length,
      (_) => List<double>.of(firstSample),
    );
    return [...padding, ..._samples.map(List<double>.of)];
  }

  void _handleSensorError(Object error, [StackTrace? stackTrace]) {
    _sensorError = error;
    _sensorStackTrace = stackTrace;
    final waiting = List<Completer<List<List<double>>>>.from(_waitingForWindow);
    _waitingForWindow.clear();
    for (final c in waiting) {
      if (!c.isCompleted) c.completeError(error, stackTrace);
    }
  }

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    _samplingTimer?.cancel();
    await _accelerometerSubscription?.cancel();
    await _gyroscopeSubscription?.cancel();
    for (final c in _waitingForWindow) {
      if (!c.isCompleted) {
        c.completeError(StateError('Disposed before window ready.'));
      }
    }
    _waitingForWindow.clear();
  }
}
