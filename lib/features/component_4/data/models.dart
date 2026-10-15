// Data models for the Component 4 API (ml/component_4/src/api/app.py).

int _int(dynamic v) => (v as num?)?.round() ?? 0;
double _dbl(dynamic v) => (v as num?)?.toDouble() ?? 0.0;

class OutlookDay {
  OutlookDay({
    required this.date,
    required this.crowdLevel,
    required this.p10,
    required this.p50,
    required this.p90,
    required this.byTrail,
    required this.chanceWetMorning,
    required this.weatherBasis,
  });

  final DateTime date;
  final int crowdLevel; // 1 = quietest 20 % of days ... 5 = busiest 20 %
  final int p10, p50, p90;
  final Map<String, int> byTrail;
  final double chanceWetMorning;
  final String weatherBasis;

  factory OutlookDay.fromJson(Map<String, dynamic> j) => OutlookDay(
        date: DateTime.parse(j['date'] as String),
        crowdLevel: _int(j['crowd_level']),
        p10: _int(j['visitors']['p10']),
        p50: _int(j['visitors']['p50']),
        p90: _int(j['visitors']['p90']),
        byTrail: (j['visitors_by_trail_p50'] as Map<String, dynamic>? ?? {})
            .map((k, v) => MapEntry(k, _int(v))),
        chanceWetMorning: _dbl(j['chance_wet_morning']),
        weatherBasis: j['weather_basis'] as String? ?? 'typical weather',
      );
}

class Outlook {
  Outlook({required this.issueDate, required this.days, required this.trailNames, required this.disclaimer});

  final DateTime issueDate;
  final List<OutlookDay> days;
  final Map<String, String> trailNames;
  final String disclaimer;

  factory Outlook.fromJson(Map<String, dynamic> j) => Outlook(
        issueDate: DateTime.parse(j['issue_date'] as String),
        days: (j['days'] as List).map((d) => OutlookDay.fromJson(d as Map<String, dynamic>)).toList(),
        trailNames: (j['trails'] as Map<String, dynamic>).map((k, v) => MapEntry(k, v as String)),
        disclaimer: j['disclaimer'] as String? ?? '',
      );
}

class TrailInfo {
  TrailInfo({required this.id, required this.name, required this.lengthKm, required this.about});

  final String id, name, about;
  final double lengthKm;

  factory TrailInfo.fromJson(Map<String, dynamic> j) => TrailInfo(
        id: j['id'] as String,
        name: j['name'] as String,
        lengthKm: _dbl(j['length_km']),
        about: j['about'] as String? ?? '',
      );
}

class SlotInfo {
  SlotInfo({required this.slot, required this.trail, required this.placesLeft, required this.bookable, required this.closed});

  final String slot, trail;
  final int placesLeft, bookable;
  final bool closed;

  factory SlotInfo.fromJson(Map<String, dynamic> j) => SlotInfo(
        slot: j['slot'] as String,
        trail: j['trail'] as String,
        placesLeft: _int(j['places_left']),
        bookable: _int(j['bookable']),
        closed: j['closed'] as bool? ?? false,
      );
}

class DaySlots {
  DaySlots({required this.day, required this.basis, required this.slots});

  final DateTime day;
  final String basis;
  final List<SlotInfo> slots;

  List<SlotInfo> forTrail(String trail) => slots.where((s) => s.trail == trail).toList();

  factory DaySlots.fromJson(Map<String, dynamic> j) => DaySlots(
        day: DateTime.parse(j['day'] as String),
        basis: j['basis'] as String? ?? '',
        slots: (j['slots'] as List).map((s) => SlotInfo.fromJson(s as Map<String, dynamic>)).toList(),
      );
}

class Booking {
  Booking({
    required this.code,
    required this.day,
    required this.trail,
    required this.slot,
    required this.groupSize,
    required this.status,
    this.windowMinutes = 15,
  });

  final String code, trail, slot, status;
  final DateTime day;
  final int groupSize, windowMinutes;

  DateTime get slotStart {
    final p = slot.split(':');
    return DateTime(day.year, day.month, day.day, int.parse(p[0]), int.parse(p[1]));
  }

  DateTime get gateOpens => slotStart.subtract(Duration(minutes: windowMinutes));
  DateTime get gateCloses => slotStart.add(Duration(minutes: windowMinutes));

