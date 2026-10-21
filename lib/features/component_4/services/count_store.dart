import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../data/api_client.dart';
import '../models/models.dart';

/// Spot counts waiting to be sent: a ranger counts on the trail without a signal, the phone sends them when it
/// can. Each count has its own id, so sending one twice stores it once on the server.
class CountStore {
  static const _key = 'c4_pending_counts';

  Future<List<SpotCount>> pending() async {
    final p = await SharedPreferences.getInstance();
    return [for (final s in p.getStringList(_key) ?? []) SpotCount.fromJson(jsonDecode(s) as Map<String, dynamic>)];
  }

  Future<void> _write(List<SpotCount> list) async {
    final p = await SharedPreferences.getInstance();
    await p.setStringList(_key, [for (final c in list) jsonEncode(c.toJson())]);
  }

  Future<void> add(SpotCount c) async => _write([...await pending(), c]);

  /// Send what is waiting. Returns (sent, still waiting). Stops at the first network failure;
  /// a count the server rejects (e.g. unknown section) is dropped so it does not block the others.
  Future<(int, int)> sync(C4Api api) async {
    final left = <SpotCount>[];
    var sent = 0;
    var offline = false;
    for (final c in await pending()) {
      if (offline) {
        left.add(c);
        continue;
      }
      try {
        await api.addCount(c);
        sent++;
      } on ApiException catch (e) {
        if (e.statusCode == 0 || e.statusCode >= 500) {
          offline = true;
          left.add(c);
        }
      }
    }
    await _write(left);
    return (sent, left.length);
  }
}
