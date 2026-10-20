import 'package:flutter/material.dart';

import '../../../data/api_client.dart';
import '../../../models/models.dart';
import '../../widgets/c4_ui.dart';
import '../bottleneck_screen.dart';
import 'ranger_home.dart';
import 'records_screen.dart';

const _trailNames = {'main': "World's End loop", 'kirigalpotta': 'Kirigalpotta', 'thotupola': 'Thotupola Kanda'};

/// Park officer: the week ahead, closures, alerts from the freeze rule, and a manual refresh.
class OfficerHome extends StatelessWidget {
  const OfficerHome({super.key});

  @override
  Widget build(BuildContext context) {
    final api = C4Scope.of(context);
    return DefaultTabController(
      length: 6,
      child: Scaffold(
        appBar: AppBar(
          title: Text('Park office · ${api.session?.username ?? ''}'),
          actions: [
            IconButton(
              tooltip: 'Gate tools',
              icon: const Icon(Icons.qr_code_scanner),
              onPressed: () => Navigator.of(context).push(c4Route(context, const RangerHome())),
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
          bottom: const TabBar(isScrollable: true, tabs: [
            Tab(icon: Icon(Icons.groups_outlined), text: 'Bottlenecks'),
            Tab(icon: Icon(Icons.calendar_view_week), text: 'This week'),
            Tab(icon: Icon(Icons.report_outlined), text: 'Trail condition'),
            Tab(icon: Icon(Icons.block), text: 'Close trail'),
            Tab(icon: Icon(Icons.notifications), text: 'Alerts'),
            Tab(icon: Icon(Icons.table_chart_outlined), text: 'Records'),
          ]),
        ),
        body: const TabBarView(
          physics: NeverScrollableScrollPhysics(), // the bottleneck map pans with a drag
          children: [BottleneckView(), _WeekTab(), ConditionTab(), _ClosureTab(), _AlertsTab(), RecordsTab()],
        ),
      ),
    );
  }
}

class _WeekTab extends StatefulWidget {
  const _WeekTab();

  @override
  State<_WeekTab> createState() => _WeekTabState();
}

class _WeekTabState extends State<_WeekTab> {
  late Future<(Outlook, List<int>)> _future;
  bool _refreshing = false;

  Future<(Outlook, List<int>)> _load() async {
    final api = C4Scope.of(context);
    final o = await api.outlook();
    final booked = <int>[];
    for (final d in o.days.take(7)) {
      final rows = await api.dayBookings(d.date);
      booked.add(rows.where((r) => r['status'] != 'cancelled').fold<int>(0, (s, r) => s + (r['group_size'] as num).round()));
    }
    return (o, booked);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = _load();
  }

  Future<void> _refresh() async {
    setState(() => _refreshing = true);
    try {
      final r = await C4Scope.of(context).refresh();
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Refreshed for ${r['today']}: ${r['alerts']} alerts')));
      setState(() { _future = _load(); });
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _refreshing = false);
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<(Outlook, List<int>)>(
        future: _future,
        builder: (context, snap) {
          if (snap.hasError) return ErrorRetry(error: snap.error!, onRetry: () => setState(() { _future = _load(); }));
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final (o, booked) = snap.data!;
          return ListView(padding: const EdgeInsets.all(16), children: [
            Row(children: [
              Expanded(child: Text('Next 7 days (forecast made ${shortDate(o.issueDate)})', style: Theme.of(context).textTheme.titleMedium)),
              FilledButton.tonalIcon(
                onPressed: _refreshing ? null : _refresh,
                icon: _refreshing ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.refresh),
                label: const Text('Refresh now'),
              ),
            ]),
            const SizedBox(height: 8),
            for (var i = 0; i < booked.length; i++)
              Card(
                child: ListTile(
                  leading: CircleAvatar(backgroundColor: C4Colors.level(o.days[i].crowdLevel)),
                  title: Text(shortDate(o.days[i].date)),
                  subtitle: Text('${peopleRange(o.days[i].p10, o.days[i].p50, o.days[i].p90)} · ${o.days[i].weatherBasis}\n'
                      '${_trailNames.entries.map((e) => '${e.value} ${o.days[i].byTrail[e.key] ?? 0}').join(' · ')}'),
                  isThreeLine: true,
                  trailing: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                    Text('${booked[i]}', style: Theme.of(context).textTheme.titleLarge),
                    const Text('booked'),
                  ]),
                ),
              ),
          ]);
        },
      );
}

