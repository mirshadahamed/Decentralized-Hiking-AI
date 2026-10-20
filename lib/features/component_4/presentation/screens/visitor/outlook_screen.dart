import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../models/models.dart';
import '../../widgets/c4_ui.dart';
import 'day_screen.dart';
import 'start_times_screen.dart';

/// Step 1 of booking: a 90-day calendar coloured by how busy each day is expected to be.
/// At a pilgrim site ([advisory]) a day opens the recommended start times instead of the slots.
class OutlookScreen extends StatefulWidget {
  const OutlookScreen({super.key, this.site = 'Horton Plains', this.advisory = false});

  final String site;
  final bool advisory;

  @override
  State<OutlookScreen> createState() => _OutlookScreenState();
}

class _OutlookScreenState extends State<OutlookScreen> {
  late Future<Outlook> _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = C4Scope.of(context).outlook();
  }

  void _reload() => setState(() { _future = C4Scope.of(context).outlook(); });

  @override
  Widget build(BuildContext context) => FutureBuilder<Outlook>(
        future: _future,
        builder: (context, snap) {
          if (snap.hasError) return ErrorRetry(error: snap.error!, onRetry: _reload);
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final o = snap.data!;
          final months = <DateTime, List<OutlookDay>>{};
          for (final d in o.days) {
            months.putIfAbsent(DateTime(d.date.year, d.date.month), () => []).add(d);
          }
          return RefreshIndicator(
            onRefresh: () async => _reload(),
            child: ListView(padding: const EdgeInsets.all(16), children: [
              Text(tr(context, widget.advisory ? 'when_climb' : 'when_visit'), style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 4),
              Text(widget.advisory ? tr(context, 'when_climb_sub') : tr(context, 'pick_day', {'site': widget.site})),
              const SizedBox(height: 12),
              const _Legend(),
              for (final e in months.entries)
                _MonthGrid(
                  month: e.key,
                  days: e.value,
                  issue: o.issueDate,
                  open: (day, info) => widget.advisory ? StartTimesScreen(day: day, outlookDay: info) : DayScreen(day: day, outlookDay: info),
                ),
              BasisNote(o.disclaimer),
            ]),
          );
        },
      );
}

class _Legend extends StatelessWidget {
  const _Legend();

  @override
  Widget build(BuildContext context) => Wrap(spacing: 12, runSpacing: 4, children: [
        for (var l = 1; l <= 5; l++)
          Row(mainAxisSize: MainAxisSize.min, children: [
            Container(width: 14, height: 14, decoration: BoxDecoration(color: C4Colors.level(l), borderRadius: BorderRadius.circular(3))),
            const SizedBox(width: 4),
            Text(crowdLabel(context, l), style: Theme.of(context).textTheme.bodySmall),
          ]),
      ]);
}

typedef DayPage = Widget Function(DateTime day, OutlookDay info);

class _MonthGrid extends StatelessWidget {
  const _MonthGrid({required this.month, required this.days, required this.issue, required this.open});

  final DateTime month;
  final List<OutlookDay> days;
  final DateTime issue;
  final DayPage open;

  @override
  Widget build(BuildContext context) {
    final byDay = {for (final d in days) d.date.day: d};
    final first = DateTime(month.year, month.month, 1);
    final lead = first.weekday - 1; // Monday first
    final nDays = DateTime(month.year, month.month + 1, 0).day;
    final cells = <Widget>[
      for (final w in ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'])
        Center(child: Text(w, style: Theme.of(context).textTheme.labelSmall)),
      for (var i = 0; i < lead; i++) const SizedBox.shrink(),
      for (var d = 1; d <= nDays; d++) _DayCell(day: DateTime(month.year, month.month, d), info: byDay[d], open: open),
    ];
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(DateFormat('MMMM yyyy').format(month), style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        GridView.count(
          crossAxisCount: 7,
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          mainAxisSpacing: 4,
          crossAxisSpacing: 4,
          children: cells,
        ),
      ]),
    );
  }
}

class _DayCell extends StatelessWidget {
  const _DayCell({required this.day, required this.info, required this.open});

  final DateTime day;
  final OutlookDay? info;
  final DayPage open;

  @override
  Widget build(BuildContext context) {
    if (info == null) {
      return Center(child: Text('${day.day}', style: TextStyle(color: Theme.of(context).disabledColor)));
    }
    final c = C4Colors.level(info!.crowdLevel);
    return Semantics(
      button: true,
      label: '${niceDate(day)}, ${crowdLabel(context, info!.crowdLevel)}',
      child: InkWell(
        borderRadius: BorderRadius.circular(8),
        onTap: () => Navigator.of(context).push(c4Route(context, open(day, info!))),
        child: Ink(
          decoration: BoxDecoration(color: c, borderRadius: BorderRadius.circular(8)),
          child: Center(
            child: Text('${day.day}', style: TextStyle(color: C4Colors.onColor(c), fontWeight: FontWeight.bold)),
          ),
        ),
      ),
    );
  }
}
