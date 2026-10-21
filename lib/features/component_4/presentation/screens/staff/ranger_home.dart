import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../../data/api_client.dart';
import '../../../models/models.dart';
import '../../widgets/c4_ui.dart';
import '../bottleneck_screen.dart';

const _trailNames = {'main': "World's End loop", 'kirigalpotta': 'Kirigalpotta', 'thotupola': 'Thotupola Kanda'};

/// Gate tools: check in tickets, sell walk-in places, live traffic lights.
/// A "demo time" lets the prototype be shown on any date (the server must allow time override).
class RangerHome extends StatefulWidget {
  const RangerHome({super.key});

  @override
  State<RangerHome> createState() => _RangerHomeState();
}

class _RangerHomeState extends State<RangerHome> {
  DateTime? _demo; // null = real time

  DateTime get _now => _demo ?? DateTime.now();
  DateTime get _day => DateTime(_now.year, _now.month, _now.day);

  Future<void> _pickDemoTime() async {
    final d = await showDatePicker(context: context, initialDate: _now, firstDate: DateTime(2025), lastDate: DateTime(2028));
    if (d == null || !mounted) return;
    final t = await showTimePicker(context: context, initialTime: TimeOfDay.fromDateTime(_now));
    if (t == null) return;
    setState(() => _demo = DateTime(d.year, d.month, d.day, t.hour, t.minute));
  }

  @override
  Widget build(BuildContext context) {
    final api = C4Scope.of(context);
    return DefaultTabController(
      length: 4,
      child: Scaffold(
        appBar: AppBar(
          title: Text('Gate · ${api.session?.username ?? ''}'),
          actions: [
            TextButton.icon(
              onPressed: _pickDemoTime,
              onLongPress: () => setState(() => _demo = null),
              icon: const Icon(Icons.schedule),
              label: Text(_demo == null ? 'Now' : 'Demo ${shortDate(_demo!)} ${TimeOfDay.fromDateTime(_demo!).format(context)}'),
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
            Tab(icon: Icon(Icons.qr_code_scanner), text: 'Check in'),
            Tab(icon: Icon(Icons.point_of_sale), text: 'Walk-ins'),
            Tab(icon: Icon(Icons.traffic), text: 'Live'),
            Tab(icon: Icon(Icons.groups_outlined), text: 'Crowding'),
          ]),
        ),
        body: TabBarView(physics: const NeverScrollableScrollPhysics(), children: [
          _CheckInTab(at: () => _demo),
          _WalkInTab(day: _day, at: () => _demo),
          _LiveTab(day: _day, now: _now, demo: _demo != null),
          const BottleneckView(), // where and when sections get crowded this week, also offline
        ]),
      ),
    );
  }
}

// ---------- check in ----------
class _CheckInTab extends StatefulWidget {
  const _CheckInTab({required this.at});

  final DateTime? Function() at;

  @override
  State<_CheckInTab> createState() => _CheckInTabState();
}

class _CheckInTabState extends State<_CheckInTab> {
  final _code = TextEditingController();
  CheckInResult? _result;
  String? _error;
  bool _busy = false;

  bool get _canScan => kIsWeb || defaultTargetPlatform == TargetPlatform.android || defaultTargetPlatform == TargetPlatform.iOS;

  Future<void> _check(String code) async {
    if (code.trim().isEmpty) return;
    setState(() {
      _busy = true;
      _error = null;
      _result = null;
    });
    try {
      final r = await C4Scope.of(context).checkIn(code.trim().toUpperCase(), at: widget.at());
      setState(() => _result = r);
      _code.clear();
    } on ApiException catch (e) {
      setState(() => _error = e.message);
    } finally {
      setState(() => _busy = false);
    }
  }

