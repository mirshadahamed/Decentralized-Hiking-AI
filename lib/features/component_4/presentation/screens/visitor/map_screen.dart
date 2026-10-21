import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../../../models/models.dart';
import '../../theme/c4_theme.dart';
import '../../widgets/c4_ui.dart';
import '../bottleneck_screen.dart';

/// Trails of the selected park on an OpenStreetMap background, one colour per route, with the trail heads,
/// halfway checkpoints and the summit / viewpoints marked.
class MapScreen extends StatefulWidget {
  const MapScreen({super.key, this.showTiles = true});

  final bool showTiles; // false in tests (no network)

  @override
  State<MapScreen> createState() => _MapScreenState();
}

const _routeColors = [Color(0xFF1B5E20), Color(0xFF1565C0), Color(0xFF6A1B9A), Color(0xFFE65100), Color(0xFF00838F)];

class _MapScreenState extends State<MapScreen> {
  late Future<(List<MapSegment>, List<TrailInfo>)> _future;

  Future<(List<MapSegment>, List<TrailInfo>)> _load() async {
    final api = C4Scope.of(context);
    final r = await Future.wait([api.geometry(), api.trails()]);
    return (r[0] as List<MapSegment>, r[1] as List<TrailInfo>);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = _load();
  }

  static LatLng _ll(List<double> p) => LatLng(p[1], p[0]);

  Marker _marker(MapSegment s, IconData icon, Color color, String tip) {
    final mid = s.points[s.points.length ~/ 2];
    return Marker(
      point: _ll(mid),
      width: 34,
      height: 34,
      child: Tooltip(
        message: tip,
        child: DecoratedBox(
          decoration: BoxDecoration(color: Colors.white, shape: BoxShape.circle, border: Border.all(color: color, width: 2)),
          child: Icon(icon, size: 20, color: color),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<(List<MapSegment>, List<TrailInfo>)>(
        future: _future,
        builder: (context, snap) {
          if (snap.hasError) return ErrorRetry(error: snap.error!, onRetry: () => setState(() { _future = _load(); }));
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final (segs, trails) = snap.data!;
          if (segs.isEmpty) return const Center(child: Text('No trail geometry'));
          final ids = [for (final t in trails) t.id];
          final names = {for (final t in trails) t.id: t.name};
          Color colorOf(String trail) => _routeColors[(ids.indexOf(trail) % _routeColors.length).clamp(0, _routeColors.length - 1)];
          final markers = <Marker>[];
          for (final s in segs.where((s) => s.poi.isNotEmpty)) {
            final c = colorOf(s.trail);
            if (s.poi == 'summit') {
              markers.add(_marker(s, Icons.flag, Colors.red.shade700, 'Summit'));
            } else if (s.poi.startsWith('half_')) {
              markers.add(_marker(s, Icons.local_police_outlined, c, 'Halfway check · ${names[s.poi.substring(5)] ?? ''}'));
            } else if (s.poi.startsWith('head_')) {
              markers.add(_marker(s, Icons.directions_walk, c, 'Start · ${names[s.poi.substring(5)] ?? ''}'));
            } else {
              markers.add(_marker(s, Icons.landscape_outlined, c, s.poi.replaceAll('_', ' ')));
            }
          }
          final all = [for (final s in segs) for (final p in s.points) _ll(p)];
          return Column(children: [
            Expanded(
              child: FlutterMap(
                options: MapOptions(
                  initialCameraFit: CameraFit.bounds(bounds: LatLngBounds.fromPoints(all), padding: const EdgeInsets.all(32)),
                ),
                children: [
                  if (widget.showTiles)
                    TileLayer(
                      urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                      userAgentPackageName: 'lk.sliit.decentralized_hiking_ai',
                    ),
                  PolylineLayer(polylines: [
                    for (final s in segs)
                      Polyline(
                        points: [for (final p in s.points) _ll(p)],
                        color: colorOf(s.trail),
                        strokeWidth: 4,
                        pattern: s.poi == 'summit' ? StrokePattern.dashed(segments: const [8, 6]) : const StrokePattern.solid(),
                      ),
                  ]),
                  MarkerLayer(markers: markers),
                  if (widget.showTiles) const SimpleAttributionWidget(source: Text('OpenStreetMap contributors')),
                  Align(
                    alignment: Alignment.topRight,
                    child: Padding(
                      padding: const EdgeInsets.all(C4Space.m),
                      child: FilledButton.icon(
                        onPressed: () => Navigator.of(context)
                            .push(c4Route(context, BottleneckScreen(showTiles: widget.showTiles))),
                        icon: const Icon(Icons.groups_outlined),
                        label: const Text('Crowding this week'),
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: C4Space.page,
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Wrap(spacing: C4Space.m, runSpacing: C4Space.xs, children: [
                  for (final t in trails)
                    Row(mainAxisSize: MainAxisSize.min, children: [
                      Container(width: 18, height: 4, color: colorOf(t.id)),
                      const SizedBox(width: C4Space.xs),
                      Text('${t.name} · ${t.lengthKm} km'),
                    ]),
                ]),
                BasisNote(tr(context, 'map_basis')),
              ]),
            ),
          ]);
        },
      );
}
