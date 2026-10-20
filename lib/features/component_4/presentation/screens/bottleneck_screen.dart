import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../../domain/bottleneck.dart';
import '../../models/models.dart';
import '../../services/edge_store.dart';
import '../theme/c4_theme.dart';
import '../widgets/c4_ui.dart';

/// Tomorrow's micro-spatial bottlenecks (proposal FR2-FR4, NFR4): every trail section coloured by how full the
/// ST-GNN expects it to be at the chosen hour, and the Cifuentes safe numbers per section and trail.
/// The forecast is computed on this phone from the daily edge pack, so this also works with no connection.
class BottleneckScreen extends StatelessWidget {
  const BottleneckScreen({super.key, this.showTiles = true});

  final bool showTiles; // false in tests (no network)

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text("Tomorrow's bottlenecks")),
        body: BottleneckView(showTiles: showTiles),
      );
}

/// The two tabs (map, safe numbers) without an app bar, so staff homes can embed them as a tab.
class BottleneckView extends StatefulWidget {
  const BottleneckView({super.key, this.showTiles = true});

  final bool showTiles;

  @override
  State<BottleneckView> createState() => _BottleneckViewState();
}

class _BottleneckViewState extends State<BottleneckView> {
  late Future<BottleneckDay> _future;
  int? _hour;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = _load();
  }

  Future<BottleneckDay> _load() async {
    final api = C4Scope.of(context);
    final loaded = await EdgeStore.load(api); // downloads today's pack, or uses the stored one offline
    if (loaded != null && loaded.$1.pack['map'] is Map) {
      final (model, offline) = loaded;
      return BottleneckDay.fromPack(model.pack, model.forecast(), offline: offline);
    }
    final r = await Future.wait([api.tomorrow(), api.geometry()]); // no pack: the server's own forecast
    final lines = <int, List<List<List<double>>>>{};
    for (final s in r[1] as List<MapSegment>) {
      lines.putIfAbsent(s.id, () => []).add(s.points);
    }
    return BottleneckDay.fromServer(r[0] as Map<String, dynamic>, lines);
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<BottleneckDay>(
        future: _future,
        builder: (context, snap) {
          if (snap.hasError) return ErrorRetry(error: snap.error!, onRetry: () => setState(() => _future = _load()));
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final d = snap.data!;
          final hour = _hour ?? d.worstHour;
          return DefaultTabController(
            length: 2,
            child: Column(children: [
              _SourceBar(day: d),
              const TabBar(tabs: [
                Tab(icon: Icon(Icons.map_outlined), text: 'Bottleneck map'),
                Tab(icon: Icon(Icons.shield_outlined), text: 'Safe numbers'),
              ]),
              Expanded(
                child: TabBarView(physics: const NeverScrollableScrollPhysics(), children: [
                  _MapTab(day: d, hour: hour, onHour: (h) => setState(() => _hour = h), showTiles: widget.showTiles),
                  _CapacityTab(day: d),
                ]),
              ),
            ]),
          );
        },
      );
}

// ---------- shared ----------
const _levelColor = {
  Crowding.quiet: Color(0xFF2E7D32),
  Crowding.filling: Color(0xFFF9A825),
  Crowding.busy: Color(0xFFEF6C00),
  Crowding.over: Color(0xFFC62828),
};
const _levelText = {
  Crowding.quiet: 'quiet',
  Crowding.filling: 'filling up',
  Crowding.busy: 'busy',
  Crowding.over: 'over capacity',
};

String _h(int h) => '${h.toString().padLeft(2, '0')}:00';

String _nice(String iso) {
  final d = DateTime.parse(iso);
  const days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return '${days[d.weekday - 1]} ${d.day} ${months[d.month - 1]}';
}

class _SourceBar extends StatelessWidget {
  const _SourceBar({required this.day});

  final BottleneckDay day;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final phone = day.source == 'phone';
    return Container(
      width: double.infinity,
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      padding: const EdgeInsets.symmetric(horizontal: C4Space.l, vertical: C4Space.s),
      child: Wrap(spacing: C4Space.s, runSpacing: C4Space.xs, crossAxisAlignment: WrapCrossAlignment.center, children: [
        Text(_nice(day.day), style: text.titleSmall),
        Chip(
          avatar: Icon(phone ? Icons.phone_android : Icons.cloud_outlined, size: 16),
          label: Text(phone ? 'ST-GNN on this phone · ${day.millis} ms' : 'Server forecast'),
          visualDensity: VisualDensity.compact,
        ),
        if (day.offline)
          const Chip(
            avatar: Icon(Icons.airplanemode_active, size: 16),
            label: Text('offline copy'),
            visualDensity: VisualDensity.compact,
          ),
      ]),
    );
  }
}

