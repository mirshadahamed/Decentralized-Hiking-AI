import 'dart:async';
import 'package:flutter/foundation.dart';
import '../domain/component_1_terrain_service.dart';

/// Adapt the existing use case to this callback when constructing the
/// controller, for example: `loadAssessment: () => useCase.execute(...)`.
typedef LoadTerrainAssessment = Future<TerrainAssessmentSnapshot> Function();

class Component1DashboardController extends ChangeNotifier {
  Component1DashboardController({
    required LoadTerrainAssessment loadAssessment,
    this.refreshInterval = const Duration(seconds: 1),
    this.highExertionThresholdW = 500,
  }) : _loadAssessment = loadAssessment;

  final LoadTerrainAssessment _loadAssessment;
  final Duration refreshInterval;
  final double highExertionThresholdW;

  Timer? _timer;
  bool _isRefreshing = false;
  bool _disposed = false;

  TerrainAssessmentSnapshot? snapshot;
  Object? error;
  bool isLoading = true;

  bool get isHighExertion =>
      snapshot != null &&
      snapshot!.metabolicCostW >= highExertionThresholdW;

  void start() {
    if (_timer != null || _disposed) return;
    unawaited(refresh());
    _timer = Timer.periodic(refreshInterval, (_) => unawaited(refresh()));
  }

  Future<void> refresh() async {
    if (_isRefreshing || _disposed) return;

    _isRefreshing = true;
    try {
      final result = await _loadAssessment();
      if (_disposed) return;
      snapshot = result;
      error = null;
      isLoading = false;
    } catch (exception) {
      if (_disposed) return;
      error = exception;
      isLoading = false;
    } finally {
      _isRefreshing = false;
      if (!_disposed) notifyListeners();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    super.dispose();
  }
}