  Future<void> _scan() async {
    final code = await Navigator.of(context).push<String>(MaterialPageRoute(builder: (_) => const _ScanPage()));
    if (code != null) await _check(code);
  }

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListView(padding: const EdgeInsets.all(16), children: [
        if (_canScan)
          FilledButton.icon(
            onPressed: _busy ? null : _scan,
            icon: const Icon(Icons.qr_code_scanner, size: 32),
            label: const Text('Scan ticket'),
            style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(72), textStyle: const TextStyle(fontSize: 20)),
          ),
        const SizedBox(height: 16),
        TextField(
          controller: _code,
          textCapitalization: TextCapitalization.characters,
          onSubmitted: _check,
          style: const TextStyle(fontSize: 22, letterSpacing: 3),
          decoration: InputDecoration(
            labelText: 'Or type the 8-letter code',
            border: const OutlineInputBorder(),
            suffixIcon: IconButton(icon: const Icon(Icons.send), onPressed: () => _check(_code.text)),
          ),
        ),
        const SizedBox(height: 24),
        if (_busy) const Center(child: CircularProgressIndicator()),
        if (_error != null) Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        if (_result != null)
          Card(
            color: _result!.ok ? const Color(0xFFE6F4EA) : const Color(0xFFFCE8E6),
            child: Padding(
              padding: const EdgeInsets.all(20),
              child: Column(children: [
                Icon(_result!.ok ? Icons.check_circle : Icons.cancel, size: 72, color: _result!.ok ? C4Colors.green : C4Colors.red),
                const SizedBox(height: 8),
                Text(_result!.reason, textAlign: TextAlign.center, style: Theme.of(context).textTheme.titleLarge),
                if (_result!.trail != null)
                  Text('${_trailNames[_result!.trail] ?? _result!.trail} · ${_result!.slot} · ${_result!.groupSize} people',
                      style: Theme.of(context).textTheme.titleMedium),
              ]),
            ),
          ),
      ]);
}

class _ScanPage extends StatefulWidget {
  const _ScanPage();

  @override
  State<_ScanPage> createState() => _ScanPageState();
}

class _ScanPageState extends State<_ScanPage> {
  bool _done = false;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('Point at the ticket QR code')),
        body: MobileScanner(onDetect: (capture) {
          final v = capture.barcodes.isEmpty ? null : capture.barcodes.first.rawValue;
          if (v != null && !_done) {
            _done = true;
            Navigator.of(context).pop(v);
          }
        }),
      );
}

// ---------- walk-ins ----------
class _WalkInTab extends StatefulWidget {
  const _WalkInTab({required this.day, required this.at});

  final DateTime day;
  final DateTime? Function() at;

  @override
  State<_WalkInTab> createState() => _WalkInTabState();
}