/// Report a trail's condition for some days. The safe limit and the tickets of those days change at once.
class ConditionTab extends StatefulWidget {
  const ConditionTab({super.key});

  @override
  State<ConditionTab> createState() => _ConditionTabState();
}

class _ConditionTabState extends State<ConditionTab> {
  static const _levels = {
    'good': ('Good', Icons.check_circle_outline, C4Colors.green),
    'muddy': ('Muddy', Icons.water_drop_outlined, C4Colors.amber),
    'partly_closed': ('Partly closed', Icons.remove_road, C4Colors.amber),
    'closed': ('Closed', Icons.block, C4Colors.red),
  };
  DateTime _from = DateTime.now().add(const Duration(days: 1));
  DateTime _to = DateTime.now().add(const Duration(days: 1));
  String _trail = 'main', _level = 'muddy';
  final _note = TextEditingController();
  List<Map<String, dynamic>>? _alerts;
  DayCapacity? _cap;
  bool _busy = false;

  Future<void> _save() async {
    setState(() => _busy = true);
    final api = C4Scope.of(context);
    try {
      final a = await api.setCondition(_trail, _from, _to, _level, _note.text.trim());
      DayCapacity? cap;
      try {
        cap = await api.capacity(_from);
      } on ApiException {
        cap = null;
      }
      setState(() {
        _alerts = a;
        _cap = cap;
      });
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _note.dispose();
    super.dispose();
  }

  Future<void> _pick(bool from) async {
    final d = await showDatePicker(context: context, initialDate: from ? _from : _to, firstDate: DateTime(2025), lastDate: DateTime(2028));
    if (d == null) return;
    setState(() {
      if (from) {
        _from = d;
        if (_to.isBefore(d)) _to = d;
      } else {
        _to = d.isBefore(_from) ? _from : d;
      }
    });
  }

  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(16), children: [
        Text('Report a trail condition', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 4),
        const Text('Muddy or partly closed trails hold fewer people safely: the safe limit and the tickets for those '
            'days go down at once. "Good" clears a report. Existing bookings are kept and listed below.'),
        const SizedBox(height: 16),
        DropdownButtonFormField<String>(
          initialValue: _trail,
          decoration: const InputDecoration(labelText: 'Trail', border: OutlineInputBorder()),
          items: [for (final e in _trailNames.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
          onChanged: (v) => setState(() => _trail = v!),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: OutlinedButton.icon(onPressed: () => _pick(true), icon: const Icon(Icons.event), label: Text('From ${shortDate(_from)}')),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: OutlinedButton.icon(onPressed: () => _pick(false), icon: const Icon(Icons.event), label: Text('To ${shortDate(_to)}')),
          ),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final e in _levels.entries)
            ChoiceChip(
              avatar: Icon(e.value.$2, size: 18, color: e.value.$3),
              label: Text(e.value.$1),
              selected: _level == e.key,
              onSelected: (_) => setState(() => _level = e.key),
            ),
        ]),
        const SizedBox(height: 12),
        TextField(controller: _note, decoration: const InputDecoration(labelText: 'Note (optional, shown to visitors)', border: OutlineInputBorder())),
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: _busy ? null : _save,
          icon: _busy ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.save),
          label: const Text('Save and re-plan tickets'),
          style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
        ),
        if (_cap != null) ...[
          const SizedBox(height: 16),
          Text('Safe limits on ${shortDate(_cap!.day)}', style: Theme.of(context).textTheme.titleMedium),
          for (final t in _cap!.trails)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: Text(t.name),
              subtitle: Text(t.condition.isGood ? 'good' : t.condition.label),
              trailing: Text(t.condition.isClosed ? 'closed' : '${t.expected} expected / ${t.safeLimit} safe'),
            ),
        ],
        if (_alerts != null) ...[
          const SizedBox(height: 8),
          Text(_alerts!.isEmpty ? 'Saved. No existing bookings are over the new limit.' : '${_alerts!.length} booked slot(s) now over the limit:',
              style: Theme.of(context).textTheme.titleMedium),
          for (final a in _alerts!) _AlertTile(a),
        ],
      ]);
}

class _ClosureTab extends StatefulWidget {
  const _ClosureTab();

  @override
  State<_ClosureTab> createState() => _ClosureTabState();
}

