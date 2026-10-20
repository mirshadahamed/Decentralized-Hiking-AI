import 'dart:async';
import 'package:sensors_plus/sensors_plus.dart';

class SensorDataSource {
  SensorDataSource();

  static const int sampleRateHz = 50;
  static const int windowSize = 128;
  static const Duration _samplePeriod = Duration(milliseconds: 20);

  final List<List<double>> _samples = <List<double>>[];
  final List<Completer<List<List<double>>>> _waitingForWindow = <Completer<List<List<double>>>>[];

  StreamSubscription<AccelerometerEvent>? _accelerometerSubscription;
  StreamSubscription<GyroscopeEvent>? _gyroscopeSubscription;
  Timer? _samplingTimer;

  double? _accelerometerX, _accelerometerY, _accelerometerZ;
  double? _gyroscopeX, _gyroscopeY, _gyroscopeZ;

  Object? _sensorError;
  StackTrace? _sensorStackTrace;
  bool _started = false, _disposed = false;

  Future<List<List<double>>> getLatestSensorWindow() {
    if (_disposed) return Future.error(StateError('Disposed.'));
    if (_sensorError != null) return Future.error(_sensorError!, _sensorStackTrace);

    _start();
    if (_samples.length == windowSize) return Future.value(_copyWindow());

    final completer = Completer<List<List<double>>>();
    _waitingForWindow.add(completer);
    return completer.future;
  }

  void _start() {
    if (_started) return;
    _started = true;
    _accelerometerSubscription = accelerometerEvents.listen(
      (event) { _accelerometerX = event.x; _accelerometerY = event.y; _accelerometerZ = event.z; },
      onError: _handleSensorError,
    );
    _gyroscopeSubscription = gyroscopeEvents.listen(
      (event) { _gyroscopeX = event.x; _gyroscopeY = event.y; _gyroscopeZ = event.z; },
      onError: _handleSensorError,
    );
    _samplingTimer = Timer.periodic(_samplePeriod, (_) => _sampleLatest());
  }

  void _sampleLatest() {
    if (_disposed || _accelerometerX == null || _gyroscopeX == null) return;
    _samples.add([_accelerometerX!, _accelerometerY!, _accelerometerZ!, _gyroscopeX!, _gyroscopeY!, _gyroscopeZ!]);
    if (_samples.length > windowSize) _samples.removeAt(0);

    if (_samples.length == windowSize && _waitingForWindow.isNotEmpty) {
      final window = _copyWindow();
      final waiting = List<Completer<List<List<double>>>>.from(_waitingForWindow);
      _waitingForWindow.clear();
      for (final c in waiting) { if (!c.isCompleted) c.complete(window); }
    }
  }

  List<List<double>> _copyWindow() => _samples.map((s) => List<double>.unmodifiable(s)).toList();

  void _handleSensorError(Object error, [StackTrace? stackTrace]) {
    _sensorError = error;
    _sensorStackTrace = stackTrace;
    final waiting = List<Completer<List<List<double>>>>.from(_waitingForWindow);
    _waitingForWindow.clear();
    for (final c in waiting) { if (!c.isCompleted) c.completeError(error, stackTrace); }
  }

  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    _samplingTimer?.cancel();
    await _accelerometerSubscription?.cancel();
    await _gyroscopeSubscription?.cancel();
    for (final c in _waitingForWindow) {
      if (!c.isCompleted) c.completeError(StateError('Disposed before window ready.'));
    }
    _waitingForWindow.clear();
  }
}
