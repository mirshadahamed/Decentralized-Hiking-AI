import 'package:flutter/material.dart';

import '../../../data/api_client.dart';
import '../../../models/models.dart';
import '../../theme/c4_theme.dart';
import '../../widgets/c4_ui.dart';

/// Officer capacity panel (A2): the day's quota per trail under each rule - Cifuentes with the crowd forecast,
/// with the weather only, one number all year, or the officer's own - and the one the tickets use. The forecast
/// lowers a quota when a section is expected over capacity; the panel says which section and when.
class CapacityTab extends StatefulWidget {
  const CapacityTab({super.key});

  @override
  State<CapacityTab> createState() => _CapacityTabState();
}

const _ruleLabel = {
  'forecast': 'With crowd forecast',
  'classic': 'Weather only',
  'static': 'Same all year',
  'manual': 'My number',
};

class _CapacityTabState extends State<CapacityTab> {
  DateTime _day = DateUtils.dateOnly(DateTime.now()).add(const Duration(days: 1));
  Future<CapacityPanel>? _future;
  String? _busyTrail;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future ??= C4Scope.of(context).capacityPanel(_day);
  }

  void _load(DateTime d) => setState(() {
        _day = d;
        _future = C4Scope.of(context).capacityPanel(d);
      });

  Future<void> _choose(TrailQuota t, String rule) async {
    final api = C4Scope.of(context);
    int? number;
    if (rule == 'manual') {
      number = await _askNumber(t);
      if (number == null) return;
    }
    setState(() => _busyTrail = t.trail);
    try {
      final alerts = await api.setQuota(_day, t.trail, rule, quota: number);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
          content: Text(alerts.isEmpty
              ? '${t.name}: tickets re-planned (${_ruleLabel[rule]})'
              : '${t.name}: re-planned. ${alerts.length} booked slot(s) are now over the safe plan - see Alerts')));
      _load(_day);
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _busyTrail = null);
    }
  }

  Future<int?> _askNumber(TrailQuota t) =>
      showDialog<int>(context: context, builder: (_) => _NumberDialog(title: 'Daily quota · ${t.name}', initial: t.quota.applied));

  @override
  Widget build(BuildContext context) {
    final today = DateUtils.dateOnly(DateTime.now());
    final days = [for (var k = 1; k <= 7; k++) today.add(Duration(days: k))];
    final picker = SizedBox(
      height: 48,
      child: ListView(scrollDirection: Axis.horizontal, padding: const EdgeInsets.symmetric(horizontal: C4Space.l), children: [
        for (final d in days)
          Padding(
            padding: const EdgeInsets.only(right: 6),
            child: ChoiceChip(label: Text(shortDate(d)), selected: DateUtils.isSameDay(d, _day), onSelected: (_) => _load(d)),
          ),
        ActionChip(
          avatar: const Icon(Icons.edit_calendar, size: 18),
          label: const Text('Other day'),
          onPressed: () async {
            final d = await showDatePicker(
                context: context, initialDate: _day, firstDate: days.first, lastDate: today.add(const Duration(days: 90)));
            if (d != null) _load(d);
          },
        ),
      ]),
    );
    return FutureBuilder<CapacityPanel>(
      future: _future,
      builder: (context, snap) {
        if (snap.hasError) {
          return Column(children: [picker, Expanded(child: ErrorRetry(error: snap.error!, onRetry: () => _load(_day)))]);
        }
        if (!snap.hasData) return Column(children: [picker, const Expanded(child: Center(child: CircularProgressIndicator()))]);
        final p = snap.data!;
        final text = Theme.of(context).textTheme;
        return Column(children: [
          picker,
          Expanded(
            child: ListView(padding: const EdgeInsets.fromLTRB(C4Space.l, C4Space.s, C4Space.l, C4Space.l), children: [
              Text('Daily quota for ${niceDate(p.day)}', style: text.titleMedium),
              const SizedBox(height: C4Space.xs),
              _Basis(p.basis),
              for (final t in p.trails)
                _TrailCard(t: t, busy: _busyTrail == t.trail, onChoose: (r) => _choose(t, r)),
              const SizedBox(height: C4Space.m),
              Text(p.over.isEmpty ? 'No section is expected over capacity' : 'Sections expected over capacity',
                  style: text.titleMedium),
              for (final o in p.over.take(12)) _OverTile(o),
              if (p.basis['evidence'] != null) BasisNote(p.basis['evidence']!),
            ]),
          ),
        ]);
      },
    );
  }
}

class _NumberDialog extends StatefulWidget {
  const _NumberDialog({required this.title, required this.initial});

  final String title;
  final int initial;

  @override
  State<_NumberDialog> createState() => _NumberDialogState();
}