class _ClosureTabState extends State<_ClosureTab> {
  static final _slots = [for (var m = 6 * 60; m <= 12 * 60 + 30; m += 30) '${(m ~/ 60).toString().padLeft(2, '0')}:${(m % 60).toString().padLeft(2, '0')}'];
  DateTime _day = DateTime.now().add(const Duration(days: 1));
  String _trail = 'main', _from = '06:00', _to = '12:30';
  final _reason = TextEditingController();
  List<Map<String, dynamic>>? _alerts;
  bool _busy = false;

  Future<void> _close() async {
    if (_reason.text.trim().length < 3) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Please give a reason (shown in the audit log).')));
      return;
    }
    setState(() => _busy = true);
    try {
      final a = await C4Scope.of(context).closeTrail(_day, _trail, _from, _to, _reason.text.trim());
      setState(() => _alerts = a);
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  void dispose() {
    _reason.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(16), children: [
        Text('Close a trail for a time window', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 4),
        const Text('Storm, landslide or wildlife. No new tickets are issued; existing bookings are kept and listed below so you can contact or move them.'),
        const SizedBox(height: 16),
        ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.event),
          title: Text(niceDate(_day)),
          trailing: const Icon(Icons.edit_calendar),
          onTap: () async {
            final d = await showDatePicker(context: context, initialDate: _day, firstDate: DateTime(2025), lastDate: DateTime(2028));
            if (d != null) setState(() => _day = d);
          },
        ),
        DropdownButtonFormField<String>(
          initialValue: _trail,
          decoration: const InputDecoration(labelText: 'Trail', border: OutlineInputBorder()),
          items: [for (final e in _trailNames.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
          onChanged: (v) => setState(() => _trail = v!),
        ),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: DropdownButtonFormField<String>(
              initialValue: _from,
              decoration: const InputDecoration(labelText: 'From', border: OutlineInputBorder()),
              items: [for (final s in _slots) DropdownMenuItem(value: s, child: Text(s))],
              onChanged: (v) => setState(() => _from = v!),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: DropdownButtonFormField<String>(
              initialValue: _to,
              decoration: const InputDecoration(labelText: 'To', border: OutlineInputBorder()),
              items: [for (final s in _slots) DropdownMenuItem(value: s, child: Text(s))],
              onChanged: (v) => setState(() => _to = v!),
            ),
          ),
        ]),
        const SizedBox(height: 12),
        TextField(controller: _reason, decoration: const InputDecoration(labelText: 'Reason', border: OutlineInputBorder())),
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: _busy ? null : _close,
          icon: const Icon(Icons.block),
          label: const Text('Close and re-plan'),
          style: FilledButton.styleFrom(backgroundColor: C4Colors.red, minimumSize: const Size.fromHeight(52)),
        ),
        if (_alerts != null) ...[
          const SizedBox(height: 16),
          Text(_alerts!.isEmpty ? 'Closed. No existing bookings affected.' : '${_alerts!.length} booked slot(s) affected:',
              style: Theme.of(context).textTheme.titleMedium),
          for (final a in _alerts!) _AlertTile(a),
        ],
      ]);
}

class _AlertsTab extends StatefulWidget {
  const _AlertsTab();

  @override
  State<_AlertsTab> createState() => _AlertsTabState();
}

class _AlertsTabState extends State<_AlertsTab> {
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = C4Scope.of(context).alerts();
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<List<Map<String, dynamic>>>(
        future: _future,
        builder: (context, snap) {
          if (snap.hasError) {
            return ErrorRetry(error: snap.error!, onRetry: () => setState(() { _future = C4Scope.of(context).alerts(); }));
          }
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final a = snap.data!;
          return ListView(padding: const EdgeInsets.all(16), children: [
            Text('From the last refresh', style: Theme.of(context).textTheme.titleMedium),
            const BasisNote('A slot has more bookings than its safe capacity after the weather got worse or a closure. '
                'Bookings are never cancelled automatically: offer those visitors another time.'),
            if (a.isEmpty) const Card(child: ListTile(leading: Icon(Icons.check_circle, color: C4Colors.green), title: Text('No alerts'))),
            for (final x in a) _AlertTile(x),
          ]);
        },
      );
}

class _AlertTile extends StatelessWidget {
  const _AlertTile(this.a);

  final Map<String, dynamic> a;

  @override
  Widget build(BuildContext context) => Card(
        child: ListTile(
          leading: const Icon(Icons.warning_amber, color: C4Colors.amber),
          title: Text('${a['day']} · ${_trailNames[a['trail']] ?? a['trail']} · ${a['slot']}'),
          subtitle: Text('${a['booked']} booked, ${a['safe_places']} safe places · ${a['reason']}'),
        ),
      );
}
