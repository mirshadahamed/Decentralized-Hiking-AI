import 'edge_forecaster.dart';

/// How full a trail section is at one hour: forecast people ÷ the people it holds at Cifuentes social spacing.
enum Crowding { quiet, filling, busy, over }

/// Tomorrow's micro-spatial bottleneck picture: for every trail section, the hourly ST-GNN forecast and its
/// Cifuentes capacity (people at once; PCC → RCC → ECC visits per day), plus the trail summaries.
/// Built from the daily edge pack (forecast computed on this phone, also offline) or from the server's forecast.
class BottleneckDay {
  BottleneckDay({
    required this.day,
    required this.sections,
    required this.trails,
    required this.openHours,
    required this.busyUtilisation,
    required this.source,
    this.millis,
    this.offline = false,
    this.expectedVisitors,
    this.recommendedQuota,
    this.classicQuota,
    this.rainShare,
    this.disclaimer = '',
    this.lastEntryHour,
    this.reversibleTrails = const [],
    this.mainTrail,
    this.calibration,
  });

  /// A5: chance of really being over capacity for a forecast fullness, from the model's validation year:
  /// (bin lower edges of forecast ÷ capacity, chance). Null in older packs.
  final (List<double>, List<double>)? calibration;

  /// Chance (0..1) that a section is really over capacity at an hour, given its forecast. Null without a table.
  double? chanceOver(Section s, int hour) {
    final c = calibration;
    if (c == null) return null;
    final u = s.utilisation(hour);
    var i = 0;
    while (i + 1 < c.$1.length && u >= c.$1[i + 1]) {
      i++;
    }
    return c.$2[i];
  }

  final double? lastEntryHour; // gate closes for new walkers (e.g. 13:00)
  final List<String> reversibleTrails; // loops that can be walked either way
  final String? mainTrail; // the busiest trail

  final String day;
  final List<Section> sections;
  final Map<String, TrailSummary> trails;
  final List<int> openHours;
  final double busyUtilisation;
  final String source; // phone (ST-GNN on this device) | planning (planning model, saved) | server
  final int? millis; // time the ST-GNN took on this phone
  final bool offline; // computed from the stored pack, no connection
  final int? expectedVisitors, recommendedQuota, classicQuota;
  final double? rainShare;
  final String disclaimer;

  /// The days a pack covers, in order: (date, source). "stgnn" = forecast on this phone, "planning" = the
  /// planning model's forecast saved in the pack. Older packs: just the pack's own day.
  static List<(String, String)> packDays(Map<String, dynamic> pack) {
    final days = ((pack['map'] as Map<String, dynamic>?)?['days'] as List?) ?? [];
    if (days.isEmpty) return [(pack['day'] as String, 'stgnn')];
    return [for (final d in days) ((d as Map)['date'] as String, d['source'] as String)];
  }

  /// From the edge pack (needs its "map" block). [date] picks a day of the week (default: the pack's day);
  /// [f] is the forecast the phone computed for that day (needed for "stgnn" days, ignored for "planning" days).
  factory BottleneckDay.fromPack(Map<String, dynamic> pack, EdgeForecast? f, {bool offline = false, String? date}) {
    final m = pack['map'] as Map<String, dynamic>;
    final day = date ?? pack['day'] as String;
    final block = [for (final d in (m['days'] as List?) ?? []) d as Map<String, dynamic>]
        .where((d) => d['date'] == day)
        .firstOrNull;
    final planned = block != null && block['source'] != 'stgnn';
    if (!planned && f == null) throw ArgumentError('The phone forecast for $day is needed');
    final cap = {for (final s in (block?['segments'] as List?) ?? []) (s as Map)['id'] as int: s};
    final plannedPeople = planned
        ? [for (final r in block['people'] as List) [for (final v in r as List) (v as num).toDouble()]]
        : null;
    final summary = block ?? m; // per-day totals, else the pack's day (older packs)
    final segs = [for (final s in m['segments'] as List) s as Map<String, dynamic>];
    final info = {for (final s in pack['segments'] as List) (s as Map)['id'] as int: s};
    return BottleneckDay(
      day: day,
      sections: [
        for (final s in segs)
          () {
            final id = s['id'] as int;
            final Map c = cap[id] ?? s;
            return Section(
              id: id,
              trail: info[id]?['trail'] as String? ?? '',
              poi: info[id]?['poi'] as String? ?? '',
              lines: _lines(s['lines']),
              people: [for (final row in plannedPeople ?? f!.people) row[id]],
              capacityAtOnce: _d(c['capacity_at_once']),
              pcc: _i(c['pcc_per_day']),
              rcc: _i(c['rcc_per_day']),
              ecc: _i(c['ecc_per_day']),
              lengthM: _i(s['length_m']),
              minutesFromStart: (s['minutes_from_start'] as num?)?.toDouble(),
              minutesOnSection: (s['minutes_on_segment'] as num?)?.toDouble(),
            );
          }(),
      ],
      trails: _trails(summary['trails']),
      lastEntryHour: (m['last_entry_hour'] as num?)?.toDouble(),
      reversibleTrails: [for (final t in m['reversible_trails'] as List? ?? []) t as String],
      mainTrail: m['main_trail'] as String?,
      openHours: [for (final h in m['open_hours'] as List) (h as num).toInt()],
      busyUtilisation: _d(m['busy_utilisation'], 0.8),
      source: planned ? 'planning' : 'phone',
      millis: planned ? null : f!.millis,
      offline: offline,
      expectedVisitors: (summary['expected_visitors'] as num?)?.toInt(),
      recommendedQuota: (summary['recommended_daily_quota'] as num?)?.toInt(),
      classicQuota: (summary['classic_cifuentes_quota'] as num?)?.toInt(),
      rainShare: (summary['rain_share_open_hours'] as num?)?.toDouble(),
      disclaimer: m['disclaimer'] as String? ?? '',
      calibration: _calibration(m['calibration']),
    );
  }

