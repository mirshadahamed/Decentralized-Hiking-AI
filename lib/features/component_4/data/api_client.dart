import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import '../models/models.dart';

/// Base URL of the Component 4 API. Override at build time:
///   flutter run --dart-define=C4_API=http://10.0.2.2:8000     (Android emulator -> host PC)
const String kC4ApiUrl = String.fromEnvironment('C4_API', defaultValue: 'http://localhost:8000');

class ApiException implements Exception {
  ApiException(this.statusCode, this.message, {this.alternatives = const []});

  final int statusCode;
  final String message;
  final List<Alternative> alternatives; // filled when a slot is full (409)

  bool get isFull => statusCode == 409;

  @override
  String toString() => message;
}

/// All calls to the Component 4 API. Tests replace it with a fake (implements C4Api).
/// With the gateway (python -m src.api.serve_all) several parks share one address: set [park] and every call
/// goes to /parks/{park}/...; without it ([park] null) the calls go straight to a single-park API.
class C4Api {
  C4Api({String? baseUrl, http.Client? client, this.park})
      : baseUrl = baseUrl ?? kC4ApiUrl,
        _http = client ?? http.Client();

  final String baseUrl;
  final http.Client _http;
  StaffSession? session;
  String? park;

  static String day(DateTime d) => d.toIso8601String().substring(0, 10);

