import 'package:flutter/material.dart';

import '../../../data/api_client.dart';
import '../../../models/models.dart';
import '../../theme/c4_theme.dart';
import '../../widgets/c4_ui.dart';

/// Halfway checks at a pilgrim site (Adam's Peak). The officer at a route's halfway rest stop counts the people
/// passing (e.g. every 10 minutes). From all counts the server estimates the queue on the final steps when they
/// arrive, and says whether to HOLD groups at the rest stop and how many to let through per 10 minutes.
class HalfwayScreen extends StatefulWidget {
  const HalfwayScreen({super.key, this.demo});

  final DateTime? demo; // start in demo time (e.g. opened from the officer console)

  @override
  State<HalfwayScreen> createState() => _HalfwayScreenState();
}

class _HalfwayScreenState extends State<HalfwayScreen> {
  late DateTime? _demo = widget.demo; // null = real time
  String? _route;
  int _count = 0;
  bool _busy = false;
  String? _error;
  late Future<(CheckpointStatus, List<TrailInfo>)> _future;

  DateTime get _now => _demo ?? DateTime.now();
  DateTime get _day => DateTime(_now.year, _now.month, _now.day);
  String get _at => '${_now.hour.toString().padLeft(2, '0')}:${_now.minute.toString().padLeft(2, '0')}';

  Future<(CheckpointStatus, List<TrailInfo>)> _load() async {
    final api = C4Scope.of(context);
    final r = await Future.wait([api.checkpoints(_day, at: _demo == null ? null : _at), api.trails()]);
    return (r[0] as CheckpointStatus, r[1] as List<TrailInfo>);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = _load();
  }

  void _reload() => setState(() { _future = _load(); });

  Future<void> _pickDemoTime() async {
    final d = await showDatePicker(context: context, initialDate: _now, firstDate: DateTime(2025), lastDate: DateTime(2028));
    if (d == null || !mounted) return;
    final t = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(_now));
    if (t == null) return;
    _demo = DateTime(d.year, d.month, d.day, t.hour, t.minute);
    _reload();
  }

  Future<void> _record(String route) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final api = C4Scope.of(context);
    try {
      await api.recordCheckpoint(route, _count, at: _demo);
      if (_demo != null) _demo = _demo!.add(const Duration(minutes: 10)); // demo: next count 10 minutes later
      _count = 0;
      _reload();
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final api = C4Scope.of(context);
    return Scaffold(
      appBar: AppBar(
        title: Text('Halfway check · ${api.session?.username ?? ''}'),
        actions: [
          TextButton.icon(
            onPressed: _pickDemoTime,
            onLongPress: () {
              _demo = null;
              _reload();
            },
            icon: const Icon(Icons.schedule),
            label: Text(_demo == null ? 'Now' : 'Demo ${shortDate(_demo!)} $_at'),
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
      ),
      body: FutureBuilder<(CheckpointStatus, List<TrailInfo>)>(
        future: _future,
        builder: (context, snap) {
          if (snap.hasError) return ErrorRetry(error: snap.error!, onRetry: _reload);
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final (st, trails) = snap.data!;
          final route = _route ?? trails.first.id;
          final text = Theme.of(context).textTheme;
          return RefreshIndicator(
            onRefresh: () async => _reload(),
            child: ListView(padding: C4Space.page, children: [
              CheckpointActionCard(status: st),
              const SizedBox(height: C4Space.l),
              Text('My checkpoint', style: text.labelLarge),
              const SizedBox(height: C4Space.xs),
              Wrap(spacing: C4Space.s, runSpacing: C4Space.xs, children: [
                for (final t in trails)
                  ChoiceChip(label: Text(t.name), selected: t.id == route, onSelected: (_) => setState(() => _route = t.id)),
              ]),
              for (final c in st.checkpoints.where((c) => c.route == route))
                BasisNote(planText(c)),
              const SizedBox(height: C4Space.m),
              Card(
                child: Padding(
                  padding: C4Space.page,
                  child: Column(children: [
                    Text('People who passed in the last 10 minutes', style: text.titleSmall, textAlign: TextAlign.center),
                    const SizedBox(height: C4Space.s),
                    Text('$_count', style: text.displayMedium?.copyWith(fontWeight: FontWeight.w700)),
                    const SizedBox(height: C4Space.s),
                    Wrap(alignment: WrapAlignment.center, spacing: C4Space.s, runSpacing: C4Space.s, children: [
                      for (final n in [1, 10, 50, 100])
                        FilledButton.tonal(onPressed: () => setState(() => _count += n), child: Text('+$n')),
                      OutlinedButton(onPressed: _count == 0 ? null : () => setState(() => _count = 0), child: const Text('Clear')),
                    ]),
                    const SizedBox(height: C4Space.m),
                    FilledButton.icon(
                      onPressed: _busy ? null : () => _record(route),
                      icon: const Icon(Icons.send),
                      label: Text('Record $_count'),
                      style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(56)),
                    ),
                    if (_error != null) ...[
                      const SizedBox(height: C4Space.s),
                      Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                    ],
                  ]),
                ),
              ),
              const SizedBox(height: C4Space.m),
              Text('All checkpoints', style: text.titleMedium),
              for (final c in st.checkpoints)
                Card(
                  child: ListTile(
                    leading: Icon(Icons.local_police_outlined, color: st.hold ? C4Colors.red : C4Colors.green),
                    title: Text(c.name),
                    subtitle: Text('${c.countedToday} counted tonight · ${c.walkToSummitMin} min to the summit'),
                    trailing: c.releasePer10Min == null
                        ? const Text('Let pass')
                        : Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.end, children: [
                            Text('${c.releasePer10Min}', style: text.titleLarge?.copyWith(fontWeight: FontWeight.w700)),
                            Text('per 10 min', style: text.labelSmall),
                          ]),
                  ),
                ),
              const BasisNote('Estimated from the halfway counts and walking times (no sensors). '
                  'Final-steps capacity is about 25 people per minute; confirm with the summit officers by radio.'),
            ]),
          );
        },
      ),
    );
  }
}

