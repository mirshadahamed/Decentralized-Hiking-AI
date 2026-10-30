import 'dart:async';

import 'package:flutter/material.dart';

import '../../../data/api_client.dart';
import '../../../models/models.dart';
import '../../widgets/c4_ui.dart';

/// §6.2.7: the day's SOS calls for rangers, open ones first; "On the way" tells the visitor a ranger saw it.
/// Refreshes every 30 s.
class SosCallsScreen extends StatefulWidget {
  const SosCallsScreen({super.key, required this.day});

  final DateTime day;

  @override
  State<SosCallsScreen> createState() => _SosCallsScreenState();
}

class _SosCallsScreenState extends State<SosCallsScreen> {
  late Future<List<SosCall>> _calls;
  Timer? _timer;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _calls = C4Scope.of(context).sosCalls(widget.day);
    _timer ??= Timer.periodic(const Duration(seconds: 30), (_) => _reload());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  void _reload() {
    if (!mounted) return;
    setState(() {
      _calls = C4Scope.of(context).sosCalls(widget.day);
    });
  }

  Future<void> _set(SosCall c, String status) async {
    try {
      await C4Scope.of(context).sosStatus(c.id, status);
      _reload();
    } on ApiException catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('SOS calls'), actions: [IconButton(onPressed: _reload, icon: const Icon(Icons.refresh))]),
        body: FutureBuilder<List<SosCall>>(
          future: _calls,
          builder: (context, snap) {
            if (snap.hasError) return ErrorRetry(error: snap.error!, onRetry: _reload);
            if (!snap.hasData) return const Center(child: CircularProgressIndicator());
            final calls = snap.data!;
            if (calls.isEmpty) return const Center(child: Text('No SOS calls today.'));
            return ListView(children: [
              for (final c in calls)
                ListTile(
                  key: Key('sos_call_${c.id}'),
                  leading: Icon(Icons.sos, color: c.status == 'closed' ? null : C4Colors.red),
                  title: Text('${c.kind[0].toUpperCase()}${c.kind.substring(1)} · ${c.people} '
                      '${c.people == 1 ? 'person' : 'people'} · ${c.place}'),
                  subtitle: Text([
                    'At ${c.created.length >= 16 ? c.created.substring(11, 16) : c.created}',
                    if (c.lat != null) 'GPS ${c.lat!.toStringAsFixed(5)}, ${c.lon!.toStringAsFixed(5)}'
                        '${c.accuracy != null ? ' (±${c.accuracy!.round()} m)' : ''}',
                    if (c.note != null && c.note!.isNotEmpty) '"${c.note}"',
                    if (c.status == 'seen') 'On the way: ${c.handledBy ?? ''}',
                    if (c.status == 'closed') 'Closed',
                  ].join(' · ')),
                  trailing: switch (c.status) {
                    'open' => FilledButton(key: Key('sos_seen_${c.id}'), onPressed: () => _set(c, 'seen'), child: const Text('On the way')),
                    'seen' => OutlinedButton(key: Key('sos_close_${c.id}'), onPressed: () => _set(c, 'closed'), child: const Text('Close')),
                    _ => null,
                  },
                ),
            ]);
          },
        ),
      );
}