  String get _root => park == null ? baseUrl : '$baseUrl/parks/$park';

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        if (session != null) 'Authorization': 'Bearer ${session!.token}',
      };

  /// Offline-first: every successful GET is kept on the device; with no connection the last copy is returned
  /// and [offline] says since when (null = live). The edge pack has its own store (services/edge_store.dart).
  final ValueNotifier<DateTime?> offline = ValueNotifier(null);

  static bool _cacheable(String method, String path) => method == 'GET' && !path.startsWith('/edge/pack');

  Future<SharedPreferences?> _prefs() async {
    try {
      return await SharedPreferences.getInstance();
    } catch (_) {
      return null; // no storage (some tests): just no offline copy
    }
  }

  Future<dynamic> _send(String method, String path,
      {Object? body, Map<String, String>? query, bool gateway = false, String? forPark}) async {
    final root = gateway ? baseUrl : (forPark != null ? '$baseUrl/parks/$forPark' : _root);
    final uri = Uri.parse('$root$path').replace(queryParameters: query);
    final key = 'c4_cache:$uri';
    late http.Response r;
    try {
      switch (method) {
        case 'GET':
          r = await _http.get(uri, headers: _headers);
        case 'POST':
          r = await _http.post(uri, headers: _headers, body: jsonEncode(body ?? {}));
        case 'DELETE':
          r = await _http.delete(uri, headers: _headers);
      }
    } catch (_) {
      if (_cacheable(method, path)) {
        final saved = (await _prefs())?.getString(key);
        if (saved != null) {
          final s = jsonDecode(saved) as Map<String, dynamic>;
          offline.value = DateTime.tryParse(s['t'] as String? ?? '') ?? DateTime.now();
          return jsonDecode(s['b'] as String);
        }
      }
      throw ApiException(0, 'Cannot reach the park server. Check your connection and try again.');
    }
    final decoded = r.body.isEmpty ? null : jsonDecode(utf8.decode(r.bodyBytes));
    if (r.statusCode >= 200 && r.statusCode < 300) {
      offline.value = null;
      if (_cacheable(method, path) && r.body.isNotEmpty) {
        await (await _prefs())
            ?.setString(key, jsonEncode({'t': DateTime.now().toIso8601String(), 'b': utf8.decode(r.bodyBytes)}));
      }
      return decoded;
    }
    var detail = decoded is Map && decoded['detail'] is String ? decoded['detail'] as String : 'Error ${r.statusCode}';
    if (r.statusCode == 404 && detail == 'Not Found') {
      // FastAPI's own 404: the route does not exist, i.e. the server runs older code than this app
      detail = 'The park server does not have this feature yet ($path). Restart the server with the latest code.';
    }
    final alts = decoded is Map && decoded['alternatives'] is List
        ? (decoded['alternatives'] as List).map((a) => Alternative.fromJson(a as Map<String, dynamic>)).toList()
        : <Alternative>[];
    throw ApiException(r.statusCode, detail, alternatives: alts);
  }

  // ---------- gateway ----------
  /// Parks served by the gateway; null when the server is a single-park API (no gateway).
  Future<List<ParkInfo>?> parks() async {
    try {
      return (await _send('GET', '/parks', gateway: true) as List).map((p) => ParkInfo.fromJson(p as Map<String, dynamic>)).toList();
    } on ApiException catch (e) {
      if (e.statusCode == 404) return null;
      rethrow;
    }
  }

  /// Switch park (staff sessions belong to one park).
  void usePark(String? id) {
    if (id != park) session = null;
    park = id;
  }

  // ---------- public ----------
  Future<ServerStatus> status() async => ServerStatus.fromJson(await _send('GET', '/status'));

  /// While online: fetch (and so keep on the device) what the visitor screens need for this park and tomorrow,
  /// so they also open with no connection. Failures are ignored.
  Future<void> prefetch() async {
    try {
      final s = await status();
      final tm = s.today.add(const Duration(days: 1));
      for (final f in <Future<Object?> Function()>[
        destination, outlook, trails, geometry, tomorrow,
        if (s.isAdvisory) () => advisory(tm) else ...[() => capacity(tm), () => slots(tm)],
      ]) {
        try {
          await f();
        } catch (_) {}
      }
    } catch (_) {}
  }

  Future<List<MapSegment>> geometry() async => MapSegment.fromGeoJson(await _send('GET', '/trails/geometry') as Map<String, dynamic>);

  /// Trained model + tomorrow's inputs, so the phone can run the forecast itself (domain/edge_forecaster.dart).
  Future<Map<String, dynamic>> edgePack() async => await _send('GET', '/edge/pack') as Map<String, dynamic>;

  /// Safe limit per trail for a day (tomorrow up to 90 days ahead) and what lowered it.
  Future<DayCapacity> capacity(DateTime d) async =>
      DayCapacity.fromJson(await _send('GET', '/capacity/${day(d)}') as Map<String, dynamic>);

  /// Trail conditions reported by officers for a day: {trail: condition}.
  Future<Map<String, TrailCondition>> conditions(DateTime d) async =>
      ((await _send('GET', '/conditions/${day(d)}'))['trails'] as Map<String, dynamic>)
          .map((k, v) => MapEntry(k, TrailCondition.fromJson(v as Map<String, dynamic>)));

  Future<StartAdvice> advisory(DateTime d) async => StartAdvice.fromJson(await _send('GET', '/advisory/${day(d)}'));

  /// 90-day outlook of the current park, or of [forPark] (destination cards, without switching park).
  Future<Outlook> outlook({String? forPark}) async => Outlook.fromJson(await _send('GET', '/outlook', forPark: forPark));

  Future<ParkInfo> destination() async => ParkInfo.fromJson(await _send('GET', '/destination') as Map<String, dynamic>);

  Future<List<TrailInfo>> trails() async =>
      (await _send('GET', '/trails') as List).map((t) => TrailInfo.fromJson(t as Map<String, dynamic>)).toList();

  Future<DayPlan> plan(DateTime d) async => DayPlan.fromPlanJson(await _send('GET', '/plan/${day(d)}'));

  Future<Map<String, dynamic>> tomorrow() async => await _send('GET', '/forecast/tomorrow') as Map<String, dynamic>;

  Future<DaySlots> slots(DateTime d) async => DaySlots.fromJson(await _send('GET', '/slots/${day(d)}'));

  Future<Booking> book(DateTime d, String trail, String slot, int groupSize) async => Booking.fromJson(
      await _send('POST', '/bookings', body: {'day': day(d), 'trail': trail, 'slot': slot, 'group_size': groupSize}));

  Future<Booking> booking(String code) async => Booking.fromJson(await _send('GET', '/bookings/$code'));

  Future<void> cancel(String code) async => _send('DELETE', '/bookings/$code');

  // ---------- staff ----------
  Future<StaffSession> login(String username, String password) async {
    session = StaffSession.fromJson(await _send('POST', '/auth/login', body: {'username': username, 'password': password}));
    return session!;
  }

  Future<void> logout() async {
    try {
      await _send('POST', '/auth/logout');
    } finally {
      session = null;
    }
  }

  Future<CheckInResult> checkIn(String code, {DateTime? at}) async => CheckInResult.fromJson(
      await _send('POST', '/checkin', body: {'code': code, if (at != null) 'at': at.toIso8601String()}));

  Future<List<WalkInSlot>> walkIns(DateTime d) async => ((await _send('GET', '/walkins/${day(d)}'))['slots'] as List)
      .map((s) => WalkInSlot.fromJson(s as Map<String, dynamic>))
      .toList();

  Future<int> sellWalkIn(DateTime d, String trail, String slot, int groupSize, {DateTime? at}) async =>
      ((await _send('POST', '/walkins', body: {
        'day': day(d),
        'trail': trail,
        'slot': slot,
        'group_size': groupSize,
        if (at != null) 'at': at.toIso8601String(),
      }))['left'] as num)
          .round();

  Future<List<LiveSegment>> live(DateTime d, {String? at}) async =>
      ((await _send('GET', '/live/${day(d)}', query: at == null ? null : {'at': at}))['segments'] as List)
          .map((s) => LiveSegment.fromJson(s as Map<String, dynamic>))
          .toList();

  Future<CheckpointStatus> checkpoints(DateTime d, {String? at}) async =>
      CheckpointStatus.fromJson(await _send('GET', '/checkpoints/${day(d)}', query: at == null ? null : {'at': at}));

  /// Halfway check: [count] people passed the checkpoint on [route] (e.g. in the last 10 minutes).
  Future<CheckpointStatus> recordCheckpoint(String route, int count, {DateTime? at}) async => CheckpointStatus.fromJson(
      await _send('POST', '/checkpoints', body: {'route': route, 'count': count, if (at != null) 'at': at.toIso8601String()}));

  /// Pilgrim sites (officer): every night of the outlook with the summit queue and when halfway checks are needed.
  /// Officer records: visitors per day and trail for past, today and future days (trail null = all trails).
  Future<CrowdRecords> records(DateTime start, DateTime end, {String? trail}) async => CrowdRecords.fromJson(
      await _send('GET', '/admin/records', query: {'start': day(start), 'end': day(end), 'trail': ?trail})
          as Map<String, dynamic>);

  Future<List<SeasonNight>> season() async => ((await _send('GET', '/admin/season'))['days'] as List)
      .map((d) => SeasonNight.fromJson(d as Map<String, dynamic>))
      .toList();

  /// Officer: report a trail's condition for a range of days ('good' clears it). Returns affected bookings.
  Future<List<Map<String, dynamic>>> setCondition(String trail, DateTime from, DateTime to, String level, String note) async =>
      ((await _send('POST', '/admin/conditions', body: {
        'trail': trail,
        'day_from': day(from),
        'day_to': day(to),
        'level': level,
        'note': note,
      }))['alerts'] as List)
          .cast<Map<String, dynamic>>();

  Future<List<Map<String, dynamic>>> closeTrail(DateTime d, String trail, String from, String to, String reason) async =>
      ((await _send('POST', '/admin/closures', body: {
        'day': day(d),
        'trail': trail,
        'slot_from': from,
        'slot_to': to,
        'reason': reason,
      }))['alerts'] as List)
          .cast<Map<String, dynamic>>();

  Future<List<Map<String, dynamic>>> alerts() async => (await _send('GET', '/admin/alerts') as List).cast<Map<String, dynamic>>();

  Future<List<Map<String, dynamic>>> dayBookings(DateTime d) async =>
      (await _send('GET', '/admin/bookings/${day(d)}') as List).cast<Map<String, dynamic>>();

  Future<Map<String, dynamic>> refresh() async => await _send('POST', '/admin/refresh') as Map<String, dynamic>;
}
