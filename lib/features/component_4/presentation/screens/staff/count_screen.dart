import 'dart:math';

import 'package:flutter/material.dart';

import '../../../data/api_client.dart';
import '../../../models/models.dart';
import '../../../services/count_store.dart';
import '../../theme/c4_theme.dart';
import '../../widgets/c4_ui.dart';

/// Ranger: count the walkers on a section (A4). Works without a signal: counts wait on the phone and are sent
/// when it is back. These counts are the park's first sensor record and check the forecast.
class CountTab extends StatefulWidget {
  const CountTab({super.key, this.store, this.now});

  final CountStore? store;
  final DateTime Function()? now;

  @override
  State<CountTab> createState() => _CountTabState();
}

class _CountTabState extends State<CountTab> {
  late final CountStore _store = widget.store ?? CountStore();
  List<SegmentInfo> _segments = [];
  int? _seg;
  int _n = 0, _waiting = 0;
  bool _busy = false;
  String? _error;

  DateTime get _now => widget.now?.call() ?? DateTime.now();

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_segments.isEmpty && _error == null) _load();
  }

  Future<void> _load() async {
    final api = C4Scope.of(context);
    try {
      final s = await api.segments();
      final w = (await _store.pending()).length;
      if (!mounted) return;
      setState(() {
        _segments = s;
        _seg ??= s.isEmpty ? null : s.first.segId;
        _waiting = w;
        _error = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  Future<void> _save() async {
    if (_seg == null) return;
    final api = C4Scope.of(context);
    final now = _now;
    final c = SpotCount(
      day: DateTime(now.year, now.month, now.day),
      segId: _seg!,
      time: '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}',
      count: _n,
      clientId: '${now.microsecondsSinceEpoch}-${Random().nextInt(1 << 30)}',
    );
    setState(() => _busy = true);
    await _store.add(c);
    final (sent, left) = await _store.sync(api);
    if (!mounted) return;
    setState(() {
      _busy = false;
      _waiting = left;
      _n = 0;
    });
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(left == 0
            ? 'Count saved and sent ($sent)'
            : 'Saved on this phone. $left count${left == 1 ? '' : 's'} will be sent when there is a signal.')));
  }

  Future<void> _sync() async {
    final (sent, left) = await _store.sync(C4Scope.of(context));
    if (!mounted) return;
    setState(() => _waiting = left);
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Sent $sent · waiting $left')));
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    if (_error != null && _segments.isEmpty) return ErrorRetry(error: _error!, onRetry: _load);
    if (_segments.isEmpty) return const Center(child: CircularProgressIndicator());
    Widget step(String label, int d, {Key? key}) => OutlinedButton(
          key: key,
          onPressed: () => setState(() => _n = max(0, _n + d)),
          style: OutlinedButton.styleFrom(minimumSize: const Size(64, 52)),
          child: Text(label, style: text.titleMedium),
        );
    return ListView(padding: const EdgeInsets.all(C4Space.l), children: [
      Text('Count walkers on a section', style: text.titleMedium),
      const SizedBox(height: C4Space.xs),
      const Text('Stand at one place and count everyone on the section you can see. Works without a signal.'),
      const SizedBox(height: C4Space.m),
      DropdownButtonFormField<int>(
        key: const Key('count_section'),
        initialValue: _seg,
        isExpanded: true,
        decoration: const InputDecoration(labelText: 'Section', border: OutlineInputBorder()),
        items: [
          for (final s in _segments)
            DropdownMenuItem(
                value: s.segId,
                child: Row(children: [
                  if (s.modelInput) ...[const Icon(Icons.star, size: 16, color: C4Colors.amber), const SizedBox(width: 4)],
                  Expanded(child: Text('${s.name} · ${s.trailName}', overflow: TextOverflow.ellipsis)),
                ])),
        ],
        onChanged: (v) => setState(() => _seg = v),
      ),
      const SizedBox(height: C4Space.l),
      Center(child: Text('$_n', key: const Key('count_value'), style: text.displayLarge)),
      const SizedBox(height: C4Space.s),
      SizedBox(
        height: 96,
        child: FilledButton(
          key: const Key('count_plus'),
          onPressed: () => setState(() => _n++),
          child: const Text('+1', style: TextStyle(fontSize: 32)),
        ),
      ),
      const SizedBox(height: C4Space.s),
      Wrap(alignment: WrapAlignment.spaceEvenly, spacing: C4Space.s, runSpacing: C4Space.s, children: [
        step('−1', -1),
        step('+5', 5, key: const Key('count_plus5')),
        step('+10', 10),
        OutlinedButton(onPressed: () => setState(() => _n = 0), child: const Text('Reset')),
      ]),
      const SizedBox(height: C4Space.l),
      FilledButton.icon(
        key: const Key('count_save'),
        onPressed: _busy ? null : _save,
        icon: const Icon(Icons.save),
        label: Text('Save count at ${TimeOfDay.fromDateTime(_now).format(context)}'),
        style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
      ),
      const SizedBox(height: C4Space.s),
      Row(children: [
        Icon(_waiting == 0 ? Icons.cloud_done : Icons.cloud_upload_outlined, size: 18),
        const SizedBox(width: 6),
        Expanded(child: Text(_waiting == 0 ? 'All counts sent' : '$_waiting waiting to be sent', key: const Key('count_waiting'))),
        if (_waiting > 0) TextButton(onPressed: _sync, child: const Text('Send now')),
      ]),
      const IconNote(
          icon: Icons.star,
          color: C4Colors.amber,
          text: 'A count here also updates today\'s forecast for every section (Live tab). All counts are the park\'s '
              'own record; the office compares them with the forecast (Forecast check).'),
    ]);
  }
}

/// Officer: the rangers' counts next to the day-ahead forecast of the same section and hour (A4).
class ForecastCheckTab extends StatefulWidget {
  const ForecastCheckTab({super.key});

  @override
  State<ForecastCheckTab> createState() => _ForecastCheckTabState();
}

class _ForecastCheckTabState extends State<ForecastCheckTab> {
  Future<ForecastCheck>? _future;
  int _days = 30;

  void _load() {
    final today = DateUtils.dateOnly(DateTime.now());
    _future = C4Scope.of(context).forecastCheck(today.subtract(Duration(days: _days)), today);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_future == null) _load();
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<ForecastCheck>(
        future: _future,
        builder: (context, snap) {
          if (snap.hasError) return ErrorRetry(error: snap.error!, onRetry: () => setState(_load));
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final c = snap.data!;
          final s = c.summary;
          final text = Theme.of(context).textTheme;
          Widget stat(String label, String v, [String? unit]) => Expanded(
                child: StatTile(label: label, value: v, unit: unit),
              );
          return ListView(padding: const EdgeInsets.all(C4Space.l), children: [
            Wrap(spacing: 6, children: [
              for (final d in const [7, 30, 90])
                ChoiceChip(
                  label: Text('Last $d days'),
                  selected: _days == d,
                  onSelected: (_) => setState(() {
                    _days = d;
                    _load();
                  }),
                ),
            ]),
            const SizedBox(height: C4Space.s),
            if ((s['counts'] ?? 0) == 0)
              const Card(child: ListTile(leading: Icon(Icons.info_outline), title: Text('No counts yet'),
                  subtitle: Text('Rangers count walkers in Gate tools → Count. Each count is compared with the forecast.')))
            else ...[
              IntrinsicHeight(
                child: Row(key: const Key('check_summary'), crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  stat('Counts', '${s['counts']}'),
                  stat('Mean error', s['mae'] == null ? '–' : '${s['mae']}', 'people'),
                  stat('Within 30 %', s['within_30pct'] == null ? '–' : '${((s['within_30pct']!) * 100).round()} %'),
                ]),
              ),
              Text(
                  'Bias ${s['bias'] ?? '–'} (more than 0 = forecast too high) · over capacity counted ${s['counted_over_capacity'] ?? 0}, '
                  'called by the forecast ${s['over_capacity_called'] ?? 0}, false alarms ${s['false_alarms'] ?? 0}',
                  style: text.bodySmall),
              const Divider(height: C4Space.xl),
              for (final r in c.rows.reversed)
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  leading: Icon(
                      r.forecast == null
                          ? Icons.help_outline
                          : (r.forecast! - r.count).abs() <= (0.3 * r.count).clamp(2, double.infinity)
                              ? Icons.check_circle_outline
                              : Icons.error_outline,
                      color: r.forecast == null
                          ? null
                          : (r.forecast! - r.count).abs() <= (0.3 * r.count).clamp(2, double.infinity)
                              ? C4Colors.green
                              : C4Colors.amber),
                  trailing: r.countedOver
                      ? const Tooltip(message: 'Over capacity when counted', child: Icon(Icons.groups, color: C4Colors.red))
                      : null,
                  title: Text('${r.name} · ${shortDate(r.day)} ${(r.timeMin ~/ 60).toString().padLeft(2, '0')}:'
                      '${(r.timeMin % 60).toString().padLeft(2, '0')}'),
                  subtitle: Text('counted ${r.count} · forecast ${r.forecast?.round() ?? '–'} · holds ${r.capacity.round()} at once'),
                ),
            ],
            BasisNote(c.note),
          ]);
        },
      );
}