  static (List<double>, List<double>)? _calibration(dynamic j) {
    if (j is! Map || j['bins'] is! List || j['p_over'] is! List) return null;
    return ([for (final v in j['bins'] as List) (v as num).toDouble()], [for (final v in j['p_over'] as List) (v as num).toDouble()]);
  }

  /// From GET /forecast/tomorrow and the segment lines of GET /trails/geometry (when no edge pack is available).
  factory BottleneckDay.fromServer(Map<String, dynamic> j, Map<int, List<List<List<double>>>> lines,
      {List<int>? openHours, double busyUtilisation = 0.8}) {
    final segs = [for (final s in j['segments'] as List) s as Map<String, dynamic>];
    final peakHours = {for (final s in segs) (s['peak_hour'] as num).toInt()};
    return BottleneckDay(
      day: j['forecast_date'] as String,
      sections: [
        for (final s in segs)
          Section(
            id: (s['seg_id'] as num).toInt(),
            trail: s['trail'] as String? ?? '',
            poi: s['poi'] as String? ?? '',
            lines: lines[(s['seg_id'] as num).toInt()] ?? const [],
            people: [for (final v in s['forecast_hourly'] as List) (v as num).toDouble()],
            capacityAtOnce: _d(s['capacity_at_once']),
            pcc: _i(s['pcc_per_day']),
            rcc: _i(s['rcc_per_day']),
            ecc: _i(s['ecc_per_day']),
            lengthM: _i(s['length_m']),
          ),
      ],
      trails: _trails(j['trails']),
      openHours: openHours ?? (peakHours.isEmpty ? List.generate(24, (h) => h) : _span(peakHours)),
      busyUtilisation: busyUtilisation,
      source: 'server',
      expectedVisitors: (j['expected_visitors'] as num?)?.toInt(),
      recommendedQuota: (j['recommended_daily_quota'] as num?)?.toInt(),
      classicQuota: (j['classic_cifuentes_quota'] as num?)?.toInt(),
      rainShare: (j['rain_share_open_hours'] as num?)?.toDouble(),
      disclaimer: j['disclaimer'] as String? ?? '',
    );
  }

  Crowding level(Section s, int hour) {
    final u = s.utilisation(hour);
    if (u > 1) return Crowding.over;
    if (u >= busyUtilisation) return Crowding.busy;
    if (u >= busyUtilisation / 2) return Crowding.filling;
    return Crowding.quiet;
  }

  /// Sections ranked by how full they are at `hour` (fullest first).
  List<Section> rankedAt(int hour) => [...sections]..sort((a, b) => b.utilisation(hour).compareTo(a.utilisation(hour)));

  /// The open hour with the most crowding (sum of utilisation over sections): where the slider starts.
  int get worstHour {
    var best = openHours.first, score = -1.0;
    for (final h in openHours) {
      final v = sections.fold<double>(0, (t, s) => t + s.utilisation(h).clamp(0, 3));
      if (v > score) (best, score) = (h, v);
    }
    return best;
  }

  /// Sections over capacity at some open hour, with their worst hour.
  List<(Section, int)> get bottlenecks => [
        for (final s in sections)
          if (openHours.any((h) => s.utilisation(h) > 1)) (s, s.peakHourIn(openHours)),
      ]..sort((a, b) => b.$1.utilisation(b.$2).compareTo(a.$1.utilisation(a.$2)));