  factory Booking.fromJson(Map<String, dynamic> j) => Booking(
        code: j['code'] as String,
        day: DateTime.parse(j['day'] as String),
        trail: j['trail'] as String,
        slot: j['slot'] as String,
        groupSize: _int(j['group_size']),
        status: j['status'] as String? ?? 'booked',
        windowMinutes: _int(j['window_minutes'] ?? 15),
      );

  Map<String, dynamic> toJson() => {
        'code': code,
        'day': day.toIso8601String().substring(0, 10),
        'trail': trail,
        'slot': slot,
        'group_size': groupSize,
        'status': status,
        'window_minutes': windowMinutes,
      };
}

class Alternative {
  Alternative({required this.day, required this.trail, required this.slot, required this.left, required this.kind});

  final DateTime day;
  final String trail, slot, kind; // kind: slot | trail | day
  final int left;

  factory Alternative.fromJson(Map<String, dynamic> j) => Alternative(
        day: DateTime.parse(j['day'] as String),
        trail: j['trail'] as String,
        slot: j['slot'] as String,
        left: _int(j['left']),
        kind: j['kind'] as String,
      );
}

class Suggestion {
  Suggestion({required this.kind, required this.title, required this.detail, required this.reductionPct});

  final String kind, title, detail;
  final int reductionPct;

  factory Suggestion.fromJson(Map<String, dynamic> j) => Suggestion(
        kind: j['kind'] as String,
        title: j['title'] as String,
        detail: j['detail'] as String,
        reductionPct: _int(j['reduction_pct']),
      );
}

class TrailCapacity {
  TrailCapacity({required this.name, required this.expected, required this.quota});

  final String name;
  final int expected, quota;

  factory TrailCapacity.fromJson(Map<String, dynamic> j) => TrailCapacity(
        name: j['name'] as String? ?? '',
        expected: _int(j['expected_visitors']),
        quota: _int(j['recommended_daily_quota']),
      );
}

class DayPlan {
  DayPlan({
    required this.day,
    required this.crowdLevel,
    required this.p10,
    required this.p50,
    required this.p90,
    required this.confidence,
    required this.suggestions,
    required this.trails,
  });

  final DateTime day;
  final int crowdLevel, p10, p50, p90;
  final String confidence;
  final List<Suggestion> suggestions;
  final Map<String, TrailCapacity> trails;

  /// /plan/{day} (2-90 days ahead)
  factory DayPlan.fromPlanJson(Map<String, dynamic> j) => DayPlan(
        day: DateTime.parse(j['target_date'] as String),
        crowdLevel: _int(j['crowd_level']),
        p10: _int(j['visitors']['p10']),
        p50: _int(j['visitors']['p50']),
        p90: _int(j['visitors']['p90']),
        confidence: j['confidence'] as String? ?? '',
        suggestions: (j['suggestions'] as List? ?? [])
            .map((s) => Suggestion.fromJson(s as Map<String, dynamic>))
            .toList(),
        trails: ((j['capacity'] as Map<String, dynamic>)['trails'] as Map<String, dynamic>)
            .map((k, v) => MapEntry(k, TrailCapacity.fromJson(v as Map<String, dynamic>))),
      );

  /// /forecast/tomorrow (hour-by-hour model; no range, no suggestions)
  factory DayPlan.fromTomorrowJson(Map<String, dynamic> j, int crowdLevel) => DayPlan(
        day: DateTime.parse(j['forecast_date'] as String),
        crowdLevel: crowdLevel,
        p10: _int(j['expected_visitors']),
        p50: _int(j['expected_visitors']),
        p90: _int(j['expected_visitors']),
        confidence: 'high (tomorrow\'s weather forecast and recent visitor numbers)',
        suggestions: const [],
        trails: (j['trails'] as Map<String, dynamic>)
            .map((k, v) => MapEntry(k, TrailCapacity.fromJson(v as Map<String, dynamic>))),
      );
}

class StaffSession {
  StaffSession({required this.token, required this.username, required this.role});

  final String token, username, role; // role: ranger | officer | admin

  bool get isOfficer => role == 'officer' || role == 'admin';

  factory StaffSession.fromJson(Map<String, dynamic> j) =>
      StaffSession(token: j['token'] as String, username: j['username'] as String, role: j['role'] as String);
}

class CheckInResult {
  CheckInResult({required this.ok, required this.reason, this.trail, this.slot, this.groupSize});

  final bool ok;
  final String reason;
  final String? trail, slot;
  final int? groupSize;

  factory CheckInResult.fromJson(Map<String, dynamic> j) => CheckInResult(
        ok: j['ok'] as bool,
        reason: j['reason'] as String,
        trail: j['trail'] as String?,
        slot: j['slot'] as String?,
        groupSize: j['group_size'] == null ? null : _int(j['group_size']),
      );
}

class LiveSegment {
  LiveSegment({
    required this.segId,
    required this.trail,
    required this.poi,
    required this.people,
    required this.capacity,
    required this.light,
    required this.action,
  });

  final int segId;
  final String trail;
  final String? poi, action;
  final double people;
  final double? capacity;
  final String light; // green | amber | red

  factory LiveSegment.fromJson(Map<String, dynamic> j) => LiveSegment(
        segId: _int(j['seg_id']),
        trail: j['trail'] as String,
        poi: j['poi'] as String?,
        people: _dbl(j['people']),
        capacity: j['capacity'] == null ? null : _dbl(j['capacity']),
        light: j['light'] as String,
        action: j['action'] as String?,
      );
}

class WalkInSlot {
  WalkInSlot({required this.slot, required this.trail, required this.left});

  final String slot, trail;
  final int left;

  factory WalkInSlot.fromJson(Map<String, dynamic> j) =>
      WalkInSlot(slot: j['slot'] as String, trail: j['trail'] as String, left: _int(j['left']));
}

class ServerStatus {
  ServerStatus({
    required this.today,
    required this.refreshedAt,
    required this.note,
    this.park = 'horton_plains',
    this.site = 'Horton Plains',
    this.bookingMode = 'required',
  });

  final DateTime today;
  final String refreshedAt, note, park, site;
  final String bookingMode; // required = slot tickets | advisory = recommended start times (pilgrim sites)

  bool get isAdvisory => bookingMode == 'advisory';

  factory ServerStatus.fromJson(Map<String, dynamic> j) => ServerStatus(
        today: DateTime.parse(j['today'] as String),
        refreshedAt: j['refreshed_at'] as String? ?? '',
        note: j['note'] as String? ?? '',
        park: j['park'] as String? ?? 'horton_plains',
        site: j['site'] as String? ?? 'Horton Plains',
        bookingMode: j['booking_mode'] as String? ?? 'required',
      );
}

// ---------- several parks (gateway) ----------
class ParkInfo {
  ParkInfo({required this.id, required this.name, required this.bookingMode, required this.trails, this.center});

  final String id, name, bookingMode;
  final Map<String, String> trails;
  final List<double>? center; // [lon, lat]

  bool get isAdvisory => bookingMode == 'advisory';

  factory ParkInfo.fromJson(Map<String, dynamic> j) => ParkInfo(
        id: j['id'] as String,
        name: j['name'] as String,
        bookingMode: j['booking_mode'] as String? ?? 'required',
        trails: (j['trails'] as Map<String, dynamic>? ?? {}).map((k, v) => MapEntry(k, v as String)),
        center: (j['center'] as List?)?.map((x) => (x as num).toDouble()).toList(),
      );
}

// ---------- pilgrim sites: recommended start times ----------
class StartWindow {
  StartWindow({
    required this.start,
    required this.waitMin,
    required this.reachSummit,
    required this.beforeSunrise,
    required this.recommended,
  });

  final String start, reachSummit;
  final int waitMin;
  final bool beforeSunrise, recommended;

  factory StartWindow.fromJson(Map<String, dynamic> j) => StartWindow(
        start: j['start'] as String,
        waitMin: _int(j['expected_wait_min']),
        reachSummit: j['reach_summit'] as String? ?? '',
        beforeSunrise: j['before_sunrise'] as bool? ?? false,
        recommended: j['recommended'] as bool? ?? false,
      );
}

class RouteAdvice {
  RouteAdvice({required this.windows, required this.bestForSunrise, required this.recommendedForSunrise, required this.shortestWait});

  final List<StartWindow> windows;
  final String bestForSunrise, shortestWait;
  final List<String> recommendedForSunrise;

  factory RouteAdvice.fromJson(Map<String, dynamic> j) => RouteAdvice(
        windows: (j['windows'] as List).map((w) => StartWindow.fromJson(w as Map<String, dynamic>)).toList(),
        bestForSunrise: j['best_for_sunrise'] as String? ?? '',
        recommendedForSunrise: (j['recommended_for_sunrise'] as List? ?? []).cast<String>(),
        shortestWait: j['shortest_wait'] as String? ?? '',
      );
}

/// /advisory/{day}
class StartAdvice {
  StartAdvice({
    required this.day,
    required this.limitMin,
    required this.routes,
    required this.peakQueue,
    required this.peakWaitMin,
    required this.peakAt,
  });

  final DateTime day;
  final int limitMin, peakQueue, peakWaitMin;
  final String peakAt;
  final Map<String, RouteAdvice> routes;

  factory StartAdvice.fromJson(Map<String, dynamic> j) => StartAdvice(
        day: DateTime.parse(j['day'] as String),
        limitMin: _int(j['limit_min']),
        routes: (j['routes'] as Map<String, dynamic>).map((k, v) => MapEntry(k, RouteAdvice.fromJson(v as Map<String, dynamic>))),
        peakQueue: _int(j['summit']?['peak_queue_people']),
        peakWaitMin: _int(j['summit']?['peak_wait_min']),
        peakAt: j['summit']?['peak_at'] as String? ?? '',
      );
}

class CheckpointRow {
  CheckpointRow({required this.route, required this.name, required this.releasePer10Min, required this.walkToSummitMin, required this.countedToday});

  final String route, name;
  final int? releasePer10Min; // only while holding
  final int walkToSummitMin, countedToday;

  factory CheckpointRow.fromJson(Map<String, dynamic> j) => CheckpointRow(
        route: j['route'] as String,
        name: j['name'] as String? ?? j['route'] as String,
        releasePer10Min: j['release_per_10_min'] == null ? null : _int(j['release_per_10_min']),
        walkToSummitMin: _int(j['walk_to_summit_min']),
        countedToday: _int(j['counted_today']),
      );
}

/// /checkpoints/{day}: summit queue estimated from the halfway counts, and what to do.
class CheckpointStatus {
  CheckpointStatus({
    required this.time,
    required this.queueNow,
    required this.waitNowMin,
    required this.waitAheadMin,
    required this.aheadMin,
    required this.hold,
    required this.action,
    required this.checkpoints,
  });

  final String time, action;
  final int queueNow, waitNowMin, waitAheadMin, aheadMin;
  final bool hold;
  final List<CheckpointRow> checkpoints;

  factory CheckpointStatus.fromJson(Map<String, dynamic> j) => CheckpointStatus(
        time: j['time'] as String? ?? '',
        queueNow: _int(j['queue_now_people']),
        waitNowMin: _int(j['wait_now_min']),
        waitAheadMin: _int(j['wait_ahead_max_min']),
        aheadMin: _int(j['ahead_min']),
        hold: j['hold'] as bool? ?? false,
        action: j['action'] as String? ?? '',
        checkpoints: (j['checkpoints'] as List? ?? []).map((c) => CheckpointRow.fromJson(c as Map<String, dynamic>)).toList(),
      );
}

/// One trail segment for the map (from /trails/geometry).
class MapSegment {
  MapSegment({required this.trail, required this.poi, required this.points});

  final String trail, poi;
  final List<List<double>> points; // [lon, lat]

  static List<MapSegment> fromGeoJson(Map<String, dynamic> fc) {
    final out = <MapSegment>[];
    for (final f in (fc['features'] as List? ?? [])) {
      final g = f['geometry'] as Map<String, dynamic>?;
      final p = f['properties'] as Map<String, dynamic>? ?? {};
      if (g == null) continue;
      final lines = switch (g['type']) {
        'LineString' => [g['coordinates'] as List],
        'MultiLineString' => (g['coordinates'] as List).cast<List>(),
        _ => <List>[],
      };
      for (final l in lines) {
        out.add(MapSegment(
          trail: p['trail'] as String? ?? '',
          poi: p['poi'] as String? ?? '',
          points: [for (final c in l) [(c[0] as num).toDouble(), (c[1] as num).toDouble()]],
        ));
      }
    }
    return out;
  }
}
