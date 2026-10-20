// Data models for the Component 4 API (research/component_4/src/api/app.py).

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

// ---------- safe limit per trail and day (/capacity/{day}) ----------
class LimitFactor {
  LimitFactor({required this.key, required this.label, required this.pct});

  final String key, label;
  final int pct; // share of the capacity this factor removes

  factory LimitFactor.fromJson(Map<String, dynamic> j) =>
      LimitFactor(key: j['key'] as String, label: j['label'] as String? ?? j['key'] as String, pct: _int(j['pct']));
}

/// A trail condition reported by an officer (good / muddy / partly_closed / closed).
class TrailCondition {
  TrailCondition({this.level = 'good', this.note = '', this.factor = 0, this.setBy = ''});

  final String level, note, setBy;
  final double factor;

  bool get isGood => level == 'good';
  bool get isClosed => factor >= 1;
  String get label => level.replaceAll('_', ' ');

  factory TrailCondition.fromJson(Map<String, dynamic>? j) => j == null
      ? TrailCondition()
      : TrailCondition(
          level: j['level'] as String? ?? 'good',
          note: j['note'] as String? ?? '',
          factor: _dbl(j['factor']),
          setBy: j['set_by'] as String? ?? '',
        );
}

class TrailLimit {
  TrailLimit({
    required this.trail,
    required this.name,
    required this.expected,
    required this.safeLimit,
    required this.condition,
    required this.factors,
  });

  final String trail, name;
  final int expected, safeLimit;
  final TrailCondition condition;
  final List<LimitFactor> factors;

  bool get overLimit => expected > safeLimit;

  factory TrailLimit.fromJson(Map<String, dynamic> j) => TrailLimit(
        trail: j['trail'] as String,
        name: j['name'] as String? ?? j['trail'] as String,
        expected: _int(j['expected_visitors']),
        safeLimit: _int(j['safe_limit']),
        condition: TrailCondition.fromJson(j['condition'] as Map<String, dynamic>?),
        factors: (j['factors'] as List? ?? []).map((f) => LimitFactor.fromJson(f as Map<String, dynamic>)).toList(),
      );
}

class DayCapacity {
  DayCapacity({
    required this.day,
    required this.weatherBasis,
    required this.rainShare,
    required this.groundRainMm,
    required this.groundDays,
    required this.groundBasis,
    required this.wetness,
    required this.trails,
  });

  final DateTime day;
  final String weatherBasis, groundBasis;
  final double rainShare, groundRainMm, wetness;
  final int groundDays;
  final List<TrailLimit> trails;

  TrailLimit? forTrail(String id) => trails.where((t) => t.trail == id).firstOrNull;

  factory DayCapacity.fromJson(Map<String, dynamic> j) {
    final g = j['ground'] as Map<String, dynamic>? ?? {};
    return DayCapacity(
      day: DateTime.parse(j['day'] as String),
      weatherBasis: j['weather_basis'] as String? ?? '',
      rainShare: _dbl(j['rain_share_open_hours']),
      groundRainMm: _dbl(g['rain_mm']),
      groundDays: g['days'] == null ? 3 : _int(g['days']),
      groundBasis: g['basis'] as String? ?? '',
      wetness: _dbl(g['wetness']),
      trails: (j['trails'] as List? ?? []).map((t) => TrailLimit.fromJson(t as Map<String, dynamic>)).toList(),
    );
  }
}

// ---------- destinations (gateway /parks, park /destination) ----------
/// One destination for the trip planner. Everything comes from the park's config, so a new destination needs
/// no app change.
class ParkInfo {
  ParkInfo({
    required this.id,
    required this.name,
    required this.bookingMode,
    required this.trails,
    this.kind = 'park',
    this.region = '',
    this.summary = '',
    this.elevation = '',
    this.bestTime = '',
    this.gettingThere = '',
    this.facts = const [],
    this.accent,
    this.trailInfo = const {},
  });

  final String id, name, bookingMode, kind, region, summary, elevation, bestTime, gettingThere;
  final Map<String, String> trails, trailInfo;
  final List<String> facts;
  final int? accent; // ARGB colour for banners

  bool get isAdvisory => bookingMode == 'advisory';

  static Map<String, String> _strMap(dynamic m) => (m as Map<String, dynamic>? ?? {}).map((k, v) => MapEntry(k, '$v'));