void _showSection(BuildContext context, BottleneckDay d, Section s, int hour) => showModalBottomSheet(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (_) => _SectionSheet(day: d, section: s, hour: hour),
    );

// ---------- map tab ----------
class _MapTab extends StatelessWidget {
  const _MapTab({required this.day, required this.hour, required this.onHour, required this.showTiles});

  final BottleneckDay day;
  final int hour;
  final ValueChanged<int> onHour;
  final bool showTiles;

  static LatLng _ll(List<double> p) => LatLng(p[1], p[0]);

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final ranked = day.rankedAt(hour);
    final top = ranked.where((s) => day.level(s, hour) != Crowding.quiet).take(3).toList();
    final all = [for (final s in day.sections) for (final l in s.lines) for (final p in l) _ll(p)];
    final over = day.sections.where((s) => day.level(s, hour) == Crowding.over);
    final hours = day.openHours;
    return Column(children: [
      Expanded(
        child: all.isEmpty
            ? const Center(child: Text('No trail lines in this forecast'))
            : FlutterMap(
                options: MapOptions(
                  initialCameraFit: CameraFit.bounds(bounds: LatLngBounds.fromPoints(all), padding: const EdgeInsets.all(28)),
                ),
                children: [
                  if (showTiles)
                    TileLayer(
                      urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                      userAgentPackageName: 'lk.sliit.decentralized_hiking_ai',
                    ),
                  PolylineLayer(polylines: [
                    for (final s in [...day.sections]..sort((a, b) => a.utilisation(hour).compareTo(b.utilisation(hour))))
                      for (final l in s.lines)
                        Polyline(
                          points: [for (final p in l) _ll(p)],
                          color: _levelColor[day.level(s, hour)]!,
                          strokeWidth: day.level(s, hour) == Crowding.over ? 8 : 5,
                          borderColor: Colors.white,
                          borderStrokeWidth: 1.5,
                        ),
                  ]),
                  MarkerLayer(markers: [
                    for (final s in over)
                      if (s.lines.isNotEmpty && s.lines.first.isNotEmpty)
                        Marker(
                          point: _ll(s.lines.first[s.lines.first.length ~/ 2]),
                          width: 30,
                          height: 30,
                          alignment: const Alignment(0, -1.6), // above the red line, not on it
                          child: GestureDetector(
                            onTap: () => _showSection(context, day, s, hour),
                            child: const DecoratedBox(
                              decoration: BoxDecoration(color: Colors.white, shape: BoxShape.circle),
                              child: Icon(Icons.warning_rounded, color: Color(0xFFC62828), size: 26),
                            ),
                          ),
                        ),
                  ]),
                  if (showTiles) const SimpleAttributionWidget(source: Text('OpenStreetMap contributors')),
                ],
              ),
      ),
      Material(
        elevation: 4,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(C4Space.l, C4Space.s, C4Space.l, C4Space.s),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
            Row(children: [
              Text(_h(hour), style: text.titleLarge),
              const SizedBox(width: C4Space.m),
              Expanded(
                child: Text(
                  '${day.countAt(hour, Crowding.over)} over capacity · ${day.countAt(hour, Crowding.busy)} busy '
                  'of ${day.sections.length} sections',
                  style: text.bodyMedium,
                ),
              ),
            ]),
            Slider(
              key: const Key('hour_slider'),
              value: hour.toDouble().clamp(hours.first.toDouble(), hours.last.toDouble()),
              min: hours.first.toDouble(),
              max: hours.last.toDouble(),
              divisions: (hours.last - hours.first).clamp(1, 23),
              label: _h(hour),
              onChanged: (v) => onHour(v.round()),
            ),
            Wrap(spacing: C4Space.m, runSpacing: C4Space.xs, children: [
              for (final c in Crowding.values)
                Row(mainAxisSize: MainAxisSize.min, children: [
                  Container(width: 16, height: 5, color: _levelColor[c]),
                  const SizedBox(width: C4Space.xs),
                  Text(_levelText[c]!, style: text.bodySmall),
                ]),
            ]),
            const SizedBox(height: C4Space.xs),
            if (top.isEmpty)
              Text('No section is filling up at ${_h(hour)}.', style: text.bodyMedium)
            else
              for (final s in top)
                InkWell(
                  onTap: () => _showSection(context, day, s, hour),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3),
                    child: Row(children: [
                      Icon(Icons.circle, size: 12, color: _levelColor[day.level(s, hour)]),
                      const SizedBox(width: C4Space.s),
                      Expanded(child: Text(day.nameOf(s), overflow: TextOverflow.ellipsis)),
                      Text('${s.peopleAt(hour).round()} / ${s.capacityAtOnce.round()} people'),
                      const Icon(Icons.chevron_right, size: 18),
                    ]),
                  ),
                ),
          ]),
        ),
      ),
    ]);
  }
}

