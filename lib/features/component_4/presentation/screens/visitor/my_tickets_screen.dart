import 'package:flutter/material.dart';

import '../../../models/models.dart';
import '../../../services/ticket_store.dart';
import '../../widgets/c4_ui.dart';
import 'ticket_screen.dart';

/// Tickets saved on this phone. Pull down to update their status when online.
class MyTicketsScreen extends StatefulWidget {
  const MyTicketsScreen({super.key});

  @override
  State<MyTicketsScreen> createState() => _MyTicketsScreenState();
}

class _MyTicketsScreenState extends State<MyTicketsScreen> {
  late Future<List<Booking>> _future = TicketStore().all();

  Future<void> _sync() async {
    final api = C4Scope.of(context);
    final store = TicketStore();
    for (final b in await store.all()) {
      try {
        await store.save(await api.booking(b.code));
      } catch (_) {
        // offline: keep the saved copy
      }
    }
    setState(() { _future = store.all(); });
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<List<Booking>>(
        future: _future,
        builder: (context, snap) {
          final list = snap.data ?? [];
          return RefreshIndicator(
            onRefresh: _sync,
            child: list.isEmpty
                ? ListView(children: const [
                    SizedBox(height: 120),
                    Icon(Icons.confirmation_number_outlined, size: 56),
                    SizedBox(height: 12),
                    Center(child: Text('No tickets yet. Book a visit in "Plan & book".')),
                  ])
                : ListView(padding: const EdgeInsets.all(16), children: [
                    for (final b in list)
                      Card(
                        child: ListTile(
                          leading: const Icon(Icons.qr_code_2, size: 36),
                          title: Text('${niceDate(b.day)} · ${b.slot}'),
                          subtitle: Text('${b.groupSize} people · ${b.status} · ${b.code}'),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: () async {
                            await Navigator.of(context).push(c4Route(context, TicketScreen(booking: b)));
                            setState(() { _future = TicketStore().all(); });
                          },
                        ),
                      ),
                  ]),
          );
        },
      );
}