  static int? _color(dynamic s) {
    if (s is! String || !RegExp(r'^#[0-9a-fA-F]{6}$').hasMatch(s)) return null;
    return 0xFF000000 | int.parse(s.substring(1), radix: 16);
  }

  factory ParkInfo.fromJson(Map<String, dynamic> j) => ParkInfo(
        id: j['id'] as String,
        name: j['name'] as String,
        bookingMode: j['booking_mode'] as String? ?? 'required',
        trails: _strMap(j['trails']),
        kind: j['kind'] as String? ?? 'park',
        region: j['region'] as String? ?? '',
        summary: j['summary'] as String? ?? '',
        elevation: j['elevation'] as String? ?? '',
        bestTime: j['best_time'] as String? ?? '',
        gettingThere: j['getting_there'] as String? ?? '',
        facts: (j['facts'] as List? ?? []).map((f) => '$f').toList(),
        accent: _color(j['accent']),
        trailInfo: _strMap(j['trail_info']),
      );
}

// ---------- pilgrim sites: officers' season plan ----------
class SeasonNight {
  SeasonNight({
    required this.date,
    required this.crowdLevel,
    required this.p10,
    required this.p50,
    required this.p90,
    required this.peakQueue,
    required this.peakWaitMin,
    required this.peakAt,
    required this.holdWindows,
    required this.highPeakWaitMin,
    required this.highHoldWindows,
    required this.checks,
  });

  final DateTime date;
  final int crowdLevel, p10, p50, p90, peakQueue, peakWaitMin, highPeakWaitMin;
  final String peakAt, checks; // checks: needed | standby | none
  final List<List<String>> holdWindows, highHoldWindows;

  factory SeasonNight.fromJson(Map<String, dynamic> j) => SeasonNight(
        date: DateTime.parse(j['date'] as String),
        crowdLevel: _int(j['crowd_level']),
        p10: _int(j['visitors']['p10']),
        p50: _int(j['visitors']['p50']),
        p90: _int(j['visitors']['p90']),
        peakQueue: _int(j['peak_queue_people']),
        peakWaitMin: _int(j['peak_wait_min']),
        peakAt: j['peak_at'] as String? ?? '',
        holdWindows: windowsOf(j['hold_windows']),
        highPeakWaitMin: _int(j['high_peak_wait_min']),
        highHoldWindows: windowsOf(j['high_hold_windows']),
        checks: j['checks'] as String? ?? 'none',
      );
}

/// [["03:15","05:00"], ...] -> list of [from, to]
List<List<String>> windowsOf(dynamic v) => (v as List? ?? []).map((w) => (w as List).map((x) => '$x').toList()).toList();

String windowsText(List<List<String>> w) => w.map((x) => '${x[0]}–${x[1]}').join(', ');

class HalfwayPlan {
  HalfwayPlan({required this.releasePer10Min, required this.walkToSummitMin, required this.holdWindows});

  final int releasePer10Min, walkToSummitMin;
  final List<List<String>> holdWindows;

  factory HalfwayPlan.fromJson(Map<String, dynamic> j) => HalfwayPlan(
        releasePer10Min: _int(j['release_per_10_min']),
        walkToSummitMin: _int(j['walk_to_summit_min']),
        holdWindows: windowsOf(j['hold_windows']),
      );

  static Map<String, HalfwayPlan> mapOf(dynamic m) =>
      (m as Map<String, dynamic>? ?? {}).map((k, v) => MapEntry(k, HalfwayPlan.fromJson(v as Map<String, dynamic>)));
}

// ---------- pilgrim sites: recommended start times ----------
class StartWindow {
  StartWindow({
    required this.start,
    required this.waitMin,
    required this.reachSummit,
    required this.beforeSunrise,
    required this.recommended,
    this.eveningBefore = false,
    this.tooEarly = false,
    this.climbH = 0,
  });

  final String start, reachSummit;
  final int waitMin;
  final bool beforeSunrise, recommended;
  final bool eveningBefore; // starts the evening before the sunrise date
  final bool tooEarly; // reaches the top hours before sunrise (cold wait)
  final double climbH; // hours from start to summit at tonight's expected crowd

  factory StartWindow.fromJson(Map<String, dynamic> j) => StartWindow(
        start: j['start'] as String,
        waitMin: _int(j['expected_wait_min']),
        reachSummit: j['reach_summit'] as String? ?? '',
        beforeSunrise: j['before_sunrise'] as bool? ?? false,
        recommended: j['recommended'] as bool? ?? false,
        eveningBefore: j['evening_before'] as bool? ?? false,
        tooEarly: j['too_early'] as bool? ?? false,
        climbH: _dbl(j['climb_h']),
      );
}

