import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../data/api_client.dart';
import '../../../models/models.dart';
import '../../theme/c4_theme.dart';
import '../../widgets/c4_ui.dart';

/// Officer records: visitors per day for past, today and future days, filtered by trail and dates, to keep and
/// export (CSV). Past = DWC total or the estimate (says which), future = forecast with a range, plus this
/// system's own counts (booked, through the gate, halfway checkpoints) and the day's safe limit.
class RecordsTab extends StatefulWidget {
  const RecordsTab({super.key});

  @override
  State<RecordsTab> createState() => _RecordsTabState();
}

enum _Range { around, past30, week, next90, pastYear, custom }

const _rangeLabel = {
  _Range.around: 'Past 30 days + next week',
  _Range.past30: 'Past 30 days',
  _Range.week: 'Today + 6 days',
  _Range.next90: 'Next 90 days',
  _Range.pastYear: 'Past year',
  _Range.custom: 'Custom…',
};

const _periodColor = {'past': Color(0xFF78909C), 'today': Color(0xFF2E7D32), 'future': Color(0xFF3B6FB6)};

class _RecordsTabState extends State<RecordsTab> {
  Future<CrowdRecords>? _future;
  DateTime? _today;
  _Range _range = _Range.around;
  DateTimeRange? _custom;
  String? _trail; // null = all trails
  Map<String, String> _trails = {};

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future ??= _load();
  }

  DateTimeRange _dates(DateTime today) => switch (_range) {
        _Range.around => DateTimeRange(start: today.subtract(const Duration(days: 30)), end: today.add(const Duration(days: 6))),
        _Range.past30 => DateTimeRange(start: today.subtract(const Duration(days: 30)), end: today),
        _Range.week => DateTimeRange(start: today, end: today.add(const Duration(days: 6))),
        _Range.next90 => DateTimeRange(start: today, end: today.add(const Duration(days: 90))),
        _Range.pastYear => DateTimeRange(start: today.subtract(const Duration(days: 365)), end: today),
        _Range.custom => _custom ?? DateTimeRange(start: today.subtract(const Duration(days: 30)), end: today),
      };

  Future<CrowdRecords> _load() async {
    final api = C4Scope.of(context);
    _today ??= (await api.status()).today;
    if (_trails.isEmpty) {
      try {
        _trails = {for (final t in await api.trails()) t.id: t.name};
      } on ApiException {
        _trails = {};
      }
    }
    final r = _dates(_today!);
    return api.records(r.start, r.end, trail: _trail);
  }

  void _reload() => setState(() {
        _future = _load();
      });

  Future<void> _pickRange() async {
    final today = _today ?? DateTime.now();
    final r = await showDateRangePicker(
      context: context,
      firstDate: DateTime(2022),
      lastDate: today.add(const Duration(days: 90)),
      initialDateRange: _custom ?? _dates(today),
    );
    if (r == null) return;
    _custom = r;
    _range = _Range.custom;
    _reload();
  }

  Future<void> _copyCsv(CrowdRecords rec) async {
    await Clipboard.setData(ClipboardData(text: rec.toCsv()));
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text('Copied ${rec.rows.length} rows as CSV - paste into Excel or a file')));
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<CrowdRecords>(
        future: _future,
        builder: (context, snap) {
          final text = Theme.of(context).textTheme;
          final filters = Padding(
            padding: const EdgeInsets.fromLTRB(C4Space.l, C4Space.s, C4Space.l, 0),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Wrap(spacing: 6, runSpacing: 0, children: [
                  for (final r in _Range.values)
                    Padding(
                      padding: EdgeInsets.zero,
                      child: ChoiceChip(
                        label: Text(r == _Range.custom && _custom != null
                            ? '${shortDate(_custom!.start)} – ${shortDate(_custom!.end)}'
                            : _rangeLabel[r]!),
                        selected: _range == r,
                        onSelected: (_) {
                          if (r == _Range.custom) {
                            _pickRange();
                          } else {
                            _range = r;
                            _reload();
                          }
                        },
                      ),
                    ),
                ]),
              const SizedBox(height: C4Space.xs),
              Row(children: [
                const Icon(Icons.alt_route, size: 18),
                const SizedBox(width: C4Space.s),
                Expanded(
                  child: DropdownButton<String?>(
                    key: const Key('records_trail'),
                    isExpanded: true,
                    value: _trail,
                    items: [
                      const DropdownMenuItem(value: null, child: Text('All trails')),
                      for (final e in _trails.entries) DropdownMenuItem(value: e.key, child: Text(e.value)),
                    ],
                    onChanged: (v) {
                      _trail = v;
                      _reload();
                    },
                  ),
                ),
                if (snap.hasData)
                  IconButton(
                    key: const Key('records_csv'),
                    tooltip: 'Copy as CSV',
                    icon: const Icon(Icons.copy_all),
                    onPressed: () => _copyCsv(snap.data!),
                  ),
              ]),
            ]),
          );
          if (snap.hasError) {
            return Column(children: [filters, Expanded(child: ErrorRetry(error: snap.error!, onRetry: _reload))]);
          }
          if (!snap.hasData) return Column(children: [filters, const Expanded(child: Center(child: CircularProgressIndicator()))]);
          final rec = snap.data!;
          final days = rec.perDay(); // a selected trail: its own numbers; all trails: added up
          return Column(children: [
            filters,
            Expanded(
              child: ListView(padding: const EdgeInsets.fromLTRB(C4Space.l, C4Space.s, C4Space.l, C4Space.l), children: [
                _Summary(days: days),
                const SizedBox(height: C4Space.s),
                _Bars(days: days),
                const SizedBox(height: C4Space.s),
                Wrap(spacing: C4Space.m, runSpacing: C4Space.xs, children: [
                  for (final p in ['past', 'today', 'future'])
                    Row(mainAxisSize: MainAxisSize.min, children: [
                      Container(width: 12, height: 12, color: _periodColor[p]),
                      const SizedBox(width: 4),
                      Text(p, style: text.bodySmall),
                    ]),
                  Row(mainAxisSize: MainAxisSize.min, children: [
                    Container(width: 14, height: 2, color: Colors.black87),
                    const SizedBox(width: 4),
                    Text('safe limit', style: text.bodySmall),
                  ]),
                  Row(mainAxisSize: MainAxisSize.min, children: [
                    Container(width: 12, height: 12, color: const Color(0xFFC62828)),
                    const SizedBox(width: 4),
                    Text('above the safe limit', style: text.bodySmall),
                  ]),
                ]),
                const Divider(height: C4Space.xl),
                for (final d in days.reversed) _DayTile(day: d, perTrail: _trail == null ? rec.rows.where((r) => r.date == d.date).toList() : const []),
                BasisNote(rec.note),
              ]),
            ),
          ]);
        },
      );
}

String _weekday(DateTime d) => const ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][d.weekday - 1];

class _Summary extends StatelessWidget {
  const _Summary({required this.days});

  final List<RecordRow> days;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    Widget card(String title, List<RecordRow> ds, Color c) {
      final known = ds.where((d) => d.visitors != null).toList();
      final total = known.fold<int>(0, (a, d) => a + d.visitors!);
      final top = known.isEmpty ? null : known.reduce((a, b) => b.visitors! > a.visitors! ? b : a);
      return Expanded(
        child: Card(
          child: Padding(
            padding: const EdgeInsets.all(C4Space.m),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(title, style: text.labelMedium?.copyWith(color: c)),
              Text(known.isEmpty ? '–' : '$total', style: text.titleLarge),
              Text(
                known.isEmpty
                    ? 'no days'
                    : '${known.length} day${known.length == 1 ? '' : 's'} · ~${(total / known.length).round()}/day'
                        '${top != null && known.length > 1 ? '\nbusiest ${shortDate(top.date)}: ${top.visitors}' : ''}',
                style: text.bodySmall,
              ),
            ]),
          ),
        ),
      );
    }

    final over = days.where((d) => d.overLimit).length;
    final gate = days.fold<int>(0, (a, d) => a + d.gateTotal);
    return Column(children: [
      Row(children: [
        card('Past', days.where((d) => d.period == 'past').toList(), _periodColor['past']!),
        card('Today', days.where((d) => d.period == 'today').toList(), _periodColor['today']!),
        card('Expected', days.where((d) => d.period == 'future').toList(), _periodColor['future']!),
      ]),
      Text('$over day${over == 1 ? '' : 's'} above the safe limit · $gate people counted at the gate',
          key: const Key('records_summary'), style: text.bodyMedium),
    ]);
  }
}

class _Bars extends StatelessWidget {
  const _Bars({required this.days});

  final List<RecordRow> days;

  @override
  Widget build(BuildContext context) {
    final maxV = days.fold<int>(1, (a, d) => [a, d.visitors ?? 0, d.high ?? 0, d.safeLimit ?? 0].reduce((x, y) => x > y ? x : y));
    const h = 120.0;
    final w = days.length > 60 ? 4.0 : days.length > 30 ? 7.0 : 12.0;
    return SizedBox(
      height: h + 18,
      child: ListView(
        scrollDirection: Axis.horizontal,
        reverse: false,
        children: [
          for (var i = 0; i < days.length; i++)
            Tooltip(
              message: '${shortDate(days[i].date)}: ${days[i].visitors ?? '–'}'
                  '${days[i].safeLimit != null ? ' (safe ${days[i].safeLimit})' : ''}',
              child: SizedBox(
                width: w + 2,
                child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                  Stack(alignment: Alignment.bottomCenter, children: [
                    SizedBox(height: h, width: w),
                    Container(
                      width: w,
                      height: h * (days[i].visitors ?? 0) / maxV,
                      color: days[i].overLimit
                          ? const Color(0xFFC62828)
                          : _periodColor[days[i].period]!.withValues(alpha: days[i].period == 'future' ? 0.7 : 1),
                    ),
                    if (days[i].safeLimit != null)
                      Positioned(bottom: h * days[i].safeLimit! / maxV, child: Container(width: w + 2, height: 2, color: Colors.black87)),
                  ]),
                  SizedBox(
                    height: 18,
                    child: (i % 7 == 0 || days.length <= 10)
                        ? Text('${days[i].date.day}', style: const TextStyle(fontSize: 9), overflow: TextOverflow.visible, softWrap: false)
                        : null,
                  ),
                ]),
              ),
            ),
        ],
      ),
    );
  }
}

class _DayTile extends StatelessWidget {
  const _DayTile({required this.day, required this.perTrail});

  final RecordRow day;
  final List<RecordRow> perTrail; // all trails selected: the split per trail

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final v = day.visitors == null
        ? '–'
        : day.period == 'future' && day.low != null
            ? '~${day.visitors} (${day.low}–${day.high})'
            : '${day.visitors}';
    final counts = [
      if (day.gateTotal > 0) 'gate ${day.gateTotal}',
      if (day.booked > 0) 'booked ${day.booked}',
      if (day.walkIns > 0) 'walk-ins ${day.walkIns}',
      if (day.halfway > 0) 'halfway counted ${day.halfway}',
      if (day.safeLimit != null) 'safe limit ${day.safeLimit}',
    ];
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      leading: CircleAvatar(
        radius: 18,
        backgroundColor: day.overLimit ? const Color(0xFFC62828) : _periodColor[day.period],
        child: Text(_weekday(day.date), style: const TextStyle(color: Colors.white, fontSize: 11)),
      ),
      title: Row(children: [
        Expanded(child: Text(shortDate(day.date), style: text.titleSmall)),
        Text(v, style: text.titleSmall?.copyWith(color: day.overLimit ? const Color(0xFFC62828) : null)),
      ]),
      subtitle: Text('${day.period} · ${day.source}${counts.isEmpty ? '' : '\n${counts.join(' · ')}'}',
          style: text.bodySmall),
      children: [
        for (final t in perTrail)
          Padding(
            padding: const EdgeInsets.only(left: 52, bottom: 4),
            child: Row(children: [
              Expanded(child: Text(t.trailName, style: text.bodySmall)),
              Text(
                '${t.visitors ?? '–'}${t.gateTotal > 0 ? ' · gate ${t.gateTotal}' : ''}'
                '${t.safeLimit != null ? ' · safe ${t.safeLimit}' : ''}',
                style: text.bodySmall?.copyWith(color: t.overLimit ? const Color(0xFFC62828) : null),
              ),
            ]),
          ),
      ],
    );
  }
}