  int countAt(int hour, Crowding c) => sections.where((s) => level(s, hour) == c).length;

  /// "World's End", or "World's End loop · section 7" (`short`: "Section 7", when the trail is already shown).
  String nameOf(Section s, {bool short = false}) {
    if (s.poi.isNotEmpty) return poiLabel(s.poi);
    final k = sections.where((x) => x.trail == s.trail).toList().indexOf(s) + 1;
    return short ? 'Section $k' : '${trails[s.trail]?.name ?? s.trail} · section $k';
  }

  /// The sections of one trail, fullest (at its own busiest hour) first.
  List<Section> sectionsOf(String trail) => sections.where((s) => s.trail == trail).toList()
    ..sort((a, b) => b.utilisation(b.peakHourIn(openHours)).compareTo(a.utilisation(a.peakHourIn(openHours))));

  static String poiLabel(String poi) => switch (poi) {
        'worlds_end' => "World's End",
        'mini_worlds_end' => "Mini World's End",
        'bakers_falls' => "Baker's Falls",
        'entrance' => 'Visitor Center',
        'summit' => 'Summit (final steps)',
        _ => poi.startsWith('half_')
            ? 'Halfway rest · ${poi.substring(5)}'
            : poi.startsWith('head_')
                ? 'Start · ${poi.substring(5)}'
                : poi.replaceAll('_', ' ').replaceFirstMapped(RegExp(r'^\w'), (m) => m[0]!.toUpperCase()),
      };

  static List<int> _span(Set<int> hours) {
    final lo = hours.reduce((a, b) => a < b ? a : b), hi = hours.reduce((a, b) => a > b ? a : b);
    return [for (var h = lo; h <= hi; h++) h];
  }

  static Map<String, TrailSummary> _trails(Object? j) => {
        for (final e in (j as Map<String, dynamic>? ?? {}).entries)
          e.key: TrailSummary.fromJson(e.key, e.value as Map<String, dynamic>),
      };

  static List<List<List<double>>> _lines(Object? j) => [
        for (final l in j as List? ?? [])
          [for (final p in l as List) [((p as List)[0] as num).toDouble(), (p[1] as num).toDouble()]],
      ];

  static double _d(Object? v, [double fallback = 0]) => (v as num?)?.toDouble() ?? fallback;
  static int _i(Object? v) => (v as num?)?.round() ?? 0;
}

class Section {
  Section({
    required this.id,
    required this.trail,
    required this.poi,
    required this.lines,
    required this.people,
    required this.capacityAtOnce,
    required this.pcc,
    required this.rcc,
    required this.ecc,
    required this.lengthM,
    this.minutesFromStart,
    this.minutesOnSection,
  });

  final double? minutesFromStart; // walking minutes from the trail start (usual direction) to this section
  final double? minutesOnSection; // minutes spent on it (walking at leisure + viewpoint stop)
  final int id;
  final String trail, poi;
  final List<List<List<double>>> lines; // [part][point][lon, lat]
  final List<double> people; // forecast people on the section, hour 0..23
  final double capacityAtOnce; // people it holds at Cifuentes social spacing
  final int pcc, rcc, ecc; // visits per day: physical, real, effective carrying capacity
  final int lengthM;

  double peopleAt(int hour) => hour >= 0 && hour < people.length ? people[hour] : 0;

  double utilisation(int hour) => capacityAtOnce <= 0 ? 0 : peopleAt(hour) / capacityAtOnce;

  int peakHourIn(List<int> hours) => hours.reduce((a, b) => peopleAt(b) > peopleAt(a) ? b : a);
}

class TrailSummary {
  TrailSummary({
    required this.id,
    required this.name,
    required this.expected,
    required this.recommended,
    required this.classic,
    required this.limitingSegment,
    required this.factors,
  });

  final String id, name;
  final int expected, recommended, classic, limitingSegment;
  final Map<String, double> factors;

  factory TrailSummary.fromJson(String id, Map<String, dynamic> j) => TrailSummary(
        id: id,
        name: j['name'] as String? ?? id,
        expected: (j['expected_visitors'] as num?)?.round() ?? 0,
        recommended: (j['recommended_daily_quota'] as num?)?.round() ?? 0,
        classic: (j['classic_cifuentes_quota'] as num?)?.round() ?? 0,
        limitingSegment: (j['limiting_segment'] as num?)?.toInt() ?? -1,
        factors: {
          for (final e in (j['factors'] as Map<String, dynamic>? ?? {}).entries) e.key: (e.value as num).toDouble(),
        },
      );
}
