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
    this.trailName,
  });

  final String code, trail, slot, status;
  final String? trailName; // the park's name for the trail (server sends it; older tickets have none)
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
        trailName: j['trail_name'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'code': code,
        'day': day.toIso8601String().substring(0, 10),
        'trail': trail,
        'slot': slot,
        'group_size': groupSize,
        'status': status,
        'window_minutes': windowMinutes,
        if (trailName != null) 'trail_name': trailName,
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
    this.sightings = false,
  });

  final DateTime today;
  final String refreshedAt, note, park, site;
  final String bookingMode; // required = slot tickets | advisory = recommended start times (pilgrim sites)
  final bool sightings; // safari parks: rangers report wildlife sightings and manage the jeeps at them

  bool get isAdvisory => bookingMode == 'advisory';

  factory ServerStatus.fromJson(Map<String, dynamic> j) => ServerStatus(
        today: DateTime.parse(j['today'] as String),
        refreshedAt: j['refreshed_at'] as String? ?? '',
        note: j['note'] as String? ?? '',
        park: j['park'] as String? ?? 'horton_plains',
        site: j['site'] as String? ?? 'Horton Plains',
        bookingMode: j['booking_mode'] as String? ?? 'required',
        sightings: j['sightings'] as bool? ?? false,
      );
}

// ---------- wildlife sightings (safari parks, /sightings/{day}) ----------
class Sighting {
  Sighting({
    required this.id,
    required this.segId,
    required this.place,
    required this.since,
    required this.species,
    required this.jeepsNear,
    required this.capJeeps,
    required this.rotationMin,
    required this.advice,
    required this.circuitsAvoiding,
  });

  final int id, segId, jeepsNear, capJeeps, rotationMin;
  final String place, since, species, advice;
  final List<String> circuitsAvoiding;

  bool get crowded => jeepsNear > capJeeps;

  factory Sighting.fromJson(Map<String, dynamic> j) => Sighting(
        id: _int(j['id']),
        segId: _int(j['seg_id']),
        place: j['place'] as String? ?? '',
        since: j['since'] as String? ?? '',
        species: j['species'] as String? ?? '',
        jeepsNear: _int(j['jeeps_near']),
        capJeeps: _int(j['cap_jeeps']),
        rotationMin: _int(j['rotation_min']),
        advice: j['advice'] as String? ?? '',
        circuitsAvoiding: [for (final c in j['circuits_avoiding'] as List? ?? []) '$c'],
      );
}

class SightingStatus {
  SightingStatus({required this.time, required this.sightings, required this.note});

  final String time, note;
  final List<Sighting> sightings;