// ---------- one section ----------
class _SectionSheet extends StatelessWidget {
  const _SectionSheet({required this.day, required this.section, required this.hour});

  final BottleneckDay day;
  final Section section;
  final int hour;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final s = section;
    final hours = day.openHours;
    final peakH = s.peakHourIn(hours);
    final maxY = [s.capacityAtOnce, for (final h in hours) s.peopleAt(h)].reduce((a, b) => a > b ? a : b) * 1.15;
    final trail = day.trails[s.trail];
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(C4Space.l, 0, C4Space.l, C4Space.l),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(day.nameOf(s), style: text.titleLarge),
          Text('${trail?.name ?? s.trail} · ${s.lengthM} m', style: text.bodySmall),
          const SizedBox(height: C4Space.m),
          Text('Expected people on this section, hour by hour (line = what it holds safely)', style: text.bodySmall),
          const SizedBox(height: C4Space.s),
          SizedBox(
            height: 120,
            child: LayoutBuilder(builder: (context, box) {
              final w = box.maxWidth / hours.length;
              final capY = box.maxHeight * (1 - s.capacityAtOnce / maxY);
              return Stack(children: [
                Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  for (final h in hours)
                    Tooltip(
                      message: '${_h(h)}: ${s.peopleAt(h).round()} people',
                      child: Container(
                        width: w - 2,
                        margin: const EdgeInsets.only(right: 2),
                        height: (box.maxHeight * s.peopleAt(h) / maxY).clamp(1, box.maxHeight),
                        color: _levelColor[day.level(s, h)]!.withValues(alpha: h == hour ? 1 : 0.65),
                      ),
                    ),
                ]),
                Positioned(left: 0, right: 0, top: capY, child: Container(height: 2, color: Colors.black87)),
              ]);
            }),
          ),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text(_h(hours.first), style: text.labelSmall),
            Text(_h(hours.last), style: text.labelSmall),
          ]),
          const SizedBox(height: C4Space.m),
          _kv(context, 'Busiest', '${_h(peakH)} · about ${s.peopleAt(peakH).round()} people'),
          _kv(context, 'Holds safely at once', '${s.capacityAtOnce.round()} people (groups of 10, 50 m apart)'),
          _kv(context, 'At ${_h(hour)}', '${s.peopleAt(hour).round()} people · ${_levelText[day.level(s, hour)]}'),
          const Divider(height: C4Space.xl),
          Text('Cifuentes carrying capacity, visits per day', style: text.titleSmall),
          _kv(context, 'Physical (PCC)', '${s.pcc}'),
          _kv(context, 'Real (RCC)', '${s.rcc}  · after weather, terrain, crowding'),
          _kv(context, 'Effective (ECC)', '${s.ecc}  · after management capacity'),
          if (trail != null && trail.limitingSegment == s.id)
            Padding(
              padding: const EdgeInsets.only(top: C4Space.s),
              child: Text('This section sets the safe number for the whole trail.',
                  style: text.bodyMedium?.copyWith(fontWeight: FontWeight.bold)),
            ),
        ]),
      ),
    );
  }
}

Widget _kv(BuildContext context, String k, String v) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(width: 150, child: Text(k, style: Theme.of(context).textTheme.bodySmall)),
        Expanded(child: Text(v)),
      ]),
    );

