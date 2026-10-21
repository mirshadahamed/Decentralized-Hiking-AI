import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../data/api_client.dart';
import '../domain/edge_forecaster.dart';

/// Keeps the last downloaded edge pack on the device, so tomorrow's forecast can be computed without internet.
class EdgeStore {
  static String _key(String? park) => 'c4_edge_pack_${park ?? 'default'}';

  /// Download a fresh pack if possible (and keep it); otherwise use the last one kept on this device.
  /// Returns null when there has never been a pack.
  static Future<(EdgeForecaster, bool)?> load(C4Api api) async {
    final prefs = await SharedPreferences.getInstance();
    try {
      final pack = await api.edgePack();
      await prefs.setString(_key(api.park), jsonEncode(pack));
      return (EdgeForecaster.fromPack(pack), false);
    } on ApiException {
      final saved = prefs.getString(_key(api.park));
      if (saved == null) return null;
      return (EdgeForecaster.fromPack(jsonDecode(saved) as Map<String, dynamic>), true); // offline copy
    } on FormatException {
      return null; // a pack from a newer server version
    }
  }

  /// For Module 3 (safety assistant): Component 4's feed (schema c4-module3-feed-1,
  /// research/component_4/docs/schema/) for tomorrow - people per segment and hour, what each segment holds,
  /// the hours to avoid, safe numbers. Read from the pack kept on the phone, so it also works with no signal.
  static Future<Map<String, dynamic>?> module3Feed(C4Api api) async =>
      (await load(api))?.$1.pack['module3_feed'] as Map<String, dynamic>?;
}
