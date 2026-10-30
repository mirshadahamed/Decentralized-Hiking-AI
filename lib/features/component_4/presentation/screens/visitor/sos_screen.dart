import 'dart:async';
import 'dart:math';

import 'package:flutter/material.dart';

import '../../../data/api_client.dart';
import '../../../models/models.dart';
import '../../theme/c4_theme.dart';
import '../../widgets/c4_ui.dart';

/// A GPS fix from the phone, or null when there is none.
typedef C4Locate = Future<({double lat, double lon, double accuracy})?> Function();

/// §6.2.7 SOS: the visitor says what happened and where; the park's rangers see it at once (POST /sos).
/// Without a connection the call is re-sent every 20 s with the same id (one call, never several).
class SosScreen extends StatefulWidget {
  const SosScreen({super.key, this.locate});

  /// GPS: the team app passes a location service here (e.g. the geolocator package); without one the visitor
  /// chooses the trail and the last place passed.
  final C4Locate? locate;

  @override
  State<SosScreen> createState() => _SosScreenState();
}

class _SosScreenState extends State<SosScreen> {
  static const _kinds = ['injury', 'lost', 'unwell', 'other'];
  final _id = 'sos-${DateTime.now().microsecondsSinceEpoch}-${Random().nextInt(1 << 30)}';
  final _note = TextEditingController();
  String _kind = 'injury';
  int _people = 1;
  List<SegmentInfo> _segments = const [];
  String? _trail;
  int? _segId;
  SosStatus? _sent;
  bool _offline = false, _busy = false;
  Timer? _retry;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_segments.isEmpty) {
      C4Scope.of(context).segments().then((s) {
        if (mounted) setState(() => _segments = s);
      }, onError: (_) {});
    }
  }

  @override
  void dispose() {
    _retry?.cancel();
    _note.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final api = C4Scope.of(context);
    setState(() => _busy = true);
    final fix = widget.locate == null ? null : await widget.locate!().catchError((_) => null);
    try {
      final r = await api.sos(_id, _kind, _people, note: _note.text.trim(), trail: _trail, segId: _segId,
          lat: fix?.lat, lon: fix?.lon, accuracy: fix?.accuracy);
      _retry?.cancel();
      _retry = null;
      if (mounted) {
        setState(() {
          _sent = r;
          _offline = _busy = false;
        });
      }
    } on ApiException {
      if (!mounted) return;
      setState(() {
        _offline = true;
        _busy = false;
      });
      _retry ??= Timer.periodic(const Duration(seconds: 20), (_) => _send());
    }
  }

  Future<void> _check() async {
    try {
      final r = await C4Scope.of(context).sosCheck(_id);
      if (mounted) setState(() => _sent = r);
    } on ApiException {
      if (mounted) setState(() => _offline = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final trails = {for (final s in _segments) s.trail: s.trailName};
    final places = [for (final s in _segments) if (s.trail == _trail) s];
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'sos_title'))),
      body: ListView(padding: C4Space.page, children: [
        Wrap(spacing: C4Space.s, children: [
          for (final k in _kinds)
            ChoiceChip(
              key: Key('sos_$k'),
              label: Text(tr(context, 'sos_kind_$k')),
              selected: _kind == k,
              onSelected: (_) => setState(() => _kind = k),
            ),
        ]),
        Row(children: [
          Expanded(child: Text(tr(context, 'sos_people', {'n': _people}))),
          IconButton(onPressed: _people > 1 ? () => setState(() => _people--) : null, icon: const Icon(Icons.remove)),
          IconButton(onPressed: _people < 40 ? () => setState(() => _people++) : null, icon: const Icon(Icons.add)),
        ]),
        Text(tr(context, widget.locate != null ? 'sos_gps' : 'sos_no_gps'), style: text.bodySmall),
        DropdownButton<String>(
          key: const Key('sos_trail'),
          isExpanded: true,
          hint: Text(tr(context, 'sos_trail')),
          value: _trail,
          items: [for (final e in trails.entries) DropdownMenuItem(value: e.key, child: Text(e.value))],
          onChanged: (v) => setState(() {
            _trail = v;
            _segId = null;
          }),
        ),
        if (places.isNotEmpty)
          DropdownButton<int>(
            key: const Key('sos_place'),
            isExpanded: true,
            hint: Text(tr(context, 'sos_place')),
            value: _segId,
            items: [for (final s in places) DropdownMenuItem(value: s.segId, child: Text(s.name))],
            onChanged: (v) => setState(() => _segId = v),
          ),
        TextField(
          controller: _note,
          maxLength: 200,
          decoration: InputDecoration(labelText: tr(context, 'sos_note')),
        ),
        const SizedBox(height: C4Space.s),
        FilledButton.icon(
          key: const Key('sos_send'),
          style: FilledButton.styleFrom(backgroundColor: C4Colors.red),
          onPressed: _busy ? null : _send,
          icon: const Icon(Icons.sos),
          label: Text(tr(context, 'sos_send')),
        ),
        if (_offline) ...[
          const SizedBox(height: C4Space.s),
          Text(tr(context, 'sos_offline'), key: const Key('sos_offline'), style: text.bodyMedium?.copyWith(color: C4Colors.red)),
        ],
        if (_sent != null) ...[
          const SizedBox(height: C4Space.m),
          Text(tr(context, 'sos_sent', {'place': _sent!.place}), style: text.titleSmall),
          Text(_sent!.note, key: const Key('sos_reply')),
          TextButton(onPressed: _check, child: Text(tr(context, 'sos_check'))),
        ],
      ]),
    );
  }
}
