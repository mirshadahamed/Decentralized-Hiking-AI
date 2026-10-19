import 'package:flutter/material.dart';

import '../../../data/api_client.dart';
import '../../../models/models.dart';
import '../../../services/ticket_store.dart';
import '../../widgets/c4_ui.dart';
import 'ticket_screen.dart';

/// Step 2: how busy the day will be, suggestions to avoid the crowd, then pick a trail and a time.
class DayScreen extends StatefulWidget {
  const DayScreen({super.key, required this.day, this.outlookDay});

  final DateTime day;
  final OutlookDay? outlookDay;

  @override
  State<DayScreen> createState() => _DayScreenState();
}

class _DayScreenState extends State<DayScreen> {
  late Future<(DayPlan, DaySlots, List<TrailInfo>, DayCapacity?)> _future;
  String _trail = 'main';
  String? _slot;
  int _size = 2;
  bool _busy = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = _load();
  }

  Future<(DayPlan, DaySlots, List<TrailInfo>, DayCapacity?)> _load() async {
    final api = C4Scope.of(context);
    final status = await api.status();
    final isTomorrow = widget.day.difference(status.today).inDays <= 1;
    final plan = isTomorrow
        ? DayPlan.fromTomorrowJson(await api.tomorrow(), widget.outlookDay?.crowdLevel ?? 3)
        : await api.plan(widget.day);
    DayCapacity? cap;
    try {
      cap = await api.capacity(widget.day);
    } on ApiException {
      cap = null; // older server: the screen still works without the safe limit
    }
    return (plan, await api.slots(widget.day), await api.trails(), cap);
  }

  Future<void> _book(DateTime day, String trail, String slot) async {
    final api = C4Scope.of(context);
    setState(() => _busy = true);
    try {
      final b = await api.book(day, trail, slot, _size);
      await TicketStore().save(b);
      if (!mounted) return;
      await Navigator.of(context).pushReplacement(c4Route(context, TicketScreen(booking: b, justBooked: true)));
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() => _busy = false); // stop the spinner before showing the options
      if (e.isFull) {
        await _showAlternatives(e);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      }
    } finally {
      if (mounted && _busy) setState(() => _busy = false);
    }
  }

  Future<void> _showAlternatives(ApiException e) => showModalBottomSheet(
        context: context,
        showDragHandle: true,
        builder: (sheet) => ListView(shrinkWrap: true, padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: [
          Text('That time just filled up', style: Theme.of(context).textTheme.titleMedium),
          Text(e.message),
          const SizedBox(height: 8),
          for (final a in e.alternatives)
            Card(
              child: ListTile(
                leading: Icon(switch (a.kind) { 'trail' => Icons.hiking, 'day' => Icons.event, _ => Icons.schedule }),
                title: Text('${a.trail == 'main' ? "World's End loop" : a.trail[0].toUpperCase() + a.trail.substring(1)} · ${a.slot}'),
                subtitle: Text('${shortDate(a.day)} · ${a.left} places left'),
                trailing: const Icon(Icons.chevron_right),
                onTap: () {
                  Navigator.of(sheet).pop();
                  _book(a.day, a.trail, a.slot);
                },
              ),
            ),
        ]),
      );

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: Text(niceDate(widget.day))),
        body: FutureBuilder(
          future: _future,
          builder: (context, snap) {
            if (snap.hasError) return ErrorRetry(error: snap.error!, onRetry: () => setState(() { _future = _load(); }));
            if (!snap.hasData) return const Center(child: CircularProgressIndicator());
            final (plan, slots, trails, cap) = snap.data!;
            final trailSlots = slots.forTrail(_trail);
            final chosen = trailSlots.where((s) => s.slot == _slot).firstOrNull;
            final canBook = chosen != null && !chosen.closed && chosen.placesLeft >= _size && !_busy;
            return ListView(padding: const EdgeInsets.all(16), children: [
              _Summary(plan: plan),
              if (cap != null) ...[const SizedBox(height: 12), SafeLimitCard(capacity: cap)],
              if (plan.suggestions.isNotEmpty) ...[
                const SizedBox(height: 16),
                Text('Want a quieter visit?', style: Theme.of(context).textTheme.titleMedium),
                for (final s in plan.suggestions) _SuggestionCard(s),
              ],
              const SizedBox(height: 20),
              Text('Choose a trail', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              for (final t in trails)
                _TrailCard(
                  trail: t,
                  expected: plan.trails[t.id]?.expected,
                  limit: cap?.forTrail(t.id),
                  selected: _trail == t.id,
                  onTap: () => setState(() {
                    _trail = t.id;
                    _slot = null;
                  }),
                ),
              const SizedBox(height: 16),
              Row(children: [
                Text('People in your group', style: Theme.of(context).textTheme.titleMedium),
                const Spacer(),
                IconButton.outlined(onPressed: _size > 1 ? () => setState(() => _size--) : null, icon: const Icon(Icons.remove)),
                Padding(padding: const EdgeInsets.symmetric(horizontal: 12), child: Text('$_size', style: Theme.of(context).textTheme.titleLarge)),
                IconButton.outlined(onPressed: _size < 20 ? () => setState(() => _size++) : null, icon: const Icon(Icons.add)),
              ]),
              const SizedBox(height: 16),
              Text('Choose an entry time', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              Wrap(spacing: 8, runSpacing: 8, children: [
                for (final s in trailSlots.where((s) => s.bookable > 0 || s.closed))
                  ChoiceChip(
                    label: Text(s.closed ? '${s.slot} · closed' : '${s.slot} · ${s.placesLeft} left'),
                    selected: _slot == s.slot,
                    onSelected: s.closed || s.placesLeft < _size ? null : (_) => setState(() => _slot = s.slot),
                  ),
              ]),
              BasisNote('Places per time are set so no part of the trail gets overcrowded '
                  '(${slots.basis}). Some places are kept for visitors without a booking.'),
              const SizedBox(height: 24),
              FilledButton.icon(
                onPressed: canBook ? () => _book(widget.day, _trail, _slot!) : null,
                icon: _busy ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Icon(Icons.confirmation_number),
                label: Text(_slot == null ? 'Pick a time to book' : 'Book $_size place${_size > 1 ? 's' : ''} at $_slot'),
                style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
              ),
            ]);
          },
        ),
      );
}

