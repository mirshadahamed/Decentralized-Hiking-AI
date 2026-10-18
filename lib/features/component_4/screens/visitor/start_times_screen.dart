import 'package:flutter/material.dart';

import '../../data/models.dart';
import '../../ui/c4_theme.dart';
import '../../ui/c4_ui.dart';

/// Pilgrim sites (Adam's Peak): no tickets. For one night, when to start on each route so the summit is reached
/// before sunrise without a long wait on the final steps (src/control/advisory.py).
class StartTimesScreen extends StatefulWidget {
  const StartTimesScreen({super.key, required this.day, this.outlookDay});

  final DateTime day;
  final OutlookDay? outlookDay;

  @override
  State<StartTimesScreen> createState() => _StartTimesScreenState();
}

class _StartTimesScreenState extends State<StartTimesScreen> {
  late Future<(StartAdvice, List<TrailInfo>)> _future;
  String? _route;

  Future<(StartAdvice, List<TrailInfo>)> _load() async {
    final api = C4Scope.of(context);
    final r = await Future.wait([api.advisory(widget.day), api.trails()]);
    return (r[0] as StartAdvice, r[1] as List<TrailInfo>);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = _load();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(niceDate(widget.day))),
        body: FutureBuilder<(StartAdvice, List<TrailInfo>)>(
          future: _future,
          builder: (context, snap) {
            if (snap.hasError) return ErrorRetry(error: snap.error!, onRetry: () => setState(() { _future = _load(); }));
            if (!snap.hasData) return const Center(child: CircularProgressIndicator());
            final (adv, trails) = snap.data!;
            final names = {for (final t in trails) t.id: t.name};
            final route = _route ?? adv.routes.keys.first;
            final r = adv.routes[route]!;
            final o = widget.outlookDay;
            final text = Theme.of(context).textTheme;
            return ListView(padding: C4Space.page, children: [
              if (o != null)
                Row(children: [
                  CrowdChip(o.crowdLevel),
                  const SizedBox(width: C4Space.s),
                  Expanded(child: Text(peopleRange(o.p10, o.p50, o.p90), style: text.bodyMedium)),
                ]),
              const SizedBox(height: C4Space.m),
              Text(tr(context, 'route'), style: text.labelLarge),
              const SizedBox(height: C4Space.xs),
              Wrap(spacing: C4Space.s, runSpacing: C4Space.xs, children: [
                for (final id in adv.routes.keys)
                  ChoiceChip(
                    label: Text(names[id] ?? id),
                    selected: id == route,
                    onSelected: (_) => setState(() => _route = id),
                  ),
              ]),
              const SizedBox(height: C4Space.m),
              _BestCard(advice: r, limit: adv.limitMin),
              const SizedBox(height: C4Space.m),
              Text(tr(context, 'wait_at_top'), style: text.titleMedium),
              const SizedBox(height: C4Space.s),
              _WaitChart(windows: r.windows, limit: adv.limitMin),
              const SizedBox(height: C4Space.m),
              _WindowTable(windows: r.windows.where((w) => w.beforeSunrise).toList()),
              const SizedBox(height: C4Space.m),
              Card(
                child: ListTile(
                  leading: Icon(adv.peakWaitMin > adv.limitMin ? Icons.groups : Icons.check_circle_outline),
                  title: Text(adv.peakQueue > 0
                      ? tr(context, 'summit_peak', {'time': adv.peakAt, 'n': adv.peakQueue >= 100 ? (adv.peakQueue / 10).round() * 10 : adv.peakQueue})
                      : tr(context, 'summit_clear')),
                  subtitle: Text(tr(context, 'halfway_note')),
                  isThreeLine: true,
                ),
              ),
              BasisNote(tr(context, 'advice_basis')),
            ]);
          },
        ),
      );
}

class _BestCard extends StatelessWidget {
  const _BestCard({required this.advice, required this.limit});