// ---------- safe numbers tab ----------
class _CapacityTab extends StatelessWidget {
  const _CapacityTab({required this.day});

  final BottleneckDay day;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final bott = day.bottlenecks;
    return ListView(padding: C4Space.page, children: [
      Card(
        child: Padding(
          padding: C4Space.page,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text('Safe number of visitors tomorrow', style: text.titleMedium),
            const SizedBox(height: C4Space.s),
            if (day.recommendedQuota != null)
              Text('${day.recommendedQuota}', key: const Key('park_safe_number'), style: text.displaySmall),
            Text(
              [
                if (day.expectedVisitors != null) 'Expected: about ${day.expectedVisitors}',
                if (day.classicQuota != null) 'Fixed Cifuentes number without the forecast: ${day.classicQuota}',
                if (day.rainShare != null) 'Rain in ${(day.rainShare! * 100).round()} % of open hours',
              ].join(' · '),
              style: text.bodyMedium,
            ),
            const SizedBox(height: C4Space.s),
            Text(
              bott.isEmpty
                  ? 'No section is forecast to go over what it holds safely.'
                  : '${bott.length} section${bott.length == 1 ? '' : 's'} forecast over capacity: '
                      '${bott.take(3).map((b) => '${day.nameOf(b.$1)} at ${_h(b.$2)}').join(', ')}.',
              style: text.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
            ),
          ]),
        ),
      ),
      for (final t in day.trails.values) _TrailCard(day: day, trail: t),
      if (day.disclaimer.isNotEmpty) BasisNote(day.disclaimer),
    ]);
  }
}

class _TrailCard extends StatelessWidget {
  const _TrailCard({required this.day, required this.trail});

  final BottleneckDay day;
  final TrailSummary trail;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final secs = day.sectionsOf(trail.id);
    final over = trail.expected > trail.recommended;
    final limiting = secs.where((s) => s.id == trail.limitingSegment).firstOrNull;
    return Card(
      child: ExpansionTile(
        title: Text(trail.name, style: text.titleMedium),
        subtitle: Text(
          'Safe: ${trail.recommended} a day · expected ${trail.expected}'
          '${limiting != null ? '\nSet by: ${day.nameOf(limiting)}' : ''}',
        ),
        trailing: Icon(over ? Icons.warning_amber_rounded : Icons.check_circle_outline,
            color: over ? const Color(0xFFC62828) : const Color(0xFF2E7D32)),
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: C4Space.l),
            child: Row(children: [
              Expanded(flex: 5, child: Text('Section', style: text.labelSmall)),
              Expanded(flex: 2, child: Text('At once', style: text.labelSmall, textAlign: TextAlign.end)),
              Expanded(flex: 3, child: Text('Busiest', style: text.labelSmall, textAlign: TextAlign.end)),
              Expanded(flex: 2, child: Text('ECC/day', style: text.labelSmall, textAlign: TextAlign.end)),
            ]),
          ),
          for (final s in secs)
            InkWell(
              onTap: () => _showSection(context, day, s, s.peakHourIn(day.openHours)),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: C4Space.l, vertical: 5),
                child: Row(children: [
                  Expanded(
                    flex: 5,
                    child: Row(children: [
                      Icon(Icons.circle, size: 10, color: _levelColor[day.level(s, s.peakHourIn(day.openHours))]),
                      const SizedBox(width: C4Space.xs),
                      Expanded(
                        child: Text(day.nameOf(s, short: true),
                            overflow: TextOverflow.ellipsis,
                            style: s.id == trail.limitingSegment ? const TextStyle(fontWeight: FontWeight.bold) : null),
                      ),
                    ]),
                  ),
                  Expanded(flex: 2, child: Text('${s.capacityAtOnce.round()}', textAlign: TextAlign.end)),
                  Expanded(
                    flex: 3,
                    child: Text('${s.peopleAt(s.peakHourIn(day.openHours)).round()} at ${_h(s.peakHourIn(day.openHours))}',
                        textAlign: TextAlign.end),
                  ),
                  Expanded(flex: 2, child: Text('${s.ecc}', textAlign: TextAlign.end)),
                ]),
              ),
            ),
          const SizedBox(height: C4Space.s),
        ],
      ),
    );
  }
}