class _Summary extends StatelessWidget {
  const _Summary({required this.plan});

  final DayPlan plan;

  @override
  Widget build(BuildContext context) => Card(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              Text('Expected crowd', style: Theme.of(context).textTheme.titleMedium),
              const Spacer(),
              CrowdChip(plan.crowdLevel),
            ]),
            const SizedBox(height: 8),
            Text(peopleRange(plan.p10, plan.p50, plan.p90), style: Theme.of(context).textTheme.headlineSmall),
            BasisNote('Confidence: ${plan.confidence}. Estimates from a simulated visitor history until park counts are connected.'),
          ]),
        ),
      );
}

class _SuggestionCard extends StatelessWidget {
  const _SuggestionCard(this.s);

  final Suggestion s;

  @override
  Widget build(BuildContext context) => Card(
        child: ListTile(
          leading: Icon(switch (s.kind) { 'date' => Icons.event, 'later' => Icons.schedule, 'trail' => Icons.hiking, _ => Icons.u_turn_left }),
          title: Text(s.title),
          subtitle: Text(s.detail),
          trailing: Text('${s.reductionPct}%\nfewer', textAlign: TextAlign.center, style: const TextStyle(color: C4Colors.green, fontWeight: FontWeight.bold)),
        ),
      );
}

class _TrailCard extends StatelessWidget {
  const _TrailCard({required this.trail, required this.expected, required this.selected, required this.onTap, this.limit});

  final TrailInfo trail;
  final int? expected;
  final TrailLimit? limit;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final cond = limit?.condition;
    return Card(
      color: selected ? scheme.primaryContainer : null,
      child: ListTile(
        onTap: onTap,
        leading: Icon(selected ? Icons.radio_button_checked : Icons.radio_button_off, color: scheme.primary),
        title: Text('${trail.name} · ${trail.lengthKm} km'),
        subtitle: Text([
          trail.about,
          if (expected != null) 'Expected that day: ${about(expected!)} people',
          if (limit != null) 'Safe limit that day: ${limit!.safeLimit} people',
          if (cond != null && !cond.isGood) 'Trail condition: ${cond.label}${cond.note.isEmpty ? '' : ' – ${cond.note}'}',
        ].join('\n')),
        isThreeLine: true,
      ),
    );
  }
}

