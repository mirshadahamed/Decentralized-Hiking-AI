import 'dart:math';

import 'package:flutter/material.dart';

import '../../../data/api_client.dart';
import '../../../models/models.dart';
import '../../theme/c4_theme.dart';
import '../../widgets/c4_ui.dart';

/// Safari parks (Yala): a ranger or tracker reports an animal by the track; every active sighting shows the rule
/// (at most N jeeps stopped, M minutes each) and, when many jeeps are near, which circuits avoid it.
class SightingsTab extends StatefulWidget {
  const SightingsTab({super.key, this.now, this.demo = false});

  final DateTime Function()? now;
  final bool demo; // demo time: ask the server for the status at that time

  @override
  State<SightingsTab> createState() => _SightingsTabState();
}

class _SightingsTabState extends State<SightingsTab> {
  static const species = ['leopard', 'elephant', 'sloth bear', 'other'];
  List<SegmentInfo> _segments = [];
  int? _seg;
  String _species = species.first;
  SightingStatus? _status;
  String? _error;
  bool _busy = false;

  DateTime get _now => widget.now?.call() ?? DateTime.now();
  DateTime get _day => DateTime(_now.year, _now.month, _now.day);
  String get _hhmm => '${_now.hour.toString().padLeft(2, '0')}:${_now.minute.toString().padLeft(2, '0')}';

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_segments.isEmpty && _error == null) _load();
  }

  Future<void> _load() async {
    final api = C4Scope.of(context);
    try {
      final segs = await api.segments();
      final st = await api.sightings(_day, at: widget.demo ? _hhmm : null);
      if (!mounted) return;
      setState(() {
        _segments = segs;
        _seg ??= segs.isEmpty ? null : segs.first.segId;
        _status = st;
        _error = null;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  Future<void> _report() async {
    if (_seg == null) return;
    setState(() => _busy = true);
    try {
      final id = '${DateTime.now().microsecondsSinceEpoch}-${Random().nextInt(1 << 30)}';
      final st = await C4Scope.of(context).reportSighting(_day, _seg!, _hhmm, _species, id);
      if (mounted) setState(() => _status = st);
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _end(Sighting s) async {
    await C4Scope.of(context).endSighting(s.id, _hhmm);
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    if (_error != null && _segments.isEmpty) return ErrorRetry(error: ApiException(0, _error!), onRetry: _load);
    if (_segments.isEmpty) return const Center(child: CircularProgressIndicator());
    final active = _status?.sightings ?? [];
    return RefreshIndicator(
      onRefresh: _load,
      child: ListView(padding: const EdgeInsets.all(C4Space.l), children: [
        Text('Report an animal by the track', style: text.titleMedium),
        const SizedBox(height: C4Space.s),
        DropdownButtonFormField<int>(
          key: const Key('sighting_section'),
          initialValue: _seg,
          isExpanded: true,
          decoration: const InputDecoration(labelText: 'Section', border: OutlineInputBorder()),
          items: [
            for (final s in _segments)
              DropdownMenuItem(value: s.segId, child: Text('${s.name} · ${s.trailName}', overflow: TextOverflow.ellipsis)),
          ],
          onChanged: (v) => setState(() => _seg = v),
        ),
        const SizedBox(height: C4Space.s),
        Wrap(spacing: C4Space.s, children: [
          for (final sp in species)
            ChoiceChip(label: Text(sp), selected: _species == sp, onSelected: (_) => setState(() => _species = sp)),
        ]),
        const SizedBox(height: C4Space.s),
        FilledButton.icon(
          key: const Key('sighting_report'),
          onPressed: _busy ? null : _report,
          icon: const Icon(Icons.pets),
          label: Text('Report at $_hhmm'),
        ),
        if (_error != null) Padding(padding: const EdgeInsets.only(top: C4Space.s), child: Text(_error!)),
        const Divider(height: C4Space.xl),
        Text(active.isEmpty ? 'No active sightings' : 'Active sightings', style: text.titleMedium),
        for (final s in active)
          Card(
            key: Key('sighting_${s.id}'),
            color: s.crowded ? Colors.orange.shade50 : null,
            child: Padding(
              padding: const EdgeInsets.all(C4Space.m),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('${s.species[0].toUpperCase()}${s.species.substring(1)} at ${s.place} · since ${s.since}',
                    style: text.titleSmall),
                const SizedBox(height: C4Space.xs),
                Text('About ${s.jeepsNear} jeeps near · at most ${s.capJeeps} stopped, ${s.rotationMin} min each'),
                const SizedBox(height: C4Space.xs),
                Text(s.advice, style: text.bodySmall),
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton(onPressed: () => _end(s), child: const Text('Animal gone')),
                ),
              ]),
            ),
          ),
        if (_status != null) Text(_status!.note, style: text.bodySmall),
      ]),
    );
  }
}
