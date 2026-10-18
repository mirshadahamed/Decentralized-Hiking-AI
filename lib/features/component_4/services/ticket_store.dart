import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../models/models.dart';

/// Tickets saved on the phone, so they can be shown at the gate without a signal (offline-first).
class TicketStore {
  static const _key = 'c4_tickets';

  Future<List<Booking>> all() async {
    final p = await SharedPreferences.getInstance();
    return (p.getStringList(_key) ?? [])
        .map((s) => Booking.fromJson(jsonDecode(s) as Map<String, dynamic>))
        .toList()
      ..sort((a, b) => a.slotStart.compareTo(b.slotStart));
  }

  Future<void> save(Booking b) async {
    final p = await SharedPreferences.getInstance();
    final list = (await all()).where((x) => x.code != b.code).toList()..add(b);
    await p.setStringList(_key, list.map((x) => jsonEncode(x.toJson())).toList());
  }

  Future<void> remove(String code) async {
    final p = await SharedPreferences.getInstance();
    final list = (await all()).where((x) => x.code != code).toList();
    await p.setStringList(_key, list.map((x) => jsonEncode(x.toJson())).toList());
  }
}