/// Start the evening before, rest at the route's halfway hall, leave it at a recommended time.
class EveningPlan {
  EveningPlan({
    required this.startFrom,
    required this.startTo,
    required this.reachHallBy,
    required this.leaveHallAt,
    required this.reachSummit,
    required this.hallPeopleExpected,
    this.hallCapacity,
    this.hallMayBeFull = false,
  });

  final String startFrom, startTo, reachHallBy, leaveHallAt, reachSummit;
  final int hallPeopleExpected;
  final int? hallCapacity;
  final bool hallMayBeFull;

  static EveningPlan? fromJson(Map<String, dynamic>? j) => j == null
      ? null
      : EveningPlan(
          startFrom: j['start_from'] as String? ?? '',
          startTo: j['start_to'] as String? ?? '',
          reachHallBy: j['reach_hall_by'] as String? ?? '',
          leaveHallAt: j['leave_hall_at'] as String? ?? '',
          reachSummit: j['reach_summit'] as String? ?? '',
          hallPeopleExpected: _int(j['hall_people_expected']),
          hallCapacity: j['hall_capacity'] == null ? null : _int(j['hall_capacity']),
          hallMayBeFull: j['hall_may_be_full'] as bool? ?? false,
        );
}

class RouteAdvice {
  RouteAdvice({
    required this.windows,
    required this.bestForSunrise,
    required this.recommendedForSunrise,
    required this.shortestWait,
    this.earlyArrivalNeeded = false,
    this.climbH = 0,
    this.usualStart = '',
    this.usualStartClimbH = 0,
    this.usualStartReaches = '',
    this.eveningPlan,
  });

  final List<StartWindow> windows;
  final String bestForSunrise, shortestWait;
  final List<String> recommendedForSunrise;
  final bool earlyArrivalNeeded; // busy night: only starts ahead of the crowd make sunrise
  final double climbH, usualStartClimbH; // climb time of the best start / of the usual start (with the crowd)
  final String usualStart, usualStartReaches;
  final EveningPlan? eveningPlan;

  StartWindow? get best => windows.where((w) => w.start == bestForSunrise).firstOrNull;

  factory RouteAdvice.fromJson(Map<String, dynamic> j) => RouteAdvice(
        windows: (j['windows'] as List).map((w) => StartWindow.fromJson(w as Map<String, dynamic>)).toList(),
        bestForSunrise: j['best_for_sunrise'] as String? ?? '',
        recommendedForSunrise: (j['recommended_for_sunrise'] as List? ?? []).cast<String>(),
        shortestWait: j['shortest_wait'] as String? ?? '',
        earlyArrivalNeeded: j['early_arrival_needed'] as bool? ?? false,
        climbH: _dbl(j['climb_h']),
        usualStart: j['usual_start'] as String? ?? '',
        usualStartClimbH: _dbl(j['usual_start_climb_h']),
        usualStartReaches: j['usual_start_reaches'] as String? ?? '',
        eveningPlan: EveningPlan.fromJson(j['evening_plan'] as Map<String, dynamic>?),
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
    this.binMin = 15,
    this.firstBinMin = 0,
    this.sunrise = '',
    this.waitByTime = const [],
    this.holdWindows = const [],
    this.halfway = const {},
    this.highVisitors = 0,
    this.highPeakWaitMin = 0,
    this.highWaitByTime = const [],
    this.highHoldWindows = const [],
    this.highHalfway = const {},
  });

  final DateTime day;
  final int limitMin, peakQueue, peakWaitMin, binMin, highVisitors, highPeakWaitMin;
  final int firstBinMin; // minute of the first bin (negative = the evening before, e.g. -360 = 18:00)
  final String peakAt, sunrise; // sunrise at the summit on that date
  final Map<String, RouteAdvice> routes;
  final List<int> waitByTime, highWaitByTime; // expected wait at the summit per [binMin] minutes from [firstBinMin]
  final List<List<String>> holdWindows, highHoldWindows;
  final Map<String, HalfwayPlan> halfway, highHalfway; // likely case / high case (P90 climbers)

  static List<int> _ints(dynamic v) => (v as List? ?? []).map((x) => _int(x)).toList();

  factory StartAdvice.fromJson(Map<String, dynamic> j) {
    final s = j['summit'] as Map<String, dynamic>? ?? {};
    final h = j['high_case'] as Map<String, dynamic>? ?? {};
    final hs = h['summit'] as Map<String, dynamic>? ?? {};
    return StartAdvice(
      day: DateTime.parse(j['day'] as String),
      limitMin: _int(j['limit_min']),
      routes: (j['routes'] as Map<String, dynamic>).map((k, v) => MapEntry(k, RouteAdvice.fromJson(v as Map<String, dynamic>))),
      peakQueue: _int(s['peak_queue_people']),
      peakWaitMin: _int(s['peak_wait_min']),
      peakAt: s['peak_at'] as String? ?? '',
      binMin: s['bin_min'] == null ? 15 : _int(s['bin_min']),
      firstBinMin: _int(s['first_bin_min']),
      sunrise: j['sunrise'] as String? ?? '',
      waitByTime: _ints(s['wait_by_time']),
      holdWindows: windowsOf(s['hold_windows']),
      halfway: HalfwayPlan.mapOf(j['halfway']),
      highVisitors: _int(h['visitors']),
      highPeakWaitMin: _int(hs['peak_wait_min']),
      highWaitByTime: _ints(hs['wait_by_time']),
      highHoldWindows: windowsOf(hs['hold_windows']),
      highHalfway: HalfwayPlan.mapOf(h['halfway']),
    );
  }
}

