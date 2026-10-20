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
}
