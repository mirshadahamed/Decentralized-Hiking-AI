import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../data/api_client.dart';
import '../../../domain/bottleneck.dart';
import '../../../models/models.dart';
import '../../../domain/edge_forecaster.dart';
import '../../../services/edge_store.dart';
import '../../../services/ticket_store.dart';
import '../../widgets/c4_ui.dart';
import '../../widgets/weather_card.dart';
import '../bottleneck_screen.dart';
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
  Future<(EdgeForecast, bool)?>? _edge; // tomorrow only: the forecast computed on this device
  Future<DayWeather?>? _weather; // the day's weather (observed / forecast / typical); none on an older server
  String _trail = 'main';
  Map<String, String> _names = const {};
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
    _weather = api.weather(widget.day).then<DayWeather?>((w) => w, onError: (_) => null);
    final ServerStatus status;
    try {
      status = await api.status();
    } on ApiException {
      _edge = _runOnDevice(api); // no connection: the stored pack still gives tomorrow's forecast (if it is for this day)
      rethrow;
    }
    final isTomorrow = widget.day.difference(status.today).inDays <= 1;
    if (isTomorrow) _edge = _runOnDevice(api);
    final plan = isTomorrow
        ? DayPlan.fromTomorrowJson(await api.tomorrow(), widget.outlookDay?.crowdLevel ?? 3)
        : await api.plan(widget.day);
    DayCapacity? cap;
    try {
      cap = await api.capacity(widget.day);
    } on ApiException {
      cap = null; // older server: the screen still works without the safe limit
    }
    final trails = await api.trails();
    _names = {for (final t in trails) t.id: t.name};
    if (!_names.containsKey(_trail) && trails.isNotEmpty) _trail = trails.first.id;   // each park has its own trails
    return (plan, await api.slots(widget.day), trails, cap);
  }

  /// Tomorrow's ST-GNN forecast computed on this device from the daily edge pack (works offline).
  Future<(EdgeForecast, bool)?> _runOnDevice(C4Api api) async {
    final loaded = await EdgeStore.load(api);
    if (loaded == null) return null;
    final (model, offline) = loaded;
    if (model.day != C4Api.day(widget.day)) return null; // pack is for another day
    return (model.forecast(), offline);
  }

  Widget _onDevice(List<TrailInfo> trails) => FutureBuilder<(EdgeForecast, bool)?>(
        future: _edge,
        builder: (context, e) => e.data == null
            ? const SizedBox.shrink()
            : Padding(
                padding: const EdgeInsets.only(top: 12),
                child: OnDeviceCard(forecast: e.data!.$1, offline: e.data!.$2, trails: trails),
              ),
      );

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
                title: Text('${_names[a.trail] ?? a.trail} · ${a.slot}'),
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
            if (snap.hasError) {
              final retry = ErrorRetry(error: snap.error!, onRetry: () => setState(() { _future = _load(); }));
              if (_edge == null) return retry;
              return ListView(padding: const EdgeInsets.all(16), children: [_onDevice(const []), retry]);
            }
            if (!snap.hasData) return const Center(child: CircularProgressIndicator());
            final (plan, slots, trails, cap) = snap.data!;
            final trailSlots = slots.forTrail(_trail);
            final chosen = trailSlots.where((s) => s.slot == _slot).firstOrNull;
            final canBook = chosen != null && !chosen.closed && chosen.placesLeft >= _size && !_busy;
            return ListView(padding: const EdgeInsets.all(16), children: [
              _Summary(plan: plan),
              FutureBuilder<DayWeather?>(
                future: _weather,
                builder: (context, w) => w.data == null
                    ? const SizedBox.shrink()
                    : Padding(padding: const EdgeInsets.only(top: 12), child: WeatherCard(weather: w.data!)),
              ),
              if (cap != null) ...[const SizedBox(height: 12), SafeLimitCard(capacity: cap)],
              if (_edge != null) _onDevice(trails),
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
              const SizedBox(height: 16),
              StartTimeCard(key: ValueKey('$_trail/$_size'), day: widget.day, trail: _trail, size: _size,
                  trailName: _names[_trail] ?? _trail),
            ]);
          },
        ),
      );
}

/// N3: for visitors without a ticket - the earliest start with room in today's plan; coming then means going in
/// first at the gate. "Hold" counts it against the plan and gives a code to show.
class StartTimeCard extends StatefulWidget {
  const StartTimeCard({super.key, required this.day, required this.trail, required this.size, required this.trailName});

  final DateTime day;
  final String trail, trailName;
  final int size;

  @override
  State<StartTimeCard> createState() => _StartTimeCardState();
}

class _StartTimeCardState extends State<StartTimeCard> {
  String _wanted = '07:00';
  Future<StartTimeSuggestion?>? _future;
  String? _code;

