import 'package:flutter/material.dart';

import '../../../models/models.dart';
import '../../theme/c4_theme.dart';
import '../../widgets/c4_ui.dart';

/// §6.2.5 trip planner: several places over a few days, each visit on a quiet day (gateway GET /trip).
class TripScreen extends StatefulWidget {
  const TripScreen({super.key, required this.parks, this.onPick});

  final List<ParkInfo> parks;
  final ValueChanged<String>? onPick;

  @override
  State<TripScreen> createState() => _TripScreenState();
}

class _TripScreenState extends State<TripScreen> {
  final Set<String> _chosen = {};
  DateTime _start = DateUtils.dateOnly(DateTime.now()).add(const Duration(days: 1));
  int _days = 3;
  Future<TripPlan>? _plan;

  void _change(VoidCallback f) => setState(() {
        f();
        _plan = null;
      });

  String _name(String id) => widget.parks.where((p) => p.id == id).firstOrNull?.name ?? id;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final ok = _chosen.isNotEmpty && _chosen.length <= _days;
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'trip_title'))),
      body: ListView(padding: C4Space.page, children: [
        Text(tr(context, 'trip_sub'), style: text.bodyLarge),
        const SizedBox(height: C4Space.m),
        Wrap(spacing: C4Space.s, runSpacing: C4Space.xs, children: [
          for (final p in widget.parks)
            FilterChip(
              key: Key('trip_${p.id}'),
              label: Text(p.name),
              selected: _chosen.contains(p.id),
              onSelected: (v) => setState(() {
                v ? _chosen.add(p.id) : _chosen.remove(p.id);
                _plan = null;
              }),
            ),
        ]),
        const SizedBox(height: C4Space.m),
        Row(children: [
          Text(tr(context, 'trip_from')),
          TextButton(
            onPressed: () async {
              final d = await showDatePicker(context: context, initialDate: _start, firstDate: DateTime.now(),
                  lastDate: DateTime.now().add(const Duration(days: 120)));
              if (d != null) _change(() => _start = d);
            },
            child: Text(shortDate(_start)),
          ),
          const Spacer(),
          IconButton(onPressed: _days > 1 ? () => _change(() => _days--) : null, icon: const Icon(Icons.remove)),
          Text(tr(context, 'trip_days', {'n': _days}), key: const Key('trip_days')),
          IconButton(onPressed: _days < 14 ? () => _change(() => _days++) : null, icon: const Icon(Icons.add)),
        ]),
        FilledButton.icon(
          key: const Key('trip_plan'),
          onPressed: ok
              ? () {
                  final f = C4Scope.of(context).trip(_chosen.toList(), _start, _days);
                  setState(() {
                    _plan = f;
                  });
                }
              : null,
          icon: const Icon(Icons.route),
          label: Text(tr(context, 'trip_plan')),
        ),
        if (_chosen.length > _days) Text(tr(context, 'trip_too_many'), style: text.bodySmall),
        const SizedBox(height: C4Space.m),
        if (_plan != null)
          FutureBuilder<TripPlan>(
            future: _plan,
            builder: (context, s) {
              if (s.hasError) return Text('${s.error}', style: TextStyle(color: C4Colors.red));
              if (!s.hasData) return const LinearProgressIndicator();
              final t = s.data!;
              return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                for (final v in t.visits)
                  Card(
                    child: ListTile(
                      key: Key('visit_${v.park}'),
                      leading: Icon(Icons.event, color: switch (v.level) {
                        'room' => C4Colors.green, 'busy' => C4Colors.amber, 'full' => C4Colors.red, _ => null }),
                      title: Text('${shortDate(v.day)} · ${_name(v.park)}'),
                      subtitle: Text(v.load == null
                          ? tr(context, 'trip_unknown')
                          : tr(context, 'trip_load', {'pct': (100 * v.load!).round()})),
                      onTap: widget.onPick == null ? null : () => widget.onPick!(v.park),
                    ),
                  ),
                Text(t.note, key: const Key('trip_note'), style: text.bodyMedium),
              ]);
            },
          ),
      ]),
    );
  }
}