class _NumberDialogState extends State<_NumberDialog> {
  late final _c = TextEditingController(text: '${widget.initial}');

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: Text(widget.title),
        content: TextField(
          key: const Key('quota_number'),
          controller: _c,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'People that day', border: OutlineInputBorder()),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, int.tryParse(_c.text.trim())), child: const Text('Use')),
        ],
      );
}

/// A6: what the numbers are based on.
class _Basis extends StatelessWidget {
  const _Basis(this.basis);

  final Map<String, String> basis;

  @override
  Widget build(BuildContext context) {
    final small = Theme.of(context).textTheme.bodySmall;
    Widget line(IconData i, String? s) => s == null
        ? const SizedBox.shrink()
        : Padding(
            padding: const EdgeInsets.only(bottom: 2),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(i, size: 16, color: Colors.black54),
              const SizedBox(width: 6),
              Expanded(child: Text(s, style: small)),
            ]),
          );
    return Card(
      key: const Key('capacity_basis'),
      color: const Color(0xFFF4F6F8),
      child: Padding(
        padding: const EdgeInsets.all(C4Space.m),
        child: Column(children: [
          line(Icons.insights, 'Crowd forecast: ${basis['crowd'] ?? '-'}'),
          line(Icons.cloud_outlined, 'Weather: ${basis['weather'] ?? '-'}'),
          line(Icons.sensors_off, basis['sensors']),
        ]),
      ),
    );
  }
}

class _TrailCard extends StatelessWidget {
  const _TrailCard({required this.t, required this.busy, required this.onChoose});

  final TrailQuota t;
  final bool busy;
  final ValueChanged<String> onChoose;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final q = t.quota;
    final maxV = [q.forecast, q.classic, q.statik, q.manual ?? 0, t.expected, 1].reduce((a, b) => a > b ? a : b);
    final over = t.expected > q.applied;
    Widget bar(String rule, int? v, Color c) => v == null
        ? const SizedBox.shrink()
        : Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(children: [
              SizedBox(width: 128, child: Text(_ruleLabel[rule]!, style: text.bodySmall)),
              Expanded(
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: FractionallySizedBox(
                    widthFactor: v / maxV,
                    child: Container(height: 10, color: q.rule == rule ? c : c.withValues(alpha: 0.35)),
                  ),
                ),
              ),
              SizedBox(width: 44, child: Text('$v', textAlign: TextAlign.right, style: text.bodySmall)),
            ]),
          );
    return Card(
      key: Key('quota_${t.trail}'),
      margin: const EdgeInsets.only(top: C4Space.s),
      child: Padding(
        padding: const EdgeInsets.all(C4Space.m),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text(t.name, style: text.titleSmall)),
            Text('${q.applied}', style: text.headlineSmall?.copyWith(color: over ? C4Colors.red : null)),
          ]),
          Text('Tickets use: ${_ruleLabel[q.rule]}${q.decidedBy != null ? ' (set by ${q.decidedBy})' : ''} · '
              '${t.expected} expected', style: text.bodySmall),
          const SizedBox(height: C4Space.s),
          bar('forecast', q.forecast, C4Colors.green),
          bar('classic', q.classic, const Color(0xFF3B6FB6)),
          bar('static', q.statik, const Color(0xFF78909C)),
          if (q.manual != null) bar('manual', q.manual, const Color(0xFF8E24AA)),
          const SizedBox(height: C4Space.xs),
          Text(t.reason, style: text.bodySmall),
          const SizedBox(height: C4Space.s),
          busy
              ? const LinearProgressIndicator()
              : Wrap(spacing: 6, runSpacing: 4, children: [
                  for (final r in const ['forecast', 'classic', 'static', 'manual'])
                    ChoiceChip(
                      key: Key('rule_${t.trail}_$r'),
                      label: Text(_ruleLabel[r]!),
                      selected: q.rule == r,
                      onSelected: (_) => onChoose(r),
                    ),
                ]),
        ]),
      ),
    );
  }
}

class _OverTile extends StatelessWidget {
  const _OverTile(this.o);

  final SectionOver o;

  @override
  Widget build(BuildContext context) => ListTile(
        dense: true,
        contentPadding: EdgeInsets.zero,
        leading: const Icon(Icons.groups, color: C4Colors.red),
        title: Text(o.name),
        subtitle: Text('${_runs(o.hours)} · up to ${o.peakPeople.round()} people, holds ${o.capacityAtOnce.round()} at once'),
      );
}

String _runs(List<int> hours) {
  final out = <String>[];
  for (var i = 0; i < hours.length; i++) {
    final start = hours[i];
    while (i + 1 < hours.length && hours[i + 1] == hours[i] + 1) {
      i++;
    }
    out.add('${start.toString().padLeft(2, '0')}–${(hours[i] + 1).toString().padLeft(2, '0')} h');
  }
  return out.join(', ');
}
