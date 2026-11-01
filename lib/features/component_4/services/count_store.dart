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

  // ---------- N5: hand counts to another phone without a signal (QR code) ----------
  static const sharePrefix = 'C4COUNTS1:';
  static const shareMax = 40; // ~2 KB: a QR code a phone camera reads easily

  /// The waiting counts as the text of one QR code (at most [shareMax]; the oldest first).
  static String shareCode(List<SpotCount> counts) => sharePrefix +
      base64Url.encode(utf8.encode(jsonEncode([
        for (final c in counts.take(shareMax))
          [c.toJson()['day'], c.segId, c.time, c.count, c.clientId]
      ])));

  /// Add counts read from another phone's QR code to this phone's queue; ones already here are skipped.
  /// Whichever phone gets a signal first sends them; the server keeps each count once (by its id).
  /// Returns how many were new. Throws [FormatException] for a QR code that is not a count share.
  Future<int> receive(String code) async {
    if (!code.startsWith(sharePrefix)) throw const FormatException('Not a count share from the ranger app');
    final rows = jsonDecode(utf8.decode(base64Url.decode(code.substring(sharePrefix.length)))) as List;
    final have = {for (final c in await pending()) c.clientId};
    final add = [
      for (final r in rows.cast<List>())
        if (!have.contains(r[4]))
          SpotCount.fromJson({'day': r[0], 'seg_id': r[1], 'time': r[2], 'count': r[3], 'client_id': r[4]})
    ];
    await _write([...await pending(), ...add]);
    return add.length;
  }

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
