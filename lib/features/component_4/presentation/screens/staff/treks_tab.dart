import 'package:flutter/material.dart';

import '../../../data/api_client.dart';
import '../../../models/models.dart';
import '../../widgets/c4_ui.dart';

/// K5: rangers check guided groups out at the trailhead and back in; groups not back in time show as overdue.
/// §6.2.7: at every park a group starting a long walk can be registered without a permit (a W code).
class TreksTab extends StatefulWidget {
  const TreksTab({super.key, required this.day, required this.at});

  final DateTime day;
  final DateTime? Function() at; // demo time, null = now

  @override
  State<TreksTab> createState() => _TreksTabState();
}

class _TreksTabState extends State<TreksTab> with ParkTrails {
  final _code = TextEditingController();
  String? _walkTrail;
  int _walkSize = 4;
  Future<OverdueStatus>? _future;
  String? _message;

  String? get _atHm {
    final a = widget.at();
    return a == null ? null : '${a.hour.toString().padLeft(2, '0')}:${a.minute.toString().padLeft(2, '0')}';
  }

  void _load() => _future = C4Scope.of(context).overdue(widget.day, at: _atHm);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future ?? _load();
  }

  @override
  void dispose() {
    _code.dispose();
    super.dispose();
  }

  Future<void> _go(bool out) async {
    final api = C4Scope.of(context);
    final code = _code.text.trim().toUpperCase();
    if (code.isEmpty) return;
    try {
      final r = out ? await api.permitOut(code, at: widget.at()) : await api.permitBack(code, at: widget.at());
      setState(() {
        _message = out
            ? 'Out: ${r['group_size']} people, back by ${(r['expected_back'] as String).substring(11, 16)}'
            : 'Back: ${r['group_size']} people';
        _code.clear();
        _load();
      });
    } on ApiException catch (e) {
      setState(() => _message = e.message);
    }
  }

  Future<void> _register() async {
    final api = C4Scope.of(context);
    final t = pickTrail(_walkTrail);
    if (t == null) return;
    try {
      final r = await api.walkOut(t, _walkSize, at: widget.at());
      setState(() {
        _message = 'Walk ${r['code']}: ${r['group_size']} people on ${trailName(t)}, back by '
            '${(r['expected_back'] as String).substring(11, 16)}';
        _load();
      });
    } on ApiException catch (e) {
      setState(() => _message = e.message);
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final walkTrail = pickTrail(_walkTrail);
    return RefreshIndicator(
      onRefresh: () async => setState(_load),
      child: ListView(padding: const EdgeInsets.all(16), children: [
        Text('Groups out and back', style: text.titleMedium),
        const SizedBox(height: 8),
        TextField(
          key: const Key('trek_code'),
          controller: _code,
          textCapitalization: TextCapitalization.characters,
          decoration: const InputDecoration(labelText: 'Permit or walk code', border: OutlineInputBorder()),
        ),
        const SizedBox(height: 8),
        Row(children: [
          Expanded(
            child: FilledButton.icon(
                key: const Key('trek_out'), onPressed: () => _go(true), icon: const Icon(Icons.logout), label: const Text('Starts now')),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: OutlinedButton.icon(
                key: const Key('trek_back'), onPressed: () => _go(false), icon: const Icon(Icons.login), label: const Text('Back')),
          ),
        ]),
        if (_message != null) Padding(padding: const EdgeInsets.only(top: 8), child: Text(_message!, key: const Key('trek_message'))),
        if (walkTrail != null) ...[
          const SizedBox(height: 16),
          Text('Register a walk (no permit)', style: text.titleSmall),
          Row(children: [
            Expanded(
              child: DropdownButton<String>(
                key: const Key('walk_trail'),
                isExpanded: true,
                value: walkTrail,
                items: [for (final e in trailNames.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
                onChanged: (v) => setState(() => _walkTrail = v),
              ),
            ),
            IconButton(onPressed: _walkSize > 1 ? () => setState(() => _walkSize--) : null, icon: const Icon(Icons.remove)),
            Text('$_walkSize'),
            IconButton(onPressed: _walkSize < 40 ? () => setState(() => _walkSize++) : null, icon: const Icon(Icons.add)),
          ]),
          OutlinedButton.icon(
              key: const Key('walk_out'), onPressed: _register, icon: const Icon(Icons.directions_walk), label: const Text('Starts now')),
        ],
        const Divider(height: 32),
        FutureBuilder<OverdueStatus>(
          future: _future,
          builder: (context, snap) {
            if (snap.hasError) return ErrorRetry(error: snap.error!, onRetry: () => setState(_load));
            if (!snap.hasData) return const Center(child: CircularProgressIndicator());
            final o = snap.data!;
            return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              if (o.overdue.isEmpty)
                const ListTile(leading: Icon(Icons.check_circle, color: C4Colors.green), title: Text('No group is overdue'))
              else
                for (final g in o.overdue)
                  Card(
                    key: Key('overdue_${g.code}'),
                    color: C4Colors.red.withValues(alpha: 0.12),
                    child: ListTile(
                      leading: const Icon(Icons.warning_amber, color: C4Colors.red),
                      title: Text('${g.name} · ${g.size} people · ${g.lateMin} min late'),
                      subtitle: Text('Code ${g.code} · out ${g.outAt}, due back ${g.expectedBack}'),
                    ),
                  ),
              Text('${o.stillOut.length} group${o.stillOut.length == 1 ? '' : 's'} out on time', style: text.bodyMedium),
              for (final g in o.stillOut)
                ListTile(dense: true, title: Text('${g.name} · ${g.size} people'), subtitle: Text('due back ${g.expectedBack}')),
              BasisNote(o.note),
            ]);
          },
        ),
      ]),
    );
  }
}
