import 'package:flutter/material.dart';

import '../../data/api_client.dart';
import '../../models/models.dart';
import 'c4_ui.dart';

/// K4: guided treks need a permit and a guide. Places left per trek; request one for the group and get a code.
class PermitCard extends StatefulWidget {
  const PermitCard({super.key, required this.day, required this.data});

  final DateTime day;
  final PermitDay data;

  @override
  State<PermitCard> createState() => _PermitCardState();
}

class _PermitCardState extends State<PermitCard> {
  late String _trek = widget.data.treks.first.trail;
  int _size = 4;
  String? _code, _error;
  List<Alternative> _alts = const [];

  Future<void> _request() async {
    final api = C4Scope.of(context);
    try {
      final code = await api.requestPermit(widget.day, _trek, _size);
      if (mounted) {
        setState(() {
          _code = code;
          _error = null;
          _alts = const [];
        });
      }
    } on ApiException catch (e) {
      if (mounted) {
        setState(() {
          _error = e.message;
          _alts = e.alternatives;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final t = widget.data.treks.firstWhere((x) => x.trail == _trek);
    return Card(
      key: const Key('permit_card'),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(tr(context, 'permit_title'), style: text.titleMedium),
          const SizedBox(height: 4),
          Wrap(spacing: 6, runSpacing: 6, children: [
            for (final x in widget.data.treks)
              ChoiceChip(
                key: Key('trek_${x.trail}'),
                label: Text(x.name),
                selected: _trek == x.trail,
                onSelected: (_) => setState(() {
                  _trek = x.trail;
                  _code = null;
                }),
              ),
          ]),
          const SizedBox(height: 4),
          Text(t.left > 0
              ? tr(context, t.left == 1 ? 'permit_places_one' : 'permit_places',
                  {'guides': t.left, 'people': t.peopleLeft, 'hours': t.walkH.toStringAsFixed(1)})
              : tr(context, 'permit_full'), key: const Key('permit_places')),
          Row(children: [
            Text(tr(context, 'group_size')),
            const Spacer(),
            IconButton(onPressed: _size > 1 ? () => setState(() => _size--) : null, icon: const Icon(Icons.remove)),
            Text('$_size', key: const Key('permit_size'), style: text.titleMedium),
            IconButton(onPressed: _size < t.maxGroup ? () => setState(() => _size++) : null, icon: const Icon(Icons.add)),
          ]),
          if (_code == null)
            FilledButton.icon(
              key: const Key('permit_request'),
              onPressed: t.left > 0 && t.peopleLeft >= _size ? _request : null,
              icon: const Icon(Icons.badge_outlined),
              label: Text(tr(context, 'permit_request', {'n': _size})),
            )
          else
            Text(tr(context, 'permit_code', {'code': _code!, 'entry': t.entry}),
                key: const Key('permit_code'), style: text.titleSmall?.copyWith(color: C4Colors.green)),
          if (_error != null) Text(_error!, style: text.bodyMedium?.copyWith(color: C4Colors.red)),
          for (final a in _alts)
            Text(tr(context, 'try_alt', {
              'trek': widget.data.treks.where((x) => x.trail == a.trail).firstOrNull?.name ?? a.trail,
              'day': shortDate(a.day),
            }),
                style: text.bodySmall),
          const SizedBox(height: 4),
          Text(tr(context, 'permit_rule'),
              style: text.bodySmall),
        ]),
      ),
    );
  }
}

/// K6: open viewpoints (no ticket): when they get busy, the car park, and when to come instead.
class ViewpointCard extends StatelessWidget {
  const ViewpointCard({super.key, required this.viewpoints});

  final List<ViewpointInfo> viewpoints;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    Color color(String l) => switch (l) { 'crowded' => C4Colors.red, 'busy' => C4Colors.amber, _ => C4Colors.green };
    return Card(
      key: const Key('viewpoint_card'),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(tr(context, 'viewpoints_title'), style: text.titleMedium),
          for (final v in viewpoints)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: Icon(Icons.landscape_outlined, color: color(v.level)),
              title: Text('${v.name} · ${tr(context, 'vp_${v.level}')}'),
              subtitle: Text([
                v.advice,
                if (v.reported != null) tr(context, 'ranger_today', {'report': v.reported!}),
                if (v.parkingSpaces != null) tr(context, 'car_park', {'n': v.parkingSpaces!}),
              ].join(' ')),
            ),
        ]),
      ),
    );
  }
}

/// K7: campsites on the treks - pitches left for the night; book a pitch and get a code.
class CampsiteCard extends StatefulWidget {
  const CampsiteCard({super.key, required this.night, required this.sites});

  final DateTime night;
  final List<Campsite> sites;

  @override
  State<CampsiteCard> createState() => _CampsiteCardState();
}

class _CampsiteCardState extends State<CampsiteCard> {
  final Map<String, String> _codes = {};

  Future<void> _book(Campsite s) async {
    final api = C4Scope.of(context);
    try {
      final code = await api.bookCampsite(widget.night, s.site, 1, 4);
      if (mounted) setState(() => _codes[s.site] = code);
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Card(
      key: const Key('campsite_card'),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(tr(context, 'campsites_title'), style: text.titleMedium),
          for (final s in widget.sites)
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.cabin_outlined),
              title: Text(s.name),
              subtitle: Text(_codes[s.site] != null
                  ? tr(context, 'pitch_booked', {'code': _codes[s.site]!})
                  : tr(context, 'pitches_left', {'left': s.left, 'total': s.pitches, 'trail': s.trailName})),
              trailing: _codes[s.site] == null && s.left > 0
                  ? TextButton(key: Key('camp_${s.site}'), onPressed: () => _book(s), child: Text(tr(context, 'book_pitch')))
                  : null,
            ),
        ]),
      ),
    );
  }
}