/// Expected visitors against the safe limit of the day, per trail. The limit is the Cifuentes carrying capacity
/// for that day's weather, ground wetness, crowding and reported trail condition; "Why this limit?" lists them.
class SafeLimitCard extends StatelessWidget {
  const SafeLimitCard({super.key, required this.capacity});

  final DayCapacity capacity;

  String get _basis {
    final ground = capacity.wetness >= 0.6
        ? 'wet ground'
        : capacity.wetness >= 0.2
            ? 'damp ground'
            : 'dry ground';
    return 'Changes with the weather: based on the ${capacity.weatherBasis} and '
        '${capacity.groundRainMm.round()} mm of ${capacity.groundBasis} in the last ${capacity.groundDays} days ($ground).';
  }

  void _why(BuildContext context, TrailLimit t) => showModalBottomSheet(
        context: context,
        showDragHandle: true,
        builder: (sheet) {
          final shown = [...t.factors.where((f) => f.pct > 0)]..sort((a, b) => b.pct.compareTo(a.pct));
          return ListView(shrinkWrap: true, padding: const EdgeInsets.fromLTRB(16, 0, 16, 24), children: [
            Text('Why the limit on ${t.name} is ${t.safeLimit}', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 4),
            const Text('Each factor removes a share of what the trail could hold (Cifuentes carrying capacity):'),
            const SizedBox(height: 8),
            for (final f in shown)
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: Icon(switch (f.key) {
                  'precipitation' => Icons.water_drop_outlined,
                  'wet_ground' => Icons.grass,
                  'condition' => Icons.report_outlined,
                  'crowding' => Icons.groups_outlined,
                  'accessibility' => Icons.terrain,
                  _ => Icons.straighten,
                }),
                title: Text(f.label[0].toUpperCase() + f.label.substring(1)),
                trailing: Text('−${f.pct} %', style: Theme.of(context).textTheme.titleSmall),
              ),
            BasisNote('${t.condition.isGood ? 'No trail problems reported. ' : 'Reported by park staff: ${t.condition.label}. '}$_basis'),
          ]);
        },
      );

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: Text('Safe limit for this day', style: text.titleMedium)),
            const Icon(Icons.shield_outlined),
          ]),
          const SizedBox(height: 8),
          for (final t in capacity.trails)
            InkWell(
              onTap: () => _why(context, t),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Row(children: [
                    Expanded(child: Text(t.name, style: text.bodyMedium?.copyWith(fontWeight: FontWeight.w600))),
                    if (!t.condition.isGood)
                      Padding(
                        padding: const EdgeInsets.only(right: 6),
                        child: Chip(
                          label: Text(t.condition.label),
                          visualDensity: VisualDensity.compact,
                          backgroundColor: (t.condition.isClosed ? C4Colors.red : C4Colors.amber).withValues(alpha: 0.18),
                        ),
                      ),
                    Text(t.condition.isClosed ? 'closed' : '${about(t.expected)} / ${t.safeLimit}', style: text.bodyMedium),
                  ]),
                  const SizedBox(height: 4),
                  LinearProgressIndicator(
                    value: t.safeLimit == 0 ? 1 : (t.expected / t.safeLimit).clamp(0.0, 1.0),
                    minHeight: 8,
                    borderRadius: BorderRadius.circular(4),
                    color: t.overLimit ? C4Colors.red : C4Colors.green,
                    backgroundColor: Theme.of(context).colorScheme.surfaceContainerHighest,
                  ),
                  if (t.overLimit && !t.condition.isClosed)
                    Text('More people expected than is safe: book early or pick a quieter trail or day.',
                        style: text.bodySmall?.copyWith(color: C4Colors.red)),
                ]),
              ),
            ),
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: () => _why(context, capacity.trails.first),
              icon: const Icon(Icons.help_outline, size: 18),
              label: const Text('Why this limit?'),
            ),
          ),
          BasisNote('expected / safe limit. $_basis'),
        ]),
      ),
    );
  }
}