  void _load() => _future = C4Scope.of(context)
      .startTime(widget.day, widget.trail, _wanted, widget.size)
      .then<StartTimeSuggestion?>((s) => s, onError: (_) => null);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_future == null) _load();
  }

  Future<void> _hold(String slot) async {
    try {
      final code = await C4Scope.of(context).holdStartTime(widget.day, widget.trail, slot, widget.size);
      if (mounted) setState(() => _code = code);
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
      setState(_load);
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<StartTimeSuggestion?>(
        future: _future,
        builder: (context, snap) {
          final s = snap.data;
          if (s == null) return const SizedBox.shrink();                 // older server or no plan
          final text = Theme.of(context).textTheme;
          return Card(
            key: const Key('start_time_card'),
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Coming without a ticket?', style: text.titleMedium),
                const SizedBox(height: 4),
                Row(children: [
                  const Text('I would like to start at '),
                  DropdownButton<String>(
                    key: const Key('start_wanted'),
                    value: _wanted,
                    items: [
                      for (var m = 6 * 60; m <= 12 * 60; m += 30)
                        '${(m ~/ 60).toString().padLeft(2, '0')}:${(m % 60).toString().padLeft(2, '0')}'
                    ].map((v) => DropdownMenuItem(value: v, child: Text(v))).toList(),
                    onChanged: (v) => setState(() {
                      _wanted = v!;
                      _code = null;
                      _load();
                    }),
                  ),
                ]),
                if (s.suggested == null)
                  Text(s.note, style: text.bodyMedium?.copyWith(color: C4Colors.red))
                else ...[
                  Text(
                      s.laterMin == 0
                          ? 'Start at ${s.suggested} on the ${widget.trailName}: there is room.'
                          : 'Start at ${s.suggested} instead (${s.laterMin} min later): the ${widget.trailName} is full before then.',
                      key: const Key('start_suggested'),
                      style: text.bodyMedium?.copyWith(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 4),
                  Text(s.note, style: text.bodySmall),
                  const SizedBox(height: 8),
                  if (_code == null)
                    OutlinedButton.icon(
                      key: const Key('start_hold'),
                      onPressed: () => _hold(s.suggested!),
                      icon: const Icon(Icons.schedule),
                      label: Text('Hold ${s.suggested} for ${widget.size}'),
                    )
                  else
                    Text('Held: show code $_code at the gate at ${s.suggested}.',
                        key: const Key('start_code'), style: text.titleSmall?.copyWith(color: C4Colors.green)),
                ],
              ]),
            ),
          );
        },
      );
}

final _n = NumberFormat.decimalPattern();

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
            StatValue(
              value: about(plan.p50).replaceFirst('about ', '~'),
              label: 'people expected',
              caption: plan.p10 == plan.p90 ? null : 'Likely between ${_n.format(plan.p10)} and ${_n.format(plan.p90)}',
            ),
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

/// Tomorrow's busiest places, forecast by the ST-GNN running on this device (no server needed once the daily
/// pack is downloaded).
class OnDeviceCard extends StatelessWidget {
  const OnDeviceCard({super.key, required this.forecast, required this.offline, required this.trails});

  final EdgeForecast forecast;
  final bool offline;
  final List<TrailInfo> trails;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final n = forecast.people.isEmpty ? 0 : forecast.people.first.length;
    final peaks = [for (var s = 0; s < n; s++) (s, forecast.peakOf(s))]..sort((a, b) => b.$2.$2.compareTo(a.$2.$2));
    final names = {for (final t in trails) t.id: t.name};
    String label(int s) {
      final (trail, poi) = s < forecast.places.length ? forecast.places[s] : ('', '');
      if (poi.isNotEmpty) return BottleneckDay.poiLabel(poi);
      return '${names[trail] ?? 'Trail'} · section ${s + 1}';
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.phone_android),
            const SizedBox(width: 8),
            Expanded(child: Text('Forecast made on this phone', style: text.titleMedium)),
            if (offline) const Chip(label: Text('offline copy'), visualDensity: VisualDensity.compact),
          ]),
          const SizedBox(height: 4),
          Text('Busiest trail sections tomorrow, hour by hour (ST-GNN, ${forecast.millis} ms on this device):',
              style: text.bodySmall),
          const SizedBox(height: 4),
          for (final (s, (hour, people)) in peaks.take(3))
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: CircleAvatar(radius: 14, child: Text('${s + 1}', style: text.labelSmall)),
              title: Text(label(s)),
              trailing: Text('about ${people.round()} people at ${hour.toString().padLeft(2, '0')}:00'),
            ),
          const BasisNote('Runs without internet from the forecast pack downloaded with the daily update. '
              'Trained on a simulated visitor history.'),
          Align(
            alignment: Alignment.centerRight,
            child: FilledButton.tonalIcon(
              onPressed: () => Navigator.of(context).push(c4Route(context, const BottleneckScreen())),
              icon: const Icon(Icons.map_outlined),
              label: const Text('Every section on the map'),
            ),
          ),
        ]),
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
                    Text(t.condition.isClosed ? 'closed' : '${about(t.expected)} expected · safe ${t.safeLimit}',
                        style: text.bodyMedium?.copyWith(
                            fontWeight: t.overLimit ? FontWeight.w600 : null, color: t.overLimit ? C4Colors.red : null)),
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
          BasisNote(_basis),
        ]),
      ),
    );
  }
}