  final RouteAdvice advice;
  final int limit;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final good = advice.recommendedForSunrise;
    return Card(
      color: good.isEmpty ? scheme.errorContainer : scheme.primaryContainer,
      child: Padding(
        padding: C4Space.page,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(tr(context, 'best_start'), style: Theme.of(context).textTheme.labelLarge),
          Text(advice.bestForSunrise, style: Theme.of(context).textTheme.displaySmall?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: C4Space.s),
          if (good.isEmpty)
            Text(tr(context, 'no_good_start'))
          else ...[
            Text(tr(context, 'good_starts'), style: Theme.of(context).textTheme.labelLarge),
            const SizedBox(height: C4Space.xs),
            Wrap(spacing: C4Space.xs, runSpacing: C4Space.xs, children: [
              for (final s in good) Chip(label: Text(s), visualDensity: VisualDensity.compact),
            ]),
          ],
        ]),
      ),
    );
  }
}

/// Bars: expected wait near the top for each start time. Green = recommended; faded = reaches after sunrise.
class _WaitChart extends StatelessWidget {
  const _WaitChart({required this.windows, required this.limit});

  final List<StartWindow> windows;
  final int limit;

  @override
  Widget build(BuildContext context) {
    final maxWait = windows.fold<int>(limit * 2, (m, w) => w.waitMin > m ? w.waitMin : m);
    const h = 120.0;
    return Semantics(
      label: windows.map((w) => '${w.start}: ${w.waitMin} min').join(', '),
      child: Column(children: [
        SizedBox(
          height: h,
          child: Stack(children: [
            Positioned(
              left: 0,
              right: 0,
              bottom: h * limit / maxWait,
              child: Divider(height: 1, color: Theme.of(context).colorScheme.outline),
            ),
            Positioned.fill(
              child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
              for (final w in windows)
                Expanded(
                  child: Tooltip(
                    message: '${w.start} → ${w.reachSummit} · ${w.waitMin} min',
                    child: Container(
                      height: (h * w.waitMin / maxWait).clamp(3.0, h),
                      margin: const EdgeInsets.symmetric(horizontal: 1),
                      decoration: BoxDecoration(
                        color: (w.recommended ? C4Colors.green : (w.waitMin > limit * 3 ? C4Colors.red : C4Colors.amber))
                            .withValues(alpha: w.beforeSunrise ? 1 : 0.35),
                        borderRadius: const BorderRadius.vertical(top: Radius.circular(3)),
                      ),
                    ),
                  ),
                ),
              ]),
            ),
          ]),
        ),
        const SizedBox(height: C4Space.xs),
        Row(children: [
          for (var i = 0; i < windows.length; i++)
            Expanded(
              child: i % 4 == 0
                  ? Text(windows[i].start, style: Theme.of(context).textTheme.labelSmall, overflow: TextOverflow.visible, softWrap: false)
                  : const SizedBox.shrink(),
            ),
        ]),
      ]),
    );
  }
}

class _WindowTable extends StatelessWidget {
  const _WindowTable({required this.windows});

  final List<StartWindow> windows;

  @override
  Widget build(BuildContext context) {
    final bold = Theme.of(context).textTheme.labelLarge;
    return Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: C4Space.l, vertical: C4Space.s),
        child: Table(
          columnWidths: const {0: FlexColumnWidth(), 1: FlexColumnWidth(), 2: FlexColumnWidth()},
          children: [
            TableRow(children: [
              Text(tr(context, 'start'), style: bold),
              Text(tr(context, 'reach_summit'), style: bold),
              Text(tr(context, 'wait'), style: bold),
            ]),
            for (final w in windows)
              TableRow(children: [
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Row(children: [
                    Icon(w.recommended ? Icons.check_circle : Icons.schedule, size: 16, color: w.recommended ? C4Colors.green : C4Colors.amber),
                    const SizedBox(width: C4Space.xs),
                    Text(w.start),
                  ]),
                ),
                Padding(padding: const EdgeInsets.symmetric(vertical: 6), child: Text(w.reachSummit)),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 6),
                  child: Text(tr(context, 'minutes', {'n': w.waitMin})),
                ),
              ]),
          ],
        ),
      ),
    );
  }
}