class CheckpointRow {
  CheckpointRow({
    required this.route,
    required this.name,
    required this.releasePer10Min,
    required this.walkToSummitMin,
    required this.countedToday,
    this.lastCountAt,
    this.plannedHold = const [],
    this.plannedHoldIfBusy = const [],
  });

  final String route, name;
  final int? releasePer10Min; // only while holding
  final int walkToSummitMin, countedToday;
  final String? lastCountAt;
  final List<List<String>> plannedHold, plannedHoldIfBusy; // from the forecast: likely / if as busy as the high case

  factory CheckpointRow.fromJson(Map<String, dynamic> j) => CheckpointRow(
        route: j['route'] as String,
        name: j['name'] as String? ?? j['route'] as String,
        releasePer10Min: j['release_per_10_min'] == null ? null : _int(j['release_per_10_min']),
        walkToSummitMin: _int(j['walk_to_summit_min']),
        countedToday: _int(j['counted_today']),
        lastCountAt: j['last_count_at'] as String?,
        plannedHold: windowsOf(j['planned_hold']),
        plannedHoldIfBusy: windowsOf(j['planned_hold_if_busy']),
      );
}

class CountEntry {
  CountEntry({required this.route, required this.name, required this.time, required this.count, required this.by});

  final String route, name, time, by;
  final int count;

  factory CountEntry.fromJson(Map<String, dynamic> j) => CountEntry(
        route: j['route'] as String,
        name: j['name'] as String? ?? j['route'] as String,
        time: j['time'] as String? ?? '',
        count: _int(j['count']),
        by: j['by'] as String? ?? '',
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
    this.log = const [],
  });

  final String time, action;
  final int queueNow, waitNowMin, waitAheadMin, aheadMin;
  final bool hold;
  final List<CheckpointRow> checkpoints;
  final List<CountEntry> log; // newest first

  factory CheckpointStatus.fromJson(Map<String, dynamic> j) => CheckpointStatus(
        time: j['time'] as String? ?? '',
        queueNow: _int(j['queue_now_people']),
        waitNowMin: _int(j['wait_now_min']),
        waitAheadMin: _int(j['wait_ahead_max_min']),
        aheadMin: _int(j['ahead_min']),
        hold: j['hold'] as bool? ?? false,
        action: j['action'] as String? ?? '',
        checkpoints: (j['checkpoints'] as List? ?? []).map((c) => CheckpointRow.fromJson(c as Map<String, dynamic>)).toList(),
        log: (j['log'] as List? ?? []).map((c) => CountEntry.fromJson(c as Map<String, dynamic>)).toList(),
      );
}

/// One trail segment for the map (from /trails/geometry).
class MapSegment {
  MapSegment({required this.trail, required this.poi, required this.points, this.id = -1});

  final int id; // seg_id (-1 if the server did not send it)
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
          id: (p['seg_id'] as num?)?.toInt() ?? -1,
          trail: p['trail'] as String? ?? '',
          poi: p['poi'] as String? ?? '',
          points: [for (final c in l) [(c[0] as num).toDouble(), (c[1] as num).toDouble()]],
        ));
      }
    }
    return out;
  }
}
