import 'dart:async';

import 'package:flutter/material.dart';

import '../../data/api_client.dart';
import '../../data/models.dart';
import '../../ui/c4_theme.dart';
import '../../ui/c4_ui.dart';
import 'halfway_screen.dart';

/// Officer console for a pilgrim site (Adam's Peak):
///   Tonight - live summit queue from all halfway counts, what each checkpoint should do, the latest counts.
///   Season  - every night of the outlook: expected pilgrims and whether halfway checks are needed (staff planning).
///   Night plan - one night: expected wait at the summit over the night, when each checkpoint holds, release rates.
class AdvisoryOfficerHome extends StatefulWidget {
  const AdvisoryOfficerHome({super.key});

  @override
  State<AdvisoryOfficerHome> createState() => _AdvisoryOfficerHomeState();
}

class _AdvisoryOfficerHomeState extends State<AdvisoryOfficerHome> {
  DateTime? _demo; // null = real time
  int _refreshes = 0; // bumps the tabs after "Refresh forecasts"
  bool _refreshing = false;

  DateTime get _now => _demo ?? DateTime.now();

  Future<void> _pickDemoTime() async {
    final d = await showDatePicker(context: context, initialDate: _now, firstDate: DateTime(2025), lastDate: DateTime(2028));
    if (d == null || !mounted) return;
    final t = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(_now));
    if (t == null) return;
    setState(() => _demo = DateTime(d.year, d.month, d.day, t.hour, t.minute));
  }

  Future<void> _refreshForecasts() async {
    setState(() => _refreshing = true);
    final api = C4Scope.of(context);
    final messenger = ScaffoldMessenger.of(context);
    try {
      final r = await api.refresh();
      messenger.showSnackBar(SnackBar(content: Text('Forecasts refreshed for ${r['today'] ?? 'today'}.')));
      setState(() => _refreshes++);
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _refreshing = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final api = C4Scope.of(context);
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: Text('Officer · ${api.session?.username ?? ''}'),
          actions: [
            TextButton.icon(
              onPressed: _pickDemoTime,
              onLongPress: () => setState(() => _demo = null),
              icon: const Icon(Icons.schedule),
              label: Text(_demo == null ? 'Now' : 'Demo ${shortDate(_demo!)} ${hhmm(_demo!)}'),
            ),
            IconButton(
              tooltip: 'Refresh forecasts',
              onPressed: _refreshing ? null : _refreshForecasts,
              icon: _refreshing ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.sync),
            ),
            IconButton(
              tooltip: 'Log out',
              icon: const Icon(Icons.logout),
              onPressed: () async {
                await api.logout();
                if (context.mounted) Navigator.of(context).popUntil((r) => r.isFirst);
              },
            ),
          ],
          bottom: const TabBar(tabs: [
            Tab(icon: Icon(Icons.nightlight_outlined), text: 'Tonight'),
            Tab(icon: Icon(Icons.date_range), text: 'Season'),
          ]),
        ),
        body: TabBarView(children: [
          _TonightTab(key: ValueKey('t$_refreshes${_demo ?? ''}'), demo: _demo),
          _SeasonTab(key: ValueKey('s$_refreshes')),
        ]),
      ),
    );
  }
}

String hhmm(DateTime t) => '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';

// ---------- tonight ----------
class _TonightTab extends StatefulWidget {
  const _TonightTab({super.key, required this.demo});

  final DateTime? demo;

  @override
  State<_TonightTab> createState() => _TonightTabState();
}

class _TonightTabState extends State<_TonightTab> {
  late Future<(CheckpointStatus, List<TrailInfo>)> _future;
  Timer? _timer;

  DateTime get _now => widget.demo ?? DateTime.now();
  DateTime get _day => DateTime(_now.year, _now.month, _now.day);

  Future<(CheckpointStatus, List<TrailInfo>)> _load() async {
    final api = C4Scope.of(context);
    final r = await Future.wait([api.checkpoints(_day, at: widget.demo == null ? null : hhmm(_now)), api.trails()]);
    return (r[0] as CheckpointStatus, r[1] as List<TrailInfo>);
  }