class _WalkInTabState extends State<_WalkInTab> {
  late Future<List<WalkInSlot>> _future;
  String _trail = 'main';

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = C4Scope.of(context).walkIns(widget.day);
  }

  @override
  void didUpdateWidget(_WalkInTab old) {
    super.didUpdateWidget(old);
    if (old.day != widget.day) _future = C4Scope.of(context).walkIns(widget.day);
  }

  Future<void> _sell(WalkInSlot s) async {
    var size = 2;
    final ok = await showDialog<bool>(
      context: context,
      builder: (d) => StatefulBuilder(
        builder: (d, set) => AlertDialog(
          title: Text('Walk-in · ${_trailNames[s.trail]} · ${s.slot}'),
          content: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            IconButton.outlined(onPressed: size > 1 ? () => set(() => size--) : null, icon: const Icon(Icons.remove)),
            Padding(padding: const EdgeInsets.all(16), child: Text('$size', style: Theme.of(d).textTheme.headlineMedium)),
            IconButton.outlined(onPressed: size < s.left && size < 20 ? () => set(() => size++) : null, icon: const Icon(Icons.add)),
          ]),
          actions: [
            TextButton(onPressed: () => Navigator.pop(d, false), child: const Text('Back')),
            FilledButton(onPressed: () => Navigator.pop(d, true), child: Text('Sell $size')),
          ],
        ),
      ),
    );
    if (ok != true || !mounted) return;
    final api = C4Scope.of(context);
    try {
      final left = await api.sellWalkIn(widget.day, s.trail, s.slot, size, at: widget.at());
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Sold $size. $left walk-in places left at ${s.slot}.')));
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
    setState(() { _future = api.walkIns(widget.day); });
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<List<WalkInSlot>>(
        future: _future,
        builder: (context, snap) {
          if (snap.hasError) {
            return ErrorRetry(error: snap.error!, onRetry: () => setState(() { _future = C4Scope.of(context).walkIns(widget.day); }));
          }
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final slots = snap.data!.where((s) => s.trail == _trail).toList();
          return ListView(padding: const EdgeInsets.all(16), children: [
            Text('Walk-in places on ${niceDate(widget.day)}', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            SegmentedButton<String>(
              segments: [for (final e in _trailNames.entries) ButtonSegment(value: e.key, label: Text(e.value))],
              selected: {_trail},
              onSelectionChanged: (s) => setState(() => _trail = s.first),
            ),
            const SizedBox(height: 8),
            for (final s in slots)
              Card(
                child: ListTile(
                  title: Text(s.slot, style: Theme.of(context).textTheme.titleLarge),
                  subtitle: Text(s.left > 0 ? '${s.left} places left' : 'Full: offer another time or trail'),
                  trailing: FilledButton.tonal(onPressed: s.left > 0 ? () => _sell(s) : null, child: const Text('Sell')),
                ),
              ),
          ]);
        },
      );
}

// ---------- live ----------
class _LiveTab extends StatefulWidget {
  const _LiveTab({required this.day, required this.now, required this.demo});

  final DateTime day, now;
  final bool demo;

  @override
  State<_LiveTab> createState() => _LiveTabState();
}

class _LiveTabState extends State<_LiveTab> {
  late Future<List<LiveSegment>> _future;

  String get _at => '${widget.now.hour.toString().padLeft(2, '0')}:${widget.now.minute.toString().padLeft(2, '0')}';

  Future<List<LiveSegment>> _load() => C4Scope.of(context).live(widget.day, at: widget.demo ? _at : null);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = _load();
  }

  @override
  void didUpdateWidget(_LiveTab old) {
    super.didUpdateWidget(old);
    if (old.now != widget.now) _future = _load();
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<List<LiveSegment>>(
        future: _future,
        builder: (context, snap) {
          if (snap.hasError) return ErrorRetry(error: snap.error!, onRetry: () => setState(() { _future = _load(); }));
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final segs = snap.data!;
          final count = {for (final l in ['green', 'amber', 'red']) l: segs.where((s) => s.light == l).length};
          final issues = segs.where((s) => s.light != 'green').toList()..sort((a, b) => b.people.compareTo(a.people));
          return RefreshIndicator(
            onRefresh: () async => setState(() { _future = _load(); }),
            child: ListView(padding: const EdgeInsets.all(16), children: [
              Text('Estimated from tickets scanned so far · $_at', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 12),
              Row(children: [
                for (final l in ['green', 'amber', 'red'])
                  Expanded(
                    child: Card(
                      color: C4Colors.light(l),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(children: [
                          Text('${count[l]}', style: Theme.of(context).textTheme.headlineMedium?.copyWith(color: Colors.white)),
                          Text('segments', style: const TextStyle(color: Colors.white)),
                        ]),
                      ),
                    ),
                  ),
              ]),
              const SizedBox(height: 12),
              if (issues.isEmpty)
                const Card(child: ListTile(leading: Icon(Icons.check_circle, color: C4Colors.green), title: Text('All clear: no action needed.'))),
              for (final s in issues)
                Card(
                  child: ListTile(
                    leading: CircleAvatar(backgroundColor: C4Colors.light(s.light)),
                    title: Text('${_trailNames[s.trail]} · segment ${s.segId}${s.poi != null ? ' (${s.poi!.replaceAll('_', ' ')})' : ''}'),
                    subtitle: Text('About ${s.people.round()} people (safe: ${s.capacity?.round() ?? '-'})\n${s.action ?? ''}'),
                    isThreeLine: true,
                  ),
                ),
              const BasisNote('No trail sensors: estimated from scan times and walking speeds. Confirm with a ranger headcount when in doubt.'),
            ]),
          );
        },
      );
}
