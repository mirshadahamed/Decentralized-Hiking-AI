import 'dart:async';

import 'package:flutter/material.dart';

import '../../../data/api_client.dart';
import '../../../models/models.dart';
import '../../l10n/c4_i18n.dart';
import '../../theme/c4_theme.dart';
import '../../widgets/c4_ui.dart';

/// §6.1.2 remedy: a tablet at the gate where walk-up visitors without the app take a start time themselves
/// (GET /start-time, POST /start-time). Large text, three languages, no login for the visitor; a ranger opens it
/// and leaves it with a long press on the lock. After [resetAfter] the screen is cleared for the next visitor.
class KioskScreen extends StatefulWidget {
  const KioskScreen({super.key, required this.now, this.resetAfter = const Duration(seconds: 45)});

  final DateTime Function() now;
  final Duration resetAfter;

  @override
  State<KioskScreen> createState() => _KioskScreenState();
}

class _KioskScreenState extends State<KioskScreen> {
  late Future<List<TrailInfo>> _trails;
  String? _trail;
  int _size = 2;
  bool _busy = false;
  String? _slot, _code, _error;
  bool _full = false;
  Timer? _reset;

  Future<List<TrailInfo>> _load() async {
    final api = C4Scope.of(context);
    final r = await Future.wait([api.status(), api.trails()]);
    final status = r[0] as ServerStatus;
    return [for (final t in r[1] as List<TrailInfo>) if (status.ticketed(t.id)) t];
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _trails = _load();
  }

  @override
  void dispose() {
    _reset?.cancel();
    super.dispose();
  }

  void _clear() {
    _reset?.cancel();
    setState(() {
      _trail = null;
      _size = 2;
      _slot = _code = _error = null;
      _full = false;
    });
  }

  Future<void> _get() async {
    final api = C4Scope.of(context);
    final now = widget.now();
    final day = DateTime(now.year, now.month, now.day);
    final wanted = '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}';
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final s = await api.startTime(day, _trail!, wanted, _size);
      final slot = s.suggested;
      final code = slot == null ? null : await api.holdStartTime(day, _trail!, slot, _size);
      if (!mounted) return;
      setState(() {
        _slot = slot;
        _code = code;
        _full = slot == null;
        _busy = false;
      });
      _reset?.cancel();
      _reset = Timer(widget.resetAfter, () {
        if (mounted) _clear();
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _error = e.message;
        _busy = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    final lang = C4Scope.langOf(context);
    return PopScope(
      canPop: false, // visitors cannot leave the kiosk; the ranger long-presses the lock
      child: Scaffold(
        appBar: AppBar(
          automaticallyImplyLeading: false,
          title: Text(tr(context, 'kiosk_title')),
          actions: [
            if (lang != null)
              for (final e in C4Lang.languages.entries)
                Padding(
                  padding: const EdgeInsets.only(right: C4Space.xs),
                  child: ChoiceChip(label: Text(e.value), selected: lang.code == e.key, onSelected: (_) => lang.set(e.key)),
                ),
            GestureDetector(
              key: const Key('kiosk_exit'),
              onLongPress: () => Navigator.of(context).pop(),
              child: const Padding(padding: EdgeInsets.all(C4Space.m), child: Icon(Icons.lock_outline)),
            ),
          ],
        ),
        body: FutureBuilder<List<TrailInfo>>(
          future: _trails,
          builder: (context, snap) {
            if (snap.hasError) return ErrorRetry(error: snap.error!, onRetry: () => setState(() { _trails = _load(); }));
            if (!snap.hasData) return const Center(child: CircularProgressIndicator());
            final trails = snap.data!;
            if (_slot != null || _full) {
              return ListView(padding: C4Space.page, children: [
                if (_slot != null) ...[
                  Text(tr(context, 'kiosk_start', {'time': _slot!}),
                      key: const Key('kiosk_slot'), style: text.displayMedium?.copyWith(fontWeight: FontWeight.w700)),
                  const SizedBox(height: C4Space.m),
                  SelectableText(_code ?? '', key: const Key('kiosk_code'), style: text.displayLarge?.copyWith(letterSpacing: 6)),
                  const SizedBox(height: C4Space.s),
                  Text(tr(context, 'kiosk_code', {'code': _code ?? '', 'time': _slot!}), style: text.titleMedium),
                ] else
                  Text(tr(context, 'kiosk_full'), key: const Key('kiosk_full'), style: text.headlineSmall?.copyWith(color: C4Colors.red)),
                const SizedBox(height: C4Space.l),
                FilledButton(key: const Key('kiosk_next'), onPressed: _clear, child: Text(tr(context, 'kiosk_next'))),
              ]);
            }
            return ListView(padding: C4Space.page, children: [
              Text(tr(context, 'kiosk_trail'), style: text.headlineSmall),
              const SizedBox(height: C4Space.s),
              Wrap(spacing: C4Space.s, runSpacing: C4Space.s, children: [
                for (final t in trails)
                  ChoiceChip(
                    key: Key('kiosk_trail_${t.id}'),
                    label: Padding(padding: const EdgeInsets.all(C4Space.s), child: Text(t.name, style: text.titleMedium)),
                    selected: _trail == t.id,
                    onSelected: (_) => setState(() => _trail = t.id),
                  ),
              ]),
              const SizedBox(height: C4Space.l),
              Row(children: [
                Expanded(child: Text(tr(context, 'kiosk_people', {'n': _size}), style: text.headlineSmall)),
                IconButton.filledTonal(
                    iconSize: 36, onPressed: _size > 1 ? () => setState(() => _size--) : null, icon: const Icon(Icons.remove)),
                const SizedBox(width: C4Space.s),
                IconButton.filledTonal(
                    key: const Key('kiosk_more'),
                    iconSize: 36,
                    onPressed: _size < 20 ? () => setState(() => _size++) : null,
                    icon: const Icon(Icons.add)),
              ]),
              const SizedBox(height: C4Space.l),
              FilledButton(
                key: const Key('kiosk_get'),
                style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(64)),
                onPressed: _trail == null || _busy ? null : _get,
                child: Text(tr(context, 'kiosk_get'), style: text.titleLarge?.copyWith(color: Colors.white)),
              ),
              if (_error != null) ...[
                const SizedBox(height: C4Space.s),
                Text(_error!, style: text.bodyLarge?.copyWith(color: C4Colors.red)),
              ],
              const SizedBox(height: C4Space.l),
              Text(tr(context, 'kiosk_sms'), style: text.bodyMedium),
            ]);
          },
        ),
      ),
    );
  }
}