  void _reload() => setState(() { _future = _load(); });

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = _load();
    _timer ??= widget.demo == null ? Timer.periodic(const Duration(minutes: 1), (_) => _reload()) : null; // live: every minute
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<(CheckpointStatus, List<TrailInfo>)>(
        future: _future,
        builder: (context, snap) {
          if (snap.hasError) return ErrorRetry(error: snap.error!, onRetry: _reload);
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final (st, _) = snap.data!;
          final text = Theme.of(context).textTheme;
          return RefreshIndicator(
            onRefresh: () async => _reload(),
            child: ListView(padding: C4Space.page, children: [
              Text('Night of ${niceDate(_day)}', style: text.titleMedium),
              const SizedBox(height: C4Space.s),
              CheckpointActionCard(status: st),
              const SizedBox(height: C4Space.m),
              Row(children: [
                Expanded(
                  child: FilledButton.tonalIcon(
                    onPressed: () async {
                      await Navigator.of(context).push(c4Route(context, HalfwayScreen(demo: widget.demo)));
                      _reload();
                    },
                    icon: const Icon(Icons.add_task),
                    label: const Text('Record a count'),
                  ),
                ),
                const SizedBox(width: C4Space.s),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => Navigator.of(context).push(c4Route(context, NightPlanScreen(day: _day))),
                    icon: const Icon(Icons.insights),
                    label: const Text('Night plan'),
                  ),
                ),
              ]),
              const SizedBox(height: C4Space.l),
              Text('Halfway checkpoints', style: text.titleMedium),
              for (final c in st.checkpoints) _CheckpointCard(c: c, holding: st.hold),
              const SizedBox(height: C4Space.m),
              Text('Latest counts', style: text.titleMedium),
              if (st.log.isEmpty)
                const Card(child: ListTile(leading: Icon(Icons.info_outline), title: Text('No counts yet tonight'))),
              for (final e in st.log.take(12))
                ListTile(
                  dense: true,
                  leading: Text(e.time, style: text.titleSmall),
                  title: Text(e.name),
                  subtitle: Text('by ${e.by}'),
                  trailing: Text('${e.count}', style: text.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                ),
              BasisNote(widget.demo == null
                  ? 'Updates every minute. Estimated from the halfway counts and walking times (no sensors).'
                  : 'Demo time: pull down to update. Estimated from the halfway counts and walking times (no sensors).'),
            ]),
          );
        },
      );
}

class _CheckpointCard extends StatelessWidget {
  const _CheckpointCard({required this.c, required this.holding});

  final CheckpointRow c;
  final bool holding;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final stale = holding && c.lastCountAt == null;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(C4Space.m),
        child: Row(children: [
          CircleAvatar(
            backgroundColor: (holding ? C4Colors.red : C4Colors.green).withValues(alpha: 0.15),
            child: Icon(holding ? Icons.front_hand : Icons.directions_walk, color: holding ? C4Colors.red : C4Colors.green),
          ),
          const SizedBox(width: C4Space.m),
          Expanded(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(c.name, style: text.titleSmall),
              Text('${c.countedToday} counted · last ${c.lastCountAt ?? '–'} · ${c.walkToSummitMin} min to the top', style: text.bodySmall),
              Text(planText(c), style: text.bodySmall?.copyWith(color: Theme.of(context).colorScheme.outline)),
              if (stale)
                Text('No count from this checkpoint yet: call by radio', style: text.bodySmall?.copyWith(color: C4Colors.red)),
            ]),
          ),
          const SizedBox(width: C4Space.s),
          c.releasePer10Min == null
              ? Text('Let pass', style: text.labelLarge)
              : Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  Text('${c.releasePer10Min}', style: text.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
                  Text('per 10 min', style: text.labelSmall),
                ]),
        ]),
      ),
    );
  }
}

// ---------- season ----------
class _SeasonTab extends StatefulWidget {
  const _SeasonTab({super.key});

  @override
  State<_SeasonTab> createState() => _SeasonTabState();
}

class _SeasonTabState extends State<_SeasonTab> {
  late Future<List<SeasonNight>> _future;
  bool _onlyChecks = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = C4Scope.of(context).season();
  }

  static const _badge = {
    'needed': ('Checks needed', C4Colors.red, Icons.front_hand),
    'standby': ('Stand by', C4Colors.amber, Icons.notifications_active_outlined),
    'none': ('Normal', C4Colors.green, Icons.check_circle_outline),
  };

  @override
  Widget build(BuildContext context) => FutureBuilder<List<SeasonNight>>(
        future: _future,
        builder: (context, snap) {
          if (snap.hasError) {
            return ErrorRetry(error: snap.error!, onRetry: () => setState(() { _future = C4Scope.of(context).season(); }));
          }
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final all = snap.data!;
          final n = {for (final k in _badge.keys) k: all.where((x) => x.checks == k).length};
          final shown = _onlyChecks ? all.where((x) => x.checks != 'none').toList() : all;
          final text = Theme.of(context).textTheme;
          return ListView(padding: C4Space.page, children: [
            Row(children: [
              for (final e in _badge.entries)
                Expanded(
                  child: Card(
                    color: e.value.$2.withValues(alpha: 0.12),
                    child: Padding(
                      padding: const EdgeInsets.all(C4Space.m),
                      child: Column(children: [
                        Text('${n[e.key]}', style: text.headlineSmall?.copyWith(fontWeight: FontWeight.w700, color: e.value.$2)),
                        Text(e.value.$1, style: text.labelSmall, textAlign: TextAlign.center),
                      ]),
                    ),
                  ),
                ),
            ]),
            const SizedBox(height: C4Space.s),
            SwitchListTile(
              value: _onlyChecks,
              onChanged: (v) => setState(() => _onlyChecks = v),
              title: const Text('Only nights that may need halfway checks'),
              contentPadding: EdgeInsets.zero,
            ),
            for (final d in shown)
              Card(
                child: ListTile(
                  onTap: () => Navigator.of(context).push(c4Route(context, NightPlanScreen(day: d.date, night: d))),
                  leading: CircleAvatar(backgroundColor: C4Colors.level(d.crowdLevel), radius: 12),
                  title: Text(niceDate(d.date)),
                  subtitle: Text([
                    peopleRange(d.p10, d.p50, d.p90),
                    if (d.checks == 'needed') 'hold ${windowsText(d.holdWindows)} (summit arrivals)',
                    if (d.checks == 'standby') 'if busier: hold ${windowsText(d.highHoldWindows)}',
                  ].join('\n')),
                  isThreeLine: d.checks != 'none',
                  trailing: Chip(
                    avatar: Icon(_badge[d.checks]!.$3, size: 16, color: _badge[d.checks]!.$2),
                    label: Text(_badge[d.checks]!.$1),
                    visualDensity: VisualDensity.compact,
                  ),
                ),
              ),
            const BasisNote('"Stand by": no queue expected, but on a night as busy as the high case (1 night in 10 is busier) '
                'the halfway checks are needed. Times are when pilgrims reach the summit; each checkpoint holds earlier by its walk to the top.'),
          ]);
        },
      );
}

// ---------- one night ----------
class NightPlanScreen extends StatefulWidget {
  const NightPlanScreen({super.key, required this.day, this.night});

  final DateTime day;
  final SeasonNight? night;

  @override
  State<NightPlanScreen> createState() => _NightPlanScreenState();
}

class _NightPlanScreenState extends State<NightPlanScreen> {
  late Future<(StartAdvice, List<TrailInfo>)> _future;

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
        appBar: AppBar(title: Text('Night plan · ${shortDate(widget.day)}')),
        body: FutureBuilder<(StartAdvice, List<TrailInfo>)>(
          future: _future,
          builder: (context, snap) {
            if (snap.hasError) return ErrorRetry(error: snap.error!, onRetry: () => setState(() { _future = _load(); }));
            if (!snap.hasData) return const Center(child: CircularProgressIndicator());
            final (a, trails) = snap.data!;
            final names = {for (final t in trails) t.id: t.name};
            final night = widget.night;
            final text = Theme.of(context).textTheme;
            return ListView(padding: C4Space.page, children: [
              Card(
                child: Padding(
                  padding: C4Space.page,
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    if (night != null) Text('Expected pilgrims: ${peopleRange(night.p10, night.p50, night.p90)}', style: text.titleSmall),
                    const SizedBox(height: C4Space.xs),
                    Text(a.holdWindows.isEmpty
                        ? 'Likely: no queue over ${a.limitMin} min (longest ${a.peakWaitMin} min).'
                        : 'Likely: queue over ${a.limitMin} min at the summit ${windowsText(a.holdWindows)} (longest ${a.peakWaitMin} min, around ${a.peakAt}).'),
                    if (a.highVisitors > 0)
                      Text(a.highHoldWindows.isEmpty
                          ? 'If busier (about ${a.highVisitors}): still no long queue (longest ${a.highPeakWaitMin} min).'
                          : 'If busier (about ${a.highVisitors}): queue over ${a.limitMin} min ${windowsText(a.highHoldWindows)} (longest ${a.highPeakWaitMin} min).'),
                  ]),
                ),
              ),
              const SizedBox(height: C4Space.m),
              Text('Expected wait at the summit', style: text.titleMedium),
              const SizedBox(height: C4Space.s),
              NightWaitChart(wait: a.waitByTime, high: a.highWaitByTime, limit: a.limitMin, binMin: a.binMin),
              const SizedBox(height: C4Space.l),
              Text('Halfway checkpoints', style: text.titleMedium),
              for (final r in a.routes.keys)
                Card(
                  child: ListTile(
                    leading: const Icon(Icons.local_police_outlined),
                    title: Text(names[r] ?? r),
                    subtitle: Text([
                      'Hold: ${a.halfway[r]?.holdWindows.isNotEmpty == true ? windowsText(a.halfway[r]!.holdWindows) : 'not expected'}',
                      if (a.highHalfway[r]?.holdWindows.isNotEmpty == true) 'If busier: ${windowsText(a.highHalfway[r]!.holdWindows)}',
                      '${a.halfway[r]?.walkToSummitMin ?? 0} min walk to the top',
                    ].join('\n')),
                    isThreeLine: true,
                    trailing: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.end, children: [
                      Text('${a.halfway[r]?.releasePer10Min ?? 0}', style: text.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
                      Text('per 10 min', style: text.labelSmall),
                    ]),
                  ),
                ),
              const SizedBox(height: C4Space.m),
              Text('Start times given to pilgrims', style: text.titleMedium),
              for (final e in a.routes.entries)
                ListTile(
                  dense: true,
                  title: Text(names[e.key] ?? e.key),
                  subtitle: Text(e.value.recommendedForSunrise.isEmpty
                      ? 'No start time avoids the queue: expect holds'
                      : 'Best ${e.value.bestForSunrise} · good ${e.value.recommendedForSunrise.first}–${e.value.recommendedForSunrise.last}'),
                ),
              const BasisNote('Release = the checkpoint\'s share of what the final steps can take while holding. '
                  'From the crowd forecast and the simulator\'s walking times; confirm on the night with the counts.'),
            ]);
          },
        ),
      );
}

