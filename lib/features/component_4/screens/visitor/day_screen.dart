import 'package:flutter/material.dart';

import '../../data/api_client.dart';
import '../../data/models.dart';
import '../../data/ticket_store.dart';
import '../../ui/c4_ui.dart';
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
  late Future<(DayPlan, DaySlots, List<TrailInfo>)> _future;
  String _trail = 'main';
  String? _slot;
  int _size = 2;
  bool _busy = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = _load();
  }

  Future<(DayPlan, DaySlots, List<TrailInfo>)> _load() async {
    final api = C4Scope.of(context);
    final status = await api.status();
    final isTomorrow = widget.day.difference(status.today).inDays <= 1;
    final plan = isTomorrow
        ? DayPlan.fromTomorrowJson(await api.tomorrow(), widget.outlookDay?.crowdLevel ?? 3)
        : await api.plan(widget.day);
    return (plan, await api.slots(widget.day), await api.trails());
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
            if (snap.hasError) return ErrorRetry(error: snap.error!, onRetry: () => setState(() => _future = _load()));
            if (!snap.hasData) return const Center(child: CircularProgressIndicator());
            final (plan, slots, trails) = snap.data!;
            final trailSlots = slots.forTrail(_trail);
            final chosen = trailSlots.where((s) => s.slot == _slot).firstOrNull;
            final canBook = chosen != null && !chosen.closed && chosen.placesLeft >= _size && !_busy;
            return ListView(padding: const EdgeInsets.all(16), children: [
              _Summary(plan: plan),
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
  const _TrailCard({required this.trail, required this.expected, required this.selected, required this.onTap});

  final TrailInfo trail;
  final int? expected;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: selected ? scheme.primaryContainer : null,
      child: ListTile(
        onTap: onTap,
        leading: Icon(selected ? Icons.radio_button_checked : Icons.radio_button_off, color: scheme.primary),
        title: Text('${trail.name} · ${trail.lengthKm} km'),
        subtitle: Text([trail.about, if (expected != null) 'Expected that day: ${about(expected!)} people'].join('\n')),
        isThreeLine: true,
      ),
    );
  }
}
