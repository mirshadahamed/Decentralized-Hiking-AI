import 'package:flutter/material.dart';

import '../../data/models.dart';
import '../../ui/c4_theme.dart';
import '../../ui/c4_ui.dart';

/// Trip planner, step 2: everything about one destination on one page: what it is, the week ahead, the
/// quietest days, when to go, how to get there and its trails. "Plan" opens the calendar / start times.
class OverviewScreen extends StatefulWidget {
  const OverviewScreen({super.key, required this.onPlan});

  final VoidCallback onPlan;

  @override
  State<OverviewScreen> createState() => _OverviewScreenState();
}

class _OverviewScreenState extends State<OverviewScreen> {
  late Future<(ParkInfo, Outlook, List<TrailInfo>)> _future;

  Future<(ParkInfo, Outlook, List<TrailInfo>)> _load() async {
    final api = C4Scope.of(context);
    final r = await Future.wait([api.destination(), api.outlook(), api.trails()]);
    return (r[0] as ParkInfo, r[1] as Outlook, r[2] as List<TrailInfo>);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = _load();
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<(ParkInfo, Outlook, List<TrailInfo>)>(
        future: _future,
        builder: (context, snap) {
          if (snap.hasError) {
            return ErrorRetry(error: snap.error!, onRetry: () => setState(() { _future = _load(); }));
          }
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final (p, o, trails) = snap.data!;
          final text = Theme.of(context).textTheme;
          final twoWeeks = o.days.take(14).toList();
          final quiet = [...twoWeeks]..sort((a, b) => a.p50.compareTo(b.p50));
          return ListView(padding: EdgeInsets.zero, children: [
            DestinationBanner(name: p.name, kind: p.kind, region: p.region, accent: p.accent, height: 160),
            Padding(
              padding: C4Space.page,
              child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                if (p.summary.isNotEmpty) Text(p.summary, style: text.bodyLarge),
                const SizedBox(height: C4Space.m),
                FilledButton.icon(
                  onPressed: widget.onPlan,
                  icon: Icon(p.isAdvisory ? Icons.schedule : Icons.calendar_month),
                  label: Text(tr(context, p.isAdvisory ? 'plan_climb' : 'plan_visit')),
                  style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
                ),
                const SizedBox(height: C4Space.l),
                if (twoWeeks.isNotEmpty) ...[
                  Text(tr(context, 'next_7_days'), style: text.titleMedium),
                  const SizedBox(height: C4Space.s),
                  WeekStrip(days: twoWeeks.take(7).toList()),
                  const SizedBox(height: C4Space.m),
                  Text(tr(context, 'quiet_days'), style: text.titleMedium),
                  for (final d in quiet.take(3))
                    Card(
                      child: ListTile(
                        leading: CircleAvatar(backgroundColor: C4Colors.level(d.crowdLevel), radius: 10),
                        title: Text(niceDate(d.date)),
                        subtitle: Text(tr(context, 'people_about', {'n': d.p50 >= 100 ? (d.p50 / 10).round() * 10 : d.p50})),
                        trailing: const Icon(Icons.chevron_right),
                        onTap: widget.onPlan,
                      ),
                    ),
                  const SizedBox(height: C4Space.m),
                ],
                if (p.bestTime.isNotEmpty) _Section(icon: Icons.wb_twilight, title: tr(context, 'best_time'), body: p.bestTime),
                if (p.gettingThere.isNotEmpty) _Section(icon: Icons.directions_bus_outlined, title: tr(context, 'getting_there'), body: p.gettingThere),
                if (p.elevation.isNotEmpty) _Section(icon: Icons.terrain, title: tr(context, 'elevation'), body: p.elevation),
                if (p.facts.isNotEmpty)
                  _Section(icon: Icons.tips_and_updates_outlined, title: tr(context, 'good_to_know'), body: p.facts.map((f) => '• $f').join('\n')),
                const SizedBox(height: C4Space.s),
                Text(tr(context, p.isAdvisory ? 'routes' : 'trails'), style: text.titleMedium),
                for (final t in trails)
                  Card(
                    child: ListTile(
                      leading: const Icon(Icons.hiking),
                      title: Text(t.name),
                      subtitle: Text([if (t.lengthKm > 0) '${t.lengthKm} km', if (t.about.isNotEmpty) t.about].join(' · ')),
                    ),
                  ),
                BasisNote(o.disclaimer),
              ]),
            ),
          ]);
        },
      );
}

class _Section extends StatelessWidget {
  const _Section({required this.icon, required this.title, required this.body});

  final IconData icon;
  final String title, body;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: C4Space.m),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Icon(icon, color: Theme.of(context).colorScheme.primary),
          const SizedBox(width: C4Space.m),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: Theme.of(context).textTheme.titleSmall),
              const SizedBox(height: 2),
              Text(body),
            ]),
          ),
        ]),
      );
}
