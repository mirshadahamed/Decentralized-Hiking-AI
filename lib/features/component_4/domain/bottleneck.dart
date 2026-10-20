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
  });

  final String day;
  final List<Section> sections;
  final Map<String, TrailSummary> trails;
  final List<int> openHours;
  final double busyUtilisation;
  final String source; // phone | server
  final int? millis; // time the ST-GNN took on this phone
  final bool offline; // computed from the stored pack, no connection
  final int? expectedVisitors, recommendedQuota, classicQuota;
  final double? rainShare;
  final String disclaimer;

  /// From the edge pack (needs its "map" block) and the forecast the phone just computed from it.
  factory BottleneckDay.fromPack(Map<String, dynamic> pack, EdgeForecast f, {bool offline = false}) {
    final m = pack['map'] as Map<String, dynamic>;
    final segs = [for (final s in m['segments'] as List) s as Map<String, dynamic>];
    final info = {for (final s in pack['segments'] as List) (s as Map)['id'] as int: s};
    return BottleneckDay(
      day: pack['day'] as String,
      sections: [
        for (final s in segs)
          Section(
            id: s['id'] as int,
            trail: info[s['id']]?['trail'] as String? ?? '',
            poi: info[s['id']]?['poi'] as String? ?? '',
            lines: _lines(s['lines']),
            people: [for (final row in f.people) row[s['id'] as int]],
            capacityAtOnce: _d(s['capacity_at_once']),
            pcc: _i(s['pcc_per_day']),
            rcc: _i(s['rcc_per_day']),
            ecc: _i(s['ecc_per_day']),
            lengthM: _i(s['length_m']),
          ),
      ],
      trails: _trails(m['trails']),
      openHours: [for (final h in m['open_hours'] as List) (h as num).toInt()],
      busyUtilisation: _d(m['busy_utilisation'], 0.8),
      source: 'phone',
      millis: f.millis,
      offline: offline,
      expectedVisitors: (m['expected_visitors'] as num?)?.toInt(),
      recommendedQuota: (m['recommended_daily_quota'] as num?)?.toInt(),
      classicQuota: (m['classic_cifuentes_quota'] as num?)?.toInt(),
      rainShare: (m['rain_share_open_hours'] as num?)?.toDouble(),
      disclaimer: m['disclaimer'] as String? ?? '',
    );
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
  });

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
