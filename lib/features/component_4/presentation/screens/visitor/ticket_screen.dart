import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../../../data/api_client.dart';
import '../../../models/models.dart';
import '../../../services/ticket_store.dart';
import '../../widgets/c4_ui.dart';


/// Step 3: the ticket. Shown from the phone's memory, so it works without a signal at the gate.
class TicketScreen extends StatelessWidget {
  const TicketScreen({super.key, required this.booking, this.justBooked = false});

  final Booking booking;
  final bool justBooked;

  Future<void> _cancel(BuildContext context) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (d) => AlertDialog(
        title: const Text('Cancel this booking?'),
        content: const Text('Your places will be offered to other visitors.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(d, false), child: const Text('Keep it')),
          FilledButton(onPressed: () => Navigator.pop(d, true), child: const Text('Cancel booking')),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    try {
      await C4Scope.of(context).cancel(booking.code);
      await TicketStore().remove(booking.code);
      if (context.mounted) Navigator.of(context).pop();
    } on ApiException catch (e) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.message)));
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = DateFormat.Hm();
    return Scaffold(
      appBar: AppBar(title: const Text('Your ticket')),
      body: ListView(padding: const EdgeInsets.all(24), children: [
        if (justBooked)
          const Card(
            color: Color(0xFFE6F4EA),
            child: ListTile(leading: Icon(Icons.check_circle, color: C4Colors.green), title: Text('Booked! The ticket is saved on this phone.')),
          ),
        const SizedBox(height: 16),
        Center(
          child: Container(
            padding: const EdgeInsets.all(12),
            color: Colors.white,
            child: QrImageView(data: booking.code, size: 220, semanticsLabel: 'Ticket QR code ${booking.code}'),
          ),
        ),
        const SizedBox(height: 12),
        Center(child: SelectableText(booking.code, style: Theme.of(context).textTheme.headlineMedium?.copyWith(letterSpacing: 4))),
        const SizedBox(height: 24),
        _row(context, Icons.hiking, booking.trailName ?? booking.trail),
        _row(context, Icons.event, niceDate(booking.day)),
        _row(context, Icons.groups, '${booking.groupSize} people'),
        _row(context, Icons.login, 'Show this at the gate between ${t.format(booking.gateOpens)} and ${t.format(booking.gateCloses)}'),
        if (booking.status != 'booked') _row(context, Icons.info, 'Status: ${booking.status}'),
        const SizedBox(height: 24),
        if (booking.status == 'booked')
          OutlinedButton.icon(onPressed: () => _cancel(context), icon: const Icon(Icons.close), label: const Text('Cancel booking')),
      ]),
    );
  }

  Widget _row(BuildContext context, IconData icon, String text) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(children: [Icon(icon), const SizedBox(width: 12), Expanded(child: Text(text, style: Theme.of(context).textTheme.titleMedium))]),
      );
}