/// Tonight's forecast plan for one checkpoint, e.g. "Forecast: hold 03:15–05:00".
String planText(CheckpointRow c) {
  if (c.plannedHold.isNotEmpty) return 'Forecast: hold expected ${windowsText(c.plannedHold)}';
  if (c.plannedHoldIfBusy.isNotEmpty) return 'Forecast: no hold expected; stand by ${windowsText(c.plannedHoldIfBusy)} in case it is busier';
  return 'Forecast: no hold expected tonight';
}

class CheckpointActionCard extends StatelessWidget {
  const CheckpointActionCard({super.key, required this.status});

  final CheckpointStatus status;

  @override
  Widget build(BuildContext context) {
    final c = status.hold ? C4Colors.red : C4Colors.green;
    final on = C4Colors.onColor(c);
    final text = Theme.of(context).textTheme;
    return Card(
      color: c,
      child: Padding(
        padding: C4Space.page,
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(status.hold ? Icons.front_hand : Icons.check_circle, color: on, size: 36),
            const SizedBox(width: C4Space.m),
            Expanded(child: Text(status.hold ? 'HOLD' : 'NORMAL', style: text.headlineMedium?.copyWith(color: on, fontWeight: FontWeight.w800))),
            Text(status.time, style: text.titleMedium?.copyWith(color: on)),
          ]),
          const SizedBox(height: C4Space.s),
          Text(status.action, style: text.titleMedium?.copyWith(color: on)),
          const SizedBox(height: C4Space.s),
          Text(
            'Queue on the final steps now: about ${status.queueNow} people (${status.waitNowMin} min). '
            'Longest wait in the next ${status.aheadMin} min: ${status.waitAheadMin} min.',
            style: text.bodyMedium?.copyWith(color: on),
          ),
        ]),
      ),
    );
  }
}