/// Expected wait at the summit through the night (00:00-12:00): likely case in colour, high case faded behind.
class NightWaitChart extends StatelessWidget {
  const NightWaitChart({super.key, required this.wait, required this.high, required this.limit, this.binMin = 15});

  final List<int> wait, high;
  final int limit, binMin;

  @override
  Widget build(BuildContext context) {
    final n = (12 * 60 ~/ binMin).clamp(0, wait.length);
    final w = wait.take(n).toList(), h = high.length >= n ? high.take(n).toList() : List.filled(n, 0);
    final maxW = [limit * 2, ...w, ...h].reduce((a, b) => a > b ? a : b).toDouble();
    const height = 140.0;
    Color colorOf(int x) => x > limit * 3 ? C4Colors.red : (x > limit ? C4Colors.amber : C4Colors.green);
    final scheme = Theme.of(context).colorScheme;
    return Semantics(
      label: 'Expected wait at the summit by time of night',
      child: Column(children: [
        SizedBox(
          height: height,
          child: Stack(children: [
            Positioned(left: 0, right: 0, bottom: height * limit / maxW, child: Divider(height: 1, color: scheme.outline)),
            Positioned(
              right: 0,
              bottom: height * limit / maxW + 2,
              child: Text('$limit min', style: Theme.of(context).textTheme.labelSmall?.copyWith(color: scheme.outline)),
            ),
            Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
              for (var i = 0; i < n; i++)
                Expanded(
                  child: Tooltip(
                    message: '${(i * binMin ~/ 60).toString().padLeft(2, '0')}:${(i * binMin % 60).toString().padLeft(2, '0')} · '
                        '${w[i]} min (if busier ${h[i]} min)',
                    child: Stack(alignment: Alignment.bottomCenter, children: [
                      Container(
                        height: (height * h[i] / maxW).clamp(0.0, height),
                        margin: const EdgeInsets.symmetric(horizontal: 0.5),
                        color: colorOf(h[i]).withValues(alpha: 0.25),
                      ),
                      Container(
                        height: (height * w[i] / maxW).clamp(2.0, height),
                        margin: const EdgeInsets.symmetric(horizontal: 1.5),
                        color: colorOf(w[i]),
                      ),
                    ]),
                  ),
                ),
            ]),
          ]),
        ),
        const SizedBox(height: C4Space.xs),
        Row(children: [
          for (var hr = 0; hr < 12; hr += 2)
            Expanded(child: Text('${hr.toString().padLeft(2, '0')}:00', style: Theme.of(context).textTheme.labelSmall)),
        ]),
        const SizedBox(height: C4Space.xs),
        Row(children: [
          Container(width: 12, height: 12, color: C4Colors.green),
          const SizedBox(width: 4),
          const Text('likely'),
          const SizedBox(width: C4Space.m),
          Container(width: 12, height: 12, color: C4Colors.green.withValues(alpha: 0.25)),
          const SizedBox(width: 4),
          const Text('if busier (1 night in 10)'),
        ]),
      ]),
    );
  }
}
