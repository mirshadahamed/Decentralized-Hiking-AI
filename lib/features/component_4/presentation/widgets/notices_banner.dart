import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../models/models.dart';
import '../theme/c4_theme.dart';
import 'c4_ui.dart';

/// §6.2.9 without push: the day's notices (closures, trail conditions, heavy rain; GET /notices/{day}), checked
/// when the park opens and every [every] while it stays open. Each notice is shown until the visitor taps OK;
/// dismissed ids are kept on the device. No connection: nothing is shown.
class NoticesBanner extends StatefulWidget {
  const NoticesBanner({super.key, required this.day, this.every = const Duration(minutes: 5)});

  final DateTime day;
  final Duration every;

  @override
  State<NoticesBanner> createState() => _NoticesBannerState();
}

class _NoticesBannerState extends State<NoticesBanner> {
  static const _key = 'c4_seen_notices';
  List<ParkNotice> _notices = const [];
  Set<String> _seen = {};
  Timer? _timer;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_timer == null) {
      SharedPreferences.getInstance().then((p) {
        if (mounted) setState(() => _seen = (p.getStringList(_key) ?? const []).toSet());
      });
      _load();
      _timer = Timer.periodic(widget.every, (_) => _load());
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final n = await C4Scope.of(context).notices(widget.day);
      if (mounted) setState(() => _notices = n);
    } catch (_) {
      // offline or an older server: no notices
    }
  }

  Future<void> _dismiss(ParkNotice n) async {
    setState(() => _seen = {..._seen, n.id});
    final p = await SharedPreferences.getInstance();
    await p.setStringList(_key, _seen.toList().sublist((_seen.length - 200).clamp(0, _seen.length)));
  }

  @override
  Widget build(BuildContext context) {
    final show = [for (final n in _notices) if (!_seen.contains(n.id)) n];
    if (show.isEmpty) return const SizedBox.shrink();
    final scheme = Theme.of(context).colorScheme;
    return Column(mainAxisSize: MainAxisSize.min, children: [
      for (final n in show)
        Material(
          key: Key('notice_${n.id}'),
          color: n.level == 'info' ? scheme.secondaryContainer : (n.level == 'danger' ? scheme.errorContainer : C4Colors.amber.withValues(alpha: 0.25)),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(C4Space.m, C4Space.xs, C4Space.xs, C4Space.xs),
            child: Row(children: [
              Icon(switch (n.kind) { 'rain' => Icons.thunderstorm_outlined, 'closure' => Icons.block, _ => Icons.warning_amber },
                  color: n.level == 'danger' ? C4Colors.red : null),
              const SizedBox(width: C4Space.s),
              Expanded(child: Text(n.text)),
              TextButton(onPressed: () => _dismiss(n), child: const Text('OK')),
            ]),
          ),
        ),
    ]);
  }
}