  factory SightingStatus.fromJson(Map<String, dynamic> j) => SightingStatus(
        time: j['time'] as String? ?? '',
        note: j['note'] as String? ?? '',
        sightings: [for (final s in j['sightings'] as List? ?? []) Sighting.fromJson(s as Map<String, dynamic>)],
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

/// One day of one trail in the officer records (GET /admin/records).
class RecordRow {
  RecordRow({
    required this.date,
    required this.trail,
    required this.trailName,
    required this.period,
    this.visitors,
    this.low,
    this.high,
    this.source = '',
    this.booked = 0,
    this.checkedIn = 0,
    this.walkIns = 0,
    this.gateTotal = 0,
    this.halfway = 0,
    this.safeLimit,
  });

  final DateTime date;
  final String trail, trailName, period; // period: past | today | future
  final int? visitors, low, high, safeLimit;
  final String source;
  final int booked, checkedIn, walkIns, gateTotal, halfway;

  bool get overLimit => visitors != null && safeLimit != null && visitors! > safeLimit!;

  factory RecordRow.fromJson(Map<String, dynamic> j) => RecordRow(
        date: DateTime.parse(j['date'] as String),
        trail: j['trail'] as String,
        trailName: j['trail_name'] as String? ?? j['trail'] as String,
        period: j['period'] as String,
        visitors: (j['visitors'] as num?)?.round(),
        low: (j['low'] as num?)?.round(),
        high: (j['high'] as num?)?.round(),
        source: j['source'] as String? ?? '',
        booked: (j['booked'] as num?)?.round() ?? 0,
        checkedIn: (j['checked_in'] as num?)?.round() ?? 0,
        walkIns: (j['walk_ins'] as num?)?.round() ?? 0,
        gateTotal: (j['gate_total'] as num?)?.round() ?? 0,
        halfway: (j['halfway'] as num?)?.round() ?? 0,
        safeLimit: (j['safe_limit'] as num?)?.round(),
      );

  static const csvHeader =
      'date,trail,period,visitors,low,high,source,booked,checked_in,walk_ins,gate_total,halfway,safe_limit';

  String toCsv() {
    String q(String s) => s.contains(',') || s.contains('"') ? '"${s.replaceAll('"', '""')}"' : s;
    String n(int? v) => v?.toString() ?? '';
    return [
      date.toIso8601String().substring(0, 10), q(trailName), period, n(visitors), n(low), n(high), q(source),
      '$booked', '$checkedIn', '$walkIns', '$gateTotal', '$halfway', n(safeLimit),
    ].join(',');
  }
}

class CrowdRecords {
  CrowdRecords({required this.site, required this.today, required this.trails, required this.rows, this.note = ''});

  final String site;
  final DateTime today;
  final Map<String, String> trails; // id -> name
  final List<RecordRow> rows;
  final String note;

  factory CrowdRecords.fromJson(Map<String, dynamic> j) => CrowdRecords(
        site: j['site'] as String? ?? '',
        today: DateTime.parse(j['today'] as String),
        trails: (j['trails'] as Map<String, dynamic>? ?? {}).map((k, v) => MapEntry(k, v as String)),
        rows: [for (final r in j['rows'] as List) RecordRow.fromJson(r as Map<String, dynamic>)],
        note: j['note'] as String? ?? '',
      );

  /// All trails of a day added up (visitors, ranges, counts, limits); one entry per date, in order.
  List<RecordRow> perDay() {
    final byDay = <DateTime, List<RecordRow>>{};
    for (final r in rows) {
      byDay.putIfAbsent(r.date, () => []).add(r);
    }
    int? sum(Iterable<int?> v) => v.any((x) => x == null) ? null : v.fold<int>(0, (a, b) => a + b!);
    return [
      for (final e in byDay.entries)
        RecordRow(
          date: e.key,
          trail: 'all',
          trailName: 'All trails',
          period: e.value.first.period,
          visitors: sum(e.value.map((r) => r.visitors)),
          low: sum(e.value.map((r) => r.low)),
          high: sum(e.value.map((r) => r.high)),
          source: e.value.first.source,
          booked: e.value.fold(0, (a, r) => a + r.booked),
          checkedIn: e.value.fold(0, (a, r) => a + r.checkedIn),
          walkIns: e.value.fold(0, (a, r) => a + r.walkIns),
          gateTotal: e.value.fold(0, (a, r) => a + r.gateTotal),
          halfway: e.value.fold(0, (a, r) => a + r.halfway),
          safeLimit: sum(e.value.map((r) => r.safeLimit)),
        ),
    ];
  }

  String toCsv() => [RecordRow.csvHeader, for (final r in rows) r.toCsv()].join('\n');
}

// ---------- officer capacity panel (A2): the day's quota under each rule ----------
class QuotaOptions {
  QuotaOptions({required this.forecast, required this.classic, required this.statik, this.manual, required this.rule,
      required this.applied, this.decidedBy});

  final int forecast, classic, statik, applied;
  final int? manual;
  final String rule;
  final String? decidedBy;

  int? of(String r) => switch (r) { 'forecast' => forecast, 'classic' => classic, 'static' => statik, _ => manual };

  factory QuotaOptions.fromJson(Map<String, dynamic> j) => QuotaOptions(
        forecast: _int(j['forecast']),
        classic: _int(j['classic']),
        statik: _int(j['static']),
        manual: j['manual'] == null ? null : _int(j['manual']),
        rule: j['rule'] as String? ?? 'forecast',
        applied: _int(j['applied']),
        decidedBy: j['decided_by'] as String?,
      );
}

class TrailQuota {
  TrailQuota({required this.trail, required this.name, required this.expected, required this.quota,
      required this.limitingSection, required this.reason, required this.sectionsOver});

  final String trail, name, limitingSection, reason;
  final int expected, sectionsOver;
  final QuotaOptions quota;

  factory TrailQuota.fromJson(Map<String, dynamic> j) => TrailQuota(
        trail: j['trail'] as String,
        name: j['name'] as String? ?? j['trail'] as String,
        expected: _int(j['expected_visitors']),
        quota: QuotaOptions.fromJson(j['quota'] as Map<String, dynamic>),
        limitingSection: j['limiting_section'] as String? ?? '',
        reason: j['reason'] as String? ?? '',
        sectionsOver: _int(j['sections_over_capacity']),
      );
}

class SectionOver {
  SectionOver({required this.segId, required this.trail, required this.name, required this.hours,
      required this.peakPeople, required this.capacityAtOnce});

  final int segId;
  final String trail, name;
  final List<int> hours;
  final double peakPeople, capacityAtOnce;

  factory SectionOver.fromJson(Map<String, dynamic> j) => SectionOver(
        segId: _int(j['seg_id']),
        trail: j['trail'] as String? ?? '',
        name: j['name'] as String? ?? '',
        hours: [for (final h in j['hours'] as List? ?? []) _int(h)],
        peakPeople: _dbl(j['peak_people']),
        capacityAtOnce: _dbl(j['capacity_at_once']),
      );
}

class CapacityPanel {
  CapacityPanel({required this.day, required this.rules, required this.defaultRule, required this.trails,
      required this.over, required this.basis});

  final DateTime day;
  final Map<String, String> rules, basis;
  final String defaultRule;
  final List<TrailQuota> trails;
  final List<SectionOver> over;

  factory CapacityPanel.fromJson(Map<String, dynamic> j) => CapacityPanel(
        day: DateTime.parse(j['day'] as String),
        rules: {for (final e in (j['rules'] as Map? ?? {}).entries) e.key as String: e.value as String},
        defaultRule: j['default_rule'] as String? ?? 'forecast',
        trails: [for (final t in j['trails'] as List? ?? []) TrailQuota.fromJson(t as Map<String, dynamic>)],
        over: [for (final o in j['over_capacity'] as List? ?? []) SectionOver.fromJson(o as Map<String, dynamic>)],
        basis: {for (final e in (j['basis'] as Map? ?? {}).entries) e.key as String: e.value as String},
      );
}
// ---------- A4: rangers' spot counts and the forecast check ----------
class SegmentInfo {
  SegmentInfo({required this.segId, required this.name, required this.trail, required this.trailName, this.modelInput = false});

  final int segId;
  final String name, trail, trailName;
  final bool modelInput; // A1: a count here updates today's forecast

  factory SegmentInfo.fromJson(Map<String, dynamic> j) => SegmentInfo(
        segId: _int(j['seg_id']),
        name: j['name'] as String? ?? '',
        trail: j['trail'] as String? ?? '',
        trailName: j['trail_name'] as String? ?? '',
        modelInput: j['model_input'] == true,
      );
}

/// A count made on the phone; kept until the server has it (offline-first).
class SpotCount {
  SpotCount({required this.day, required this.segId, required this.time, required this.count, required this.clientId});

  final DateTime day;
  final int segId, count;
  final String time, clientId; // 'HH:MM'

  Map<String, dynamic> toJson() => {
        'day': '${day.year.toString().padLeft(4, '0')}-${day.month.toString().padLeft(2, '0')}-${day.day.toString().padLeft(2, '0')}',
        'seg_id': segId,
        'time': time,
        'count': count,
        'client_id': clientId,
      };

  factory SpotCount.fromJson(Map<String, dynamic> j) => SpotCount(
        day: DateTime.parse(j['day'] as String),
        segId: _int(j['seg_id']),
        time: j['time'] as String,
        count: _int(j['count']),
        clientId: j['client_id'] as String,
      );
}

class CheckRow {
  CheckRow({required this.day, required this.segId, required this.name, required this.timeMin, required this.count,
      this.forecast, required this.capacity, required this.countedOver, this.forecastOver});

  final DateTime day;
  final int segId, timeMin, count;
  final String name;
  final double? forecast;
  final double capacity;
  final bool countedOver;
  final bool? forecastOver;

  factory CheckRow.fromJson(Map<String, dynamic> j) => CheckRow(
        day: DateTime.parse(j['day'] as String),
        segId: _int(j['seg_id']),
        name: j['name'] as String? ?? 'section ${j['seg_id']}',
        timeMin: _int(j['time_min']),
        count: _int(j['count']),
        forecast: j['forecast'] == null ? null : _dbl(j['forecast']),
        capacity: _dbl(j['capacity_at_once']),
        countedOver: j['counted_over'] == true,
        forecastOver: j['forecast_over'] as bool?,
      );
}

class ForecastCheck {
  ForecastCheck({required this.summary, required this.rows, required this.note});

  final Map<String, num> summary;
  final List<CheckRow> rows;
  final String note;

  factory ForecastCheck.fromJson(Map<String, dynamic> j) => ForecastCheck(
        summary: {for (final e in (j['summary'] as Map? ?? {}).entries) e.key as String: e.value as num},
        rows: [for (final r in j['rows'] as List? ?? []) CheckRow.fromJson(r as Map<String, dynamic>)],
        note: j['note'] as String? ?? '',
      );
}
// ---------- A3: what to do at the gate in the next two hours ----------
class GateAdvice {
  GateAdvice({required this.time, required this.over, required this.advice, required this.inside, required this.basis});

  final String time, basis;
  final int inside;
  final List<Map<String, dynamic>> over; // seg_id, name, trail, at, people, capacity
  final List<Map<String, dynamic>> advice; // trail, trail_name, hold_min, send_to, text

  factory GateAdvice.fromJson(Map<String, dynamic> j) => GateAdvice(
        time: j['time'] as String? ?? '',
        over: [for (final o in j['over'] as List? ?? []) o as Map<String, dynamic>],
        advice: [for (final a in j['advice'] as List? ?? []) a as Map<String, dynamic>],
        inside: _int(j['inside']),
        basis: j['basis'] as String? ?? '',
      );
}

// ---------- A1: the rest of today, updated from the rangers' spot counts ----------
class TodayUpdate {
  TodayUpdate({required this.fromHour, required this.countsUsed, required this.changes, required this.over, required this.basis});

  final int fromHour, countsUsed;
  final List<Map<String, dynamic>> changes; // seg_id, name, change (peak people, updated - morning), over_hours
  final List<Map<String, dynamic>> over; // seg_id, name, over_hours, capacity_at_once
  final String basis;

  factory TodayUpdate.fromJson(Map<String, dynamic> j) => TodayUpdate(
        fromHour: _int(j['from_hour']),
        countsUsed: _int(j['counts_used']),
        changes: [for (final c in j['biggest_changes'] as List? ?? []) c as Map<String, dynamic>],
        over: [for (final o in j['over_capacity'] as List? ?? []) o as Map<String, dynamic>],
        basis: j['basis'] as String? ?? '',
      );
}

// ---------- W-c: the weather of a chosen date (GET /weather/{day}, or the edge pack offline) ----------
class WeatherHour {
  WeatherHour({required this.hour, required this.rainMm, required this.tempC, required this.windKmh});

  final int hour;
  final double rainMm, tempC, windKmh;

  factory WeatherHour.fromJson(Map<String, dynamic> j) => WeatherHour(
        hour: _int(j['hour']),
        rainMm: _dbl(j['rain_mm']),
        tempC: _dbl(j['temp_c']),
        windKmh: _dbl(j['wind_kmh']),
      );
}

class DayWeather {
  DayWeather({required this.basis, required this.basisLabel, required this.hours, required this.rainMm,
      required this.rainShare, required this.tempMin, required this.tempMax, required this.dryWindows,
      required this.dryBasis, required this.effect, this.typicalLow, this.typicalHigh, this.chanceWetDay});

  final String basis, basisLabel, dryBasis, effect; // basis: observed | forecast | typical
  final List<WeatherHour> hours; // open hours
  final double rainMm, rainShare, tempMin, tempMax;
  final List<(int, int)> dryWindows; // (from, to) hours, to exclusive
  final double? typicalLow, typicalHigh, chanceWetDay; // typical days: rain mm P10-P90, chance of a wet day

  /// 0 dry · 1 showers · 2 wet · 3 very wet (for an icon).
  int get wetness => rainShare < 0.1 ? 0 : rainShare < 0.3 ? 1 : rainShare < 0.6 ? 2 : 3;

  factory DayWeather.fromJson(Map<String, dynamic> j) {
    final s = j['summary'] as Map<String, dynamic>? ?? {};
    final open = {for (final h in j['open_hours'] as List? ?? []) (h as num).toInt()};
    final t = j['typical_range'] as Map<String, dynamic>?;
    return DayWeather(
      basis: j['basis'] as String? ?? 'forecast',
      basisLabel: j['basis_label'] as String? ?? '',
      hours: [
        for (final h in j['hourly'] as List? ?? [])
          if (open.isEmpty || open.contains(((h as Map)['hour'] as num).toInt())) WeatherHour.fromJson(h as Map<String, dynamic>),
      ],
      rainMm: _dbl(s['rain_mm_open_hours']),
      rainShare: _dbl(s['rain_share_open_hours']),
      tempMin: _dbl(s['temp_min']),
      tempMax: _dbl(s['temp_max']),
      dryWindows: [for (final w in s['dry_windows'] as List? ?? []) (_int((w as Map)['from']), _int(w['to']))],
      dryBasis: s['dry_windows_basis'] as String? ?? 'hours without rain',
      effect: (j['effect'] as Map?)?['text'] as String? ?? '',
      typicalLow: t == null ? null : _dbl(t['rain_mm_p10']),
      typicalHigh: t == null ? null : _dbl(t['rain_mm_p90']),
      chanceWetDay: t == null ? null : _dbl(t['chance_wet_day']),
    );
  }
}

// ---------- RQ13: closed-loop gate control (MPC), re-planned every slot ----------
class GateControl {
  GateControl({required this.slot, required this.ratio, required this.trails, required this.basis});

  final String slot, basis;
  final double ratio; // arrivals so far / expected so far
  final List<Map<String, dynamic>> trails; // trail, trail_name, entered_this_slot, can_enter_now, closed_for_entry, next_slots

  factory GateControl.fromJson(Map<String, dynamic> j) => GateControl(
        slot: j['slot'] as String? ?? '',
        ratio: _dbl(j['arrivals_vs_expected']),
        trails: [for (final t in j['trails'] as List? ?? []) t as Map<String, dynamic>],
        basis: j['basis'] as String? ?? '',
      );
}

// ---------- N3: a start time for visitors without a ticket (GET /start-time/{day}) ----------
class StartTimeSuggestion {
  StartTimeSuggestion({required this.trail, required this.wanted, this.suggested, this.laterMin, required this.note});

  final String trail, wanted, note;
  final String? suggested; // null: full for the next 3 hours
  final int? laterMin;

  factory StartTimeSuggestion.fromJson(Map<String, dynamic> j) => StartTimeSuggestion(
        trail: j['trail'] as String? ?? '',
        wanted: j['wanted'] as String? ?? '',
        suggested: j['suggested'] as String?,
        laterMin: j['later_than_wanted_min'] == null ? null : _int(j['later_than_wanted_min']),
        note: j['note'] as String? ?? '',
      );
}