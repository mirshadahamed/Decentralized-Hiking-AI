import 'package:flutter/material.dart';

import '../../models/models.dart';
import '../theme/c4_theme.dart';
import '../widgets/c4_ui.dart';
import 'visitor/trip_screen.dart';

/// Trip planner, step 1: choose a destination. Built only from the server's destination list, so a new
/// destination (a new configs/parks/*.yaml) appears here, with its own filter chip, without changing the app.
class DestinationsScreen extends StatefulWidget {
  const DestinationsScreen({super.key, required this.parks, required this.onPick, this.actions = const []});

  final List<ParkInfo> parks;
  final ValueChanged<String> onPick;
  final List<Widget> actions;

  @override
  State<DestinationsScreen> createState() => _DestinationsScreenState();
}

class _DestinationsScreenState extends State<DestinationsScreen> {
  String _query = '';
  String? _kind; // null = all

  bool _matches(ParkInfo p) {
    if (_kind != null && p.kind != _kind) return false;
    final q = _query.trim().toLowerCase();
    if (q.isEmpty) return true;
    return [p.name, p.region, p.summary, ...p.trails.values].any((s) => s.toLowerCase().contains(q));
  }

  @override
  Widget build(BuildContext context) {
    final kinds = {for (final p in widget.parks) p.kind}.toList();
    final shown = widget.parks.where(_matches).toList();
    final text = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'where_to')), actions: [
        if (widget.parks.length > 1)
          IconButton(
            key: const Key('open_trip'),
            tooltip: tr(context, 'trip_open'),
            icon: const Icon(Icons.route),
            onPressed: () => Navigator.of(context).push(c4Route(context, TripScreen(parks: widget.parks, onPick: (id) {
              Navigator.of(context).pop();
              widget.onPick(id);
            }))),
          ),
        ...widget.actions,
      ]),
      body: ListView(padding: C4Space.page, children: [
        Text(tr(context, 'where_to_sub'), style: text.bodyLarge),
        const SizedBox(height: C4Space.m),
        if (widget.parks.length > 3)
          Padding(
            padding: const EdgeInsets.only(bottom: C4Space.s),
            child: TextField(
              onChanged: (v) => setState(() => _query = v),
              decoration: InputDecoration(prefixIcon: const Icon(Icons.search), hintText: tr(context, 'search'), isDense: true),
            ),
          ),
        if (kinds.length > 1)
          Wrap(spacing: C4Space.s, runSpacing: C4Space.xs, children: [
            ChoiceChip(label: Text(tr(context, 'all')), selected: _kind == null, onSelected: (_) => setState(() => _kind = null)),
            for (final k in kinds)
              ChoiceChip(
                avatar: Icon(kindIcon(k), size: 18),
                label: Text(kindLabel(context, k)),
                selected: _kind == k,
                onSelected: (_) => setState(() => _kind = _kind == k ? null : k),
              ),
          ]),
        const SizedBox(height: C4Space.s),
        if (shown.isEmpty) Padding(padding: C4Space.page, child: Center(child: Text(tr(context, 'no_match')))),
        for (final p in shown) _DestinationCard(park: p, onTap: () => widget.onPick(p.id)),
      ]),
    );
  }
}

class _DestinationCard extends StatefulWidget {
  const _DestinationCard({required this.park, required this.onTap});

  final ParkInfo park;
  final VoidCallback onTap;

  @override
  State<_DestinationCard> createState() => _DestinationCardState();
}

class _DestinationCardState extends State<_DestinationCard> {
  late Future<Outlook> _outlook;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _outlook = C4Scope.of(context).outlook(forPark: widget.park.id);
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.park;
    final text = Theme.of(context).textTheme;
    final nTrails = p.trails.length;
    return Card(
      clipBehavior: Clip.antiAlias,
      margin: const EdgeInsets.symmetric(vertical: C4Space.s),
      child: InkWell(
        onTap: widget.onTap,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          DestinationBanner(name: p.name, kind: p.kind, region: p.region, accent: p.accent),
          Padding(
            padding: C4Space.page,
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (p.summary.isNotEmpty) Text(p.summary, style: text.bodyMedium),
              const SizedBox(height: C4Space.s),
              Wrap(spacing: C4Space.s, runSpacing: C4Space.xs, children: [
                _Fact(icon: Icons.route, label: tr(context, p.isAdvisory || p.kind == 'safari' ? 'routes_n' : 'trails_n', {'n': nTrails})),
                if (p.elevation.isNotEmpty) _Fact(icon: Icons.terrain, label: p.elevation),
                _Fact(
                  icon: p.isAdvisory ? Icons.schedule : Icons.confirmation_number_outlined,
                  label: tr(context, p.isAdvisory ? 'start_times_advice' : 'tickets_needed'),
                ),
              ]),
              const SizedBox(height: C4Space.m),
              FutureBuilder<Outlook>(
                future: _outlook,
                builder: (context, snap) {
                  if (!snap.hasData || snap.data!.days.isEmpty) {
                    return snap.hasError ? const SizedBox.shrink() : const LinearProgressIndicator();
                  }
                  final week = snap.data!.days.take(7).toList();
                  final q = quietestOf(week);
                  return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Row(children: [
                      Text(tr(context, 'next_7_days'), style: text.labelLarge),
                      const Spacer(),
                      Text(tr(context, 'quietest', {'day': shortDate(q.date)}), style: text.labelMedium),
                    ]),
                    const SizedBox(height: C4Space.xs),
                    WeekStrip(days: week),
                  ]);
                },
              ),
            ]),
          ),
        ]),
      ),
    );
  }
}

class _Fact extends StatelessWidget {
  const _Fact({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(icon, size: 16, color: Theme.of(context).colorScheme.primary),
        const SizedBox(width: C4Space.xs),
        Text(label, style: Theme.of(context).textTheme.bodySmall),
      ]);
}
