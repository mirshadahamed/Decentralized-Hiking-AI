import 'component_1_terrain_service.dart';

enum Component1TerrainStatus { initial, loading, success, failure }

/// Immutable result state for a component 1 terrain assessment.
class Component1TerrainState {
  const Component1TerrainState._({
    required this.status,
    this.snapshot,
    this.error,
  });

  const Component1TerrainState.initial()
      : this._(status: Component1TerrainStatus.initial);

  const Component1TerrainState.loading()
      : this._(status: Component1TerrainStatus.loading);

  const Component1TerrainState.success(TerrainAssessmentSnapshot snapshot)
      : this._(status: Component1TerrainStatus.success, snapshot: snapshot);

  const Component1TerrainState.failure(Object error)
      : this._(status: Component1TerrainStatus.failure, error: error);

  final Component1TerrainStatus status;
  final TerrainAssessmentSnapshot? snapshot;
  final Object? error;

  bool get isLoading => status == Component1TerrainStatus.loading;
  bool get hasResult => status == Component1TerrainStatus.success;
  bool get hasError => status == Component1TerrainStatus.failure;
}