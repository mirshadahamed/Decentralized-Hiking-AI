// Widget tests for Component 4 with a fake API (no server needed).
import 'dart:convert';
import 'dart:io';

import 'package:decentralized_hiking_ai/app/app.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/component4_home.dart';
import 'package:decentralized_hiking_ai/features/component_4/data/api_client.dart';
import 'package:decentralized_hiking_ai/features/component_4/models/models.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/screens/bottleneck_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/screens/staff/capacity_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/screens/staff/count_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/screens/staff/halfway_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/screens/staff/sightings_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/screens/staff/officer_home.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/screens/staff/records_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/screens/staff/ranger_home.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/screens/visitor/day_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/screens/visitor/map_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/screens/visitor/start_times_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/l10n/c4_i18n.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/widgets/c4_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:shared_preferences/shared_preferences.dart';

final today = DateTime(2026, 10, 15);
final visit = DateTime(2026, 11, 24);

Map<String, dynamic> outlookDay(DateTime d, int level) => {
      'date': C4Api.day(d),
      'lead_days': d.difference(today).inDays,
      'crowd_level': level,
      'visitors': {'p10': 666, 'p50': 867, 'p90': 1104},
      'visitors_by_trail_p50': {'main': 746, 'kirigalpotta': 43, 'thotupola': 78},
      'chance_wet_morning': 0.02,
      'weather_basis': 'typical weather',
    };

final planJson = {
  'target_date': '2026-11-24',
  'crowd_level': 4,
  'visitors': {'p10': 666, 'p50': 867, 'p90': 1104},
  'confidence': 'low (calendar and typical weather only)',
  'suggestions': [
    {'kind': 'date', 'title': 'Go on Wed 25 Nov instead', 'detail': 'about 300 people', 'reduction_pct': 60},
  ],
  'capacity': {
    'trails': {
      'main': {'name': "World's End loop", 'expected_visitors': 746, 'recommended_daily_quota': 273},
      'thotupola': {'name': 'Thotupola Kanda', 'expected_visitors': 78, 'recommended_daily_quota': 357},
    },
  },
};

Map<String, dynamic> window(String start, int wait, String reach, bool sunrise) => {
      'start': start,
      'expected_wait_min': wait,
      'reach_summit': reach,
      'before_sunrise': sunrise,
      'recommended': wait <= 20,
    };

final advisoryJson = {
  'day': '2026-12-23',
  'limit_min': 20,
  'flow_per_min': 25,
  'routes': {
    'nallathanniya': {
      'windows': [window('00:00', 0, '03:17', true), window('01:00', 15, '04:17', true), window('02:00', 95, '05:17', true), window('03:00', 140, '06:17', false)],
      'best_for_sunrise': '01:00',
      'recommended_for_sunrise': ['00:00', '01:00'],
      'shortest_wait': '00:00',
    },
    'palabaddala': {
      'windows': [window('00:00', 0, '05:30', true)],
      'best_for_sunrise': '00:00',
      'recommended_for_sunrise': ['00:00'],
      'shortest_wait': '00:00',
    },
  },
  'summit': {
    'peak_queue_people': 2140,
    'peak_wait_min': 86,
    'peak_at': '05:15',
    'bin_min': 15,
    'wait_by_time': [for (var i = 0; i < 96; i++) i >= 18 && i < 26 ? 40 : 0],
    'hold_windows': [['04:30', '06:30']],
  },
  'halfway': {
    'nallathanniya': {'release_per_10_min': 194, 'walk_to_summit_min': 143, 'hold_windows': [['02:07', '04:07']]},
    'palabaddala': {'release_per_10_min': 30, 'walk_to_summit_min': 142, 'hold_windows': [['02:08', '04:08']]},
  },
  'high_case': {
    'visitors': 9965,
    'summit': {'peak_wait_min': 120, 'wait_by_time': [for (var i = 0; i < 96; i++) i >= 16 && i < 30 ? 70 : 0], 'hold_windows': [['04:00', '07:30']]},
    'halfway': {
      'nallathanniya': {'release_per_10_min': 194, 'walk_to_summit_min': 143, 'hold_windows': [['01:37', '05:07']]},
    },
  },
};

Map<String, dynamic> seasonNight(String date, String checks) => {
      'date': date,
      'crowd_level': checks == 'none' ? 2 : 5,
      'visitors': {'p10': 5408, 'p50': 7198, 'p90': 9965},
      'peak_queue_people': 0,
      'peak_wait_min': checks == 'needed' ? 70 : 5,
      'peak_at': '05:00',
      'hold_windows': checks == 'needed' ? [['04:15', '07:45']] : [],
      'high_peak_wait_min': 90,
      'high_hold_windows': checks == 'none' ? [] : [['04:00', '08:00']],
      'checks': checks,
    };

final geometryJson = {
  'type': 'FeatureCollection',
  'features': [
    {
      'type': 'Feature',
      'properties': {'trail': 'nallathanniya', 'poi': 'head_nallathanniya'},
      'geometry': {'type': 'LineString', 'coordinates': [[80.50, 6.83], [80.50, 6.82]]},
    },
    {
      'type': 'Feature',
      'properties': {'trail': 'nallathanniya', 'poi': 'summit'},
      'geometry': {'type': 'LineString', 'coordinates': [[80.50, 6.82], [80.4994, 6.8096]]},
    },
  ],
};

Map<String, dynamic> checkpointJson(bool hold) => {
      'day': '2026-12-23',
      'time': '02:10',
      'queue_now_people': hold ? 900 : 0,
      'wait_now_min': hold ? 36 : 0,
      'ahead_min': 158,
      'wait_ahead_max_min': hold ? 64 : 0,
      'action': hold ? 'HOLD at the halfway checks: release only the listed number per 10 minutes' : 'Normal: let groups continue',
      'hold': hold,
      'checkpoints': [
        {
          'route': 'nallathanniya',
          'name': 'Nallathanniya (Hatton)',
          'release_per_10_min': hold ? 194 : null,
          'walk_to_summit_min': 143,
          'counted_today': hold ? 900 : 0,
          'last_count_at': hold ? '02:10' : null,
          'planned_hold': [],
          'planned_hold_if_busy': [['01:37', '05:07']],
        },
        {'route': 'palabaddala', 'name': 'Palabaddala (Ratnapura)', 'release_per_10_min': hold ? 30 : null, 'walk_to_summit_min': 142, 'counted_today': 0},
      ],
      'log': hold
          ? [
              {'route': 'nallathanniya', 'name': 'Nallathanniya (Hatton)', 'time': '02:10', 'count': 500, 'by': 'ranger1'},
              {'route': 'nallathanniya', 'name': 'Nallathanniya (Hatton)', 'time': '02:00', 'count': 400, 'by': 'ranger1'},
            ]
          : [],
    };

final horton = ParkInfo.fromJson({
  'id': 'horton_plains',
  'name': 'Horton Plains National Park',
  'kind': 'national_park',
  'region': 'Central Highlands',
  'summary': 'High-altitude plateau ending at World\'s End.',
  'elevation': '2,100 – 2,389 m',
  'best_time': 'Early morning, before the mist rises.',
  'getting_there': 'By road via Ohiya or Pattipola.',
  'facts': ['No plastic in the park'],
  'accent': '#2F6B4F',
  'booking_mode': 'required',
  'trails': {'main': "World's End loop", 'thotupola': 'Thotupola Kanda'},
});

final adamsPeak = ParkInfo.fromJson({
  'id': 'adams_peak',
  'name': "Adam's Peak (Sri Pada)",
  'kind': 'pilgrimage',
  'region': 'Peak Wilderness',
  'summary': 'Sacred mountain climbed by night.',
  'elevation': 'about 2,240 m',
  'best_time': 'December to May; weekdays away from Poya.',
  'getting_there': 'Hatton to Dalhousie.',
  'facts': ['Dress modestly'],
  'accent': '#8A4B2A',
  'booking_mode': 'advisory',
  'trails': {'nallathanniya': 'Nallathanniya (Hatton)', 'palabaddala': 'Palabaddala (Ratnapura)'},
});

Map<String, dynamic> capacityJson({String mainLevel = 'good'}) => {
      'day': '2026-11-24',
      'rain_share_open_hours': 0.58,
      'weather_basis': 'weather forecast',
      'ground': {'rain_mm': 67.8, 'days': 3, 'wetness': 1.0, 'basis': 'forecast rain'},
      'total_safe_limit': 516,
      'total_expected': 338,
      'trails': [
        {
          'trail': 'main',
          'name': "World's End loop",
          'expected_visitors': 291,
          'safe_limit': mainLevel == 'closed' ? 0 : 107,
          'over_limit': true,
          'condition': mainLevel == 'good' ? {'level': 'good', 'note': '', 'factor': 0.0} : {'level': mainLevel, 'note': 'wet boardwalk', 'factor': 0.2},
          'factors': [
            {'key': 'precipitation', 'label': 'rain during opening hours', 'pct': 58},
            {'key': 'wet_ground', 'label': 'ground still wet from earlier rain', 'pct': 12},
            {'key': 'condition', 'label': 'trail condition', 'pct': mainLevel == 'good' ? 0 : 20},
            {'key': 'crowding', 'label': 'expected crowding at the busiest place', 'pct': 16},
          ],
        },
        {
          'trail': 'thotupola',
          'name': 'Thotupola Kanda',
          'expected_visitors': 30,
          'safe_limit': 218,
          'over_limit': false,
          'condition': {'level': 'good', 'note': '', 'factor': 0.0},
          'factors': [
            {'key': 'precipitation', 'label': 'rain during opening hours', 'pct': 58},
          ],
        },
      ],
    };

class FakeApi extends C4Api {
  FakeApi({this.full = false, this.loginOk = true, this.withParks = false, this.role = 'ranger'}) : super(baseUrl: 'http://fake');

  final bool full, loginOk, withParks;
  final String role;
  int bookings = 0, recorded = 0, refreshes = 0;
  String mainLevel = 'good';

  @override
  Future<DayCapacity> capacity(DateTime d) async => DayCapacity.fromJson(capacityJson(mainLevel: mainLevel));

  @override
  Future<List<Map<String, dynamic>>> setCondition(String trail, DateTime from, DateTime to, String level, String note) async {
    mainLevel = level;
    return [
      {'day': '2026-11-24', 'trail': trail, 'slot': '07:00', 'booked': 18, 'safe_places': 12, 'reason': 'trail condition'},
    ];
  }

  bool get _ap => park == 'adams_peak';

  @override
  Future<List<ParkInfo>?> parks() async => withParks ? [horton, adamsPeak] : null;

  @override
  Future<ParkInfo> destination() async => _ap ? adamsPeak : horton;

  @override
  Future<List<SeasonNight>> season() async => [
        SeasonNight.fromJson(seasonNight('2026-12-23', 'standby')),
        SeasonNight.fromJson(seasonNight('2026-12-24', 'none')),
        SeasonNight.fromJson(seasonNight('2026-12-25', 'needed')),
      ];

  @override
  Future<Map<String, dynamic>> refresh() async {
    refreshes++;
    return {'today': '2026-10-16'};
  }

  @override
  Future<ServerStatus> status() async => _ap
      ? ServerStatus(today: today, refreshedAt: '', note: '', park: 'adams_peak', site: "Adam's Peak (Sri Pada)", bookingMode: 'advisory')
      : ServerStatus(today: today, refreshedAt: '', note: '');

  @override
  Future<StartAdvice> advisory(DateTime d) async => StartAdvice.fromJson(advisoryJson);

  @override
  Future<List<MapSegment>> geometry() async => MapSegment.fromGeoJson(geometryJson);

  @override
  Future<CheckpointStatus> checkpoints(DateTime d, {String? at}) async => CheckpointStatus.fromJson(checkpointJson(recorded > 0));

  @override
  Future<CheckpointStatus> recordCheckpoint(String route, int count, {DateTime? at}) async {
    recorded += count;
    return CheckpointStatus.fromJson(checkpointJson(true));
  }

  @override
  Future<Outlook> outlook({String? forPark}) async => Outlook(
        issueDate: today,
        days: [OutlookDay.fromJson(outlookDay(today.add(const Duration(days: 1)), 2)), OutlookDay.fromJson(outlookDay(visit, 4))],
        trailNames: {'main': "World's End loop"},
        disclaimer: 'Estimated.',
      );

  @override
  Future<List<TrailInfo>> trails() async => _ap
      ? [
          TrailInfo(id: 'nallathanniya', name: 'Nallathanniya (Hatton)', lengthKm: 4.5, about: ''),
          TrailInfo(id: 'palabaddala', name: 'Palabaddala (Ratnapura)', lengthKm: 8.3, about: ''),
        ]
      : [
          TrailInfo(id: 'main', name: "World's End loop", lengthKm: 7.5, about: 'Main loop'),
          TrailInfo(id: 'thotupola', name: 'Thotupola Kanda', lengthKm: 1.3, about: 'Short peak'),
        ];

  @override
  Future<DayPlan> plan(DateTime d) async => DayPlan.fromPlanJson(planJson);

  @override
  Future<DaySlots> slots(DateTime d) async => DaySlots(day: d, basis: 'typical weather', slots: [
        SlotInfo(slot: '07:00', trail: 'main', placesLeft: 18, bookable: 20, closed: false),
        SlotInfo(slot: '07:30', trail: 'main', placesLeft: 0, bookable: 20, closed: false),
        SlotInfo(slot: '07:00', trail: 'thotupola', placesLeft: 20, bookable: 20, closed: false),
      ]);

  @override
  Future<Booking> book(DateTime d, String trail, String slot, int groupSize) async {
    if (full) {
      throw ApiException(409, 'Only 1 places left in this slot.', alternatives: [
        Alternative(day: d, trail: 'thotupola', slot: '07:00', left: 20, kind: 'trail'),
      ]);
    }
    bookings++;
    return Booking(code: 'ABCD2345', day: d, trail: trail, slot: slot, groupSize: groupSize, status: 'booked');
  }

  @override
  Future<StaffSession> login(String username, String password) async {
    if (!loginOk) throw ApiException(401, 'Wrong username or password, or account locked');
    return session = StaffSession(token: 't', username: username, role: role);
  }

  @override
  Future<List<WalkInSlot>> walkIns(DateTime d) async => [WalkInSlot(slot: '07:00', trail: 'main', left: 5)];

  @override
  Future<List<LiveSegment>> live(DateTime d, {String? at}) async => [];
}

/// Serves the edge-pack fixture (a pack for 2025-04-11) and "today" = the day before; can go offline
/// (only the pack download fails) or into airplane mode (every call fails).
class _EdgeApi extends FakeApi {
  bool online = true;
  bool airplane = false;

  @override
  Future<ServerStatus> status() async {
    if (airplane) throw ApiException(0, 'Cannot reach the park server.');
    return ServerStatus(today: DateTime(2025, 4, 10), refreshedAt: '', note: '');
  }

  @override
  Future<Map<String, dynamic>> tomorrow() async => {
        'forecast_date': '2025-04-11',
        'expected_visitors': 900,
        'trails': (planJson['capacity'] as Map)['trails'],
      };

  @override
  Future<Map<String, dynamic>> edgePack() async {
    if (!online) throw ApiException(0, 'Cannot reach the park server.');
    return jsonDecode(File('test/component_4/fixtures/edge_pack.json').readAsStringSync()) as Map<String, dynamic>;
  }
}

/// Officer records: 3 trails a day; remembers the last request (dates, trail).
class _RecordsApi extends FakeApi {
  _RecordsApi() : super(role: 'officer');

  DateTime? start, end;
  String? trailAsked;

  @override
  Future<List<TrailInfo>> trails() async => [
        TrailInfo(id: 'main', name: "World's End loop", lengthKm: 7.5, about: ''),
        TrailInfo(id: 'kirigalpotta', name: 'Kirigalpotta', lengthKm: 5.1, about: ''),
      ];

  @override
  Future<CrowdRecords> records(DateTime start, DateTime end, {String? trail}) async {
    this.start = start;
    this.end = end;
    trailAsked = trail;
    final rows = <RecordRow>[];
    for (var d = start; !d.isAfter(end); d = d.add(const Duration(days: 1))) {
      final period = d.isBefore(today) ? 'past' : d == today ? 'today' : 'future';
      for (final (id, name, n) in [('main', "World's End loop", 300), ('kirigalpotta', 'Kirigalpotta', 20)]) {
        if (trail != null && trail != id) continue;
        rows.add(RecordRow(
          date: d, trail: id, trailName: name, period: period,
          visitors: n + d.day, low: period == 'future' ? n - 50 : null, high: period == 'future' ? n + 80 : null,
          source: period == 'future' ? 'forecast (planning model)' : 'estimate (simulated with real weather)',
          booked: period == 'past' ? 0 : 4, checkedIn: period == 'today' ? 3 : 0, gateTotal: period == 'today' ? 3 : 0,
          safeLimit: id == 'main' ? 310 : 200,
        ));
      }
    }
    return CrowdRecords(site: 'Horton Plains National Park', today: today,
        trails: {'main': "World's End loop", 'kirigalpotta': 'Kirigalpotta'}, rows: rows, note: 'estimates');
  }
}

/// Officer capacity panel: one trail; remembers the rule chosen.
class _QuotaApi extends FakeApi {
  _QuotaApi() : super(role: 'officer');

  String rule = 'forecast';
  int? manual;

  @override
  Future<CapacityPanel> capacityPanel(DateTime d) async => CapacityPanel.fromJson({
        'day': C4Api.day(d),
        'rules': {'forecast': 'a', 'classic': 'b', 'static': 'c', 'manual': 'd'},
        'default_rule': 'forecast',
        'trails': [
          {
            'trail': 'main', 'name': "World's End loop", 'expected_visitors': 300,
            'quota': {'forecast': 175, 'classic': 351, 'static': 400, 'manual': manual, 'rule': rule,
              'applied': {'forecast': 175, 'classic': 351, 'static': 400}[rule] ?? manual, 'decided_by': rule == 'forecast' ? null : 'off'},
            'limiting_section': "World's End", 'reason': "World's End is expected over capacity 10-12 h",
            'sections_over_capacity': 1,
          }
        ],
        'over_capacity': [
          {'seg_id': 25, 'trail': 'main', 'name': "World's End", 'hours': [10, 11], 'peak_people': 52.0, 'capacity_at_once': 30.0}
        ],
        'basis': {'crowd': 'ST-GNN day-ahead', 'weather': 'forecast', 'sensors': 'No counters inside the trail',
          'evidence': 'RQ9 replay'},
      });

  @override
  Future<List<Map<String, dynamic>>> setQuota(DateTime d, String trail, String rule, {int? quota}) async {
    this.rule = rule;
    manual = quota;
    return [];
  }
}

/// Ranger spot counts: the server can be switched off (no signal); counts it received are kept.
class _CountApi extends FakeApi {
  _CountApi() : super(role: 'ranger');

  bool online = true;
  final received = <String, SpotCount>{};

  @override
  Future<List<SegmentInfo>> segments() async => [
        SegmentInfo(segId: 3, name: 'Mini World\'s End', trail: 'main', trailName: "World's End loop"),
        SegmentInfo(segId: 25, name: "World's End", trail: 'main', trailName: "World's End loop"),
      ];

  @override
  Future<void> addCount(SpotCount c) async {
    if (!online) throw ApiException(0, 'Cannot reach the park server.');
    received[c.clientId] = c;
  }

  @override
  Future<ForecastCheck> forecastCheck(DateTime start, DateTime end) async => ForecastCheck.fromJson({
        'summary': {'counts': 2, 'with_forecast': 2, 'mae': 6.5, 'bias': 2.5, 'within_30pct': 0.5,
          'counted_over_capacity': 1, 'over_capacity_called': 1, 'false_alarms': 0},
        'rows': [
          {'day': C4Api.day(today), 'seg_id': 25, 'name': "World's End", 'time_min': 620, 'count': 40, 'forecast': 44.0,
            'capacity_at_once': 30.0, 'counted_over': true, 'forecast_over': true},
          {'day': C4Api.day(today), 'seg_id': 3, 'name': "Mini World's End", 'time_min': 560, 'count': 12, 'forecast': 3.0,
            'capacity_at_once': 30.0, 'counted_over': false, 'forecast_over': false},
        ],
        'note': 'day-ahead forecast',
      });
}

class _AdvisoryApi extends FakeApi {
  _AdvisoryApi(this.json);

  final Map<String, dynamic> json;

  @override
  Future<StartAdvice> advisory(DateTime d) async => StartAdvice.fromJson(json);
}

Widget wrap(Widget child, C4Api api) => MaterialApp(home: C4Scope(api: api, child: child));

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('models parse the API JSON', () {
    final p = DayPlan.fromPlanJson(planJson);
    expect(p.crowdLevel, 4);
    expect(p.trails['main']!.quota, 273);
    expect(p.suggestions.single.reductionPct, 60);
    final d = OutlookDay.fromJson(outlookDay(visit, 4));
    expect(d.byTrail['thotupola'], 78);
    final b = Booking(code: 'X', day: visit, trail: 'main', slot: '07:00', groupSize: 2, status: 'booked');
    expect(b.gateOpens, DateTime(2026, 11, 24, 6, 45));
    expect(Booking.fromJson(b.toJson()).slot, '07:00');
  });

  testWidgets('calendar shows the outlook; tapping a day opens it', (t) async {
    await t.pumpWidget(MaterialApp(home: Component4Home(api: FakeApi())));
    await t.pumpAndSettle();
    await t.tap(find.text('Plan & book'));
    await t.pumpAndSettle();
    expect(find.text('When do you want to visit?'), findsOneWidget);
    expect(find.text('Very busy'), findsOneWidget);
    final handle = t.ensureSemantics();
    final day = find.bySemanticsLabel(RegExp('Tue 24 Nov 2026'));
    await t.scrollUntilVisible(day, 200, scrollable: find.byType(Scrollable).first);
    await t.drag(find.byType(Scrollable).first, const Offset(0, -150)); // clear of the bottom navigation bar
    await t.pumpAndSettle();
    await t.tap(day);
    await t.pumpAndSettle();
    expect(find.text('Expected crowd'), findsOneWidget);          // the day screen got the API
    handle.dispose();
  });

  testWidgets('booking a slot ends on the ticket with its code', (t) async {
    final api = FakeApi();
    await t.pumpWidget(wrap(DayScreen(day: visit), api));
    await t.pumpAndSettle();
    expect(find.text('Want a quieter visit?'), findsOneWidget);
    await t.scrollUntilVisible(find.text('07:00 · 18 left'), 200);
    await t.tap(find.text('07:00 · 18 left'));
    await t.pump();
    await t.scrollUntilVisible(find.textContaining('Book 2 places'), 200);
    await t.tap(find.textContaining('Book 2 places'));
    await t.pumpAndSettle();
    expect(api.bookings, 1);
    expect(find.text('ABCD2345'), findsOneWidget);
    expect(find.textContaining('06:45'), findsOneWidget);
  });

  testWidgets('a full slot offers alternatives instead of an error', (t) async {
    await t.pumpWidget(wrap(DayScreen(day: visit), FakeApi(full: true)));
    await t.pumpAndSettle();
    await t.scrollUntilVisible(find.text('07:00 · 18 left'), 200);
    await t.tap(find.text('07:00 · 18 left'));
    await t.pump();
    await t.scrollUntilVisible(find.textContaining('Book 2 places'), 200);
    await t.tap(find.textContaining('Book 2 places'));
    await t.pumpAndSettle();
    expect(find.text('That time just filled up'), findsOneWidget);
    expect(find.textContaining('Thotupola'), findsWidgets);
  });

  testWidgets('staff login: a wrong password shows an error', (t) async {
    await t.pumpWidget(MaterialApp(home: Component4Home(api: FakeApi(loginOk: false))));
    await t.pumpAndSettle();
    await t.tap(find.text('Staff'));
    await t.pumpAndSettle();
    await t.enterText(find.byType(TextField).first, 'ranger1');
    await t.enterText(find.byType(TextField).last, 'nope');
    await t.tap(find.text('Log in'));
    await t.pumpAndSettle();
    expect(find.textContaining('Wrong username'), findsOneWidget);
  });

  testWidgets('staff login: a ranger lands on the gate tools', (t) async {
    await t.pumpWidget(MaterialApp(home: Component4Home(api: FakeApi())));
    await t.pumpAndSettle();
    await t.tap(find.text('Staff'));
    await t.pumpAndSettle();
    await t.enterText(find.byType(TextField).first, 'ranger1');
    await t.enterText(find.byType(TextField).last, 'correct-horse');
    await t.tap(find.text('Log in'));
    await t.pumpAndSettle();
    expect(find.text('Check in'), findsOneWidget);
    expect(find.text('Walk-ins'), findsOneWidget);
  });

  test('advisory, checkpoint and map models parse the API JSON', () {
    final a = StartAdvice.fromJson(advisoryJson);
    expect(a.routes['nallathanniya']!.bestForSunrise, '01:00');
    expect(a.routes['nallathanniya']!.windows[2].recommended, isFalse);
    expect(a.peakQueue, 2140);
    final c = CheckpointStatus.fromJson(checkpointJson(true));
    expect(c.hold, isTrue);
    expect(c.checkpoints.first.releasePer10Min, 194);
    expect(CheckpointStatus.fromJson(checkpointJson(false)).checkpoints.first.releasePer10Min, isNull);
    final segs = MapSegment.fromGeoJson(geometryJson);
    expect(segs.length, 2);
    expect(segs.last.points.last, [80.4994, 6.8096]);
  });

  test('the park prefix goes in front of every call', () {
    final api = C4Api(baseUrl: 'http://h:8000');
    api.usePark('adams_peak');
    expect(api.park, 'adams_peak');
    api.session = StaffSession(token: 't', username: 'u', role: 'ranger');
    api.usePark('horton_plains');
    expect(api.session, isNull); // staff accounts belong to one park
  });

  test('destination and season models parse the API JSON', () {
    expect(adamsPeak.kind, 'pilgrimage');
    expect(adamsPeak.accent, 0xFF8A4B2A);
    expect(adamsPeak.isAdvisory, isTrue);
    final n = SeasonNight.fromJson(seasonNight('2026-12-25', 'needed'));
    expect(windowsText(n.holdWindows), '04:15–07:45');
    final a = StartAdvice.fromJson(advisoryJson);
    expect(a.waitByTime.length, 96);
    expect(a.highVisitors, 9965);
    expect(a.halfway['nallathanniya']!.holdWindows.single, ['02:07', '04:07']);
    expect(CheckpointStatus.fromJson(checkpointJson(true)).log.first.count, 500);
  });

  testWidgets('trip planner: destinations with a week strip, a filter by kind, then the destination overview', (t) async {
    await t.pumpWidget(MaterialApp(home: Component4Home(api: FakeApi(withParks: true), lang: C4Lang())));
    await t.pumpAndSettle();
    expect(find.text('Where to?'), findsOneWidget);
    expect(find.text('Next 7 days'), findsWidgets);
    expect(find.textContaining('Quietest:'), findsWidgets);
    await t.tap(find.widgetWithText(ChoiceChip, 'Pilgrimage'));    // filter by kind
    await t.pumpAndSettle();
    expect(find.text('Horton Plains National Park'), findsNothing);
    await t.tap(find.text("Adam's Peak (Sri Pada)"));
    await t.pumpAndSettle();
    expect(find.text('Sacred mountain climbed by night.'), findsOneWidget);   // overview of the destination
    expect(find.text('My tickets'), findsNothing);                           // pilgrim site: no tickets
    await t.scrollUntilVisible(find.text('Getting there'), 200);
    expect(find.text('Hatton to Dalhousie.'), findsOneWidget);
    await t.scrollUntilVisible(find.text('Plan your climb'), -200);
    await t.tap(find.text('Plan your climb'));
    await t.pumpAndSettle();
    expect(find.text('When will you climb?'), findsOneWidget);
    await t.tap(find.byTooltip('All destinations'));                         // back to the list
    await t.pumpAndSettle();
    expect(find.text('Where to?'), findsOneWidget);
  });

  testWidgets('Adam\'s Peak officer: tonight, season plan and a night plan', (t) async {
    final api = FakeApi(withParks: true, role: 'officer');
    await t.pumpWidget(MaterialApp(home: Component4Home(api: api, lang: C4Lang())));
    await t.pumpAndSettle();
    await t.tap(find.text("Adam's Peak (Sri Pada)"));
    await t.pumpAndSettle();
    await t.tap(find.text('Staff'));
    await t.pumpAndSettle();
    await t.enterText(find.byType(TextField).first, 'officer1');
    await t.enterText(find.byType(TextField).last, 'correct-horse');
    await t.tap(find.text('Log in'));
    await t.pumpAndSettle();
    expect(find.text('Tonight'), findsOneWidget);                 // officer console, not the halfway screen
    expect(find.text('NORMAL'), findsOneWidget);
    expect(find.textContaining('stand by 01:37–05:07'), findsOneWidget);
    await t.dragUntilVisible(find.text('No counts yet tonight'), find.byType(ListView).first, const Offset(0, -200));
    await t.tap(find.text('Season'));
    await t.pumpAndSettle();
    expect(find.text('Checks needed'), findsWidgets);
    expect(find.text('Stand by'), findsWidgets);
    await t.tap(find.byType(SwitchListTile));                    // only nights that may need checks
    await t.pumpAndSettle();
    expect(find.text(niceDate(DateTime(2026, 12, 24))), findsNothing);
    await t.tap(find.text(niceDate(DateTime(2026, 12, 25))));
    await t.pumpAndSettle();
    expect(find.text('Night plan · Fri 25 Dec'), findsOneWidget);
    expect(find.textContaining('04:30–06:30'), findsOneWidget);   // likely queue window at the summit
    await t.scrollUntilVisible(find.textContaining('Hold: 02:07–04:07'), 200);
    expect(find.textContaining('If busier: 01:37–05:07'), findsOneWidget);
    await t.pageBack();
    await t.pumpAndSettle();
    await t.tap(find.byTooltip('Refresh forecasts'));
    await t.pumpAndSettle();
    expect(api.refreshes, 1);
  });

  testWidgets('start times: best start, good windows and the wait table', (t) async {
    final api = FakeApi()..usePark('adams_peak');
    await t.pumpWidget(wrap(StartTimesScreen(day: DateTime(2026, 12, 23)), api));
    await t.pumpAndSettle();
    expect(find.text('Best start for sunrise'), findsOneWidget);
    expect(find.text('01:00'), findsWidgets);
    expect(find.text('95 min'), findsOneWidget);   // in the table (before sunrise)
    expect(find.text('140 min'), findsNothing);    // reaches after sunrise: chart only
    await t.scrollUntilVisible(find.textContaining('Busiest at the summit around 05:15'), 200);
    await t.drag(find.byType(ListView), const Offset(0, 3000));          // back to the top
    await t.pumpAndSettle();
    await t.tap(find.text('Palabaddala (Ratnapura)'));
    await t.pumpAndSettle();
    expect(find.text('05:30'), findsOneWidget);
  });

  testWidgets('busy night: sunrise, slower climb with the crowd, early start and the evening plan', (t) async {
    final json = Map<String, dynamic>.from(advisoryJson)
      ..['sunrise'] = '06:10'
      ..['routes'] = {
        'nallathanniya': {
          'windows': [
            {'start': '22:30', 'start_min': -90, 'evening_before': true, 'expected_wait_min': 0, 'reach_summit': '02:05', 'climb_h': 3.6, 'before_sunrise': true, 'too_early': true, 'recommended': true},
            {'start': '23:30', 'start_min': -30, 'evening_before': true, 'expected_wait_min': 0, 'reach_summit': '03:05', 'climb_h': 3.6, 'before_sunrise': true, 'too_early': true, 'recommended': true},
            {'start': '01:30', 'start_min': 90, 'evening_before': false, 'expected_wait_min': 5, 'reach_summit': '09:22', 'climb_h': 7.6, 'before_sunrise': false, 'too_early': false, 'recommended': false},
          ],
          'best_for_sunrise': '23:30',
          'recommended_for_sunrise': ['22:30', '23:30'],
          'early_arrival_needed': true,
          'shortest_wait': '22:30',
          'climb_h': 3.6,
          'usual_start': '01:30',
          'usual_start_climb_h': 7.6,
          'usual_start_reaches': '09:22',
          'evening_plan': {
            'start_from': '18:00', 'start_to': '22:55', 'reach_hall_by': '00:00', 'leave_hall_at': '01:00',
            'reach_summit': '04:05', 'hall_people_expected': 1400, 'hall_capacity': 2000, 'hall_may_be_full': false,
          },
        },
      };
    final api = _AdvisoryApi(json)..usePark('adams_peak');
    await t.pumpWidget(wrap(StartTimesScreen(day: DateTime(2026, 12, 25)), api));
    await t.pumpAndSettle();
    expect(find.text('Sunrise at the summit: 06:10'), findsOneWidget);
    expect(find.text('23:30'), findsWidgets);
    expect(find.text('the evening before'), findsOneWidget);
    expect(find.textContaining('the climb takes about 3.6 h tonight'), findsOneWidget);
    expect(find.textContaining('Starting with the crowd at 01:30 takes about 7.6 h'), findsOneWidget);
    expect(find.textContaining('You will arrive early'), findsOneWidget);
    expect(find.text('23:30 · the evening before'), findsOneWidget);    // good start chip
    await t.scrollUntilVisible(find.text('Or start the evening before and rest on the way'), 200);
    expect(find.textContaining('leave the hall at 01:00'), findsOneWidget);
  });

  testWidgets('halfway check: recording a count turns the advice to HOLD with release rates', (t) async {
    final api = FakeApi()..usePark('adams_peak');
    await t.pumpWidget(wrap(const HalfwayScreen(), api));
    await t.pumpAndSettle();
    expect(find.text('NORMAL'), findsOneWidget);
    await t.tap(find.text('+50'));
    await t.tap(find.text('+10'));
    await t.pump();
    await t.tap(find.text('Record 60'));
    await t.pumpAndSettle();
    expect(api.recorded, 60);
    expect(find.text('HOLD'), findsOneWidget);
    await t.scrollUntilVisible(find.text('194'), 200);
    expect(find.text('194'), findsOneWidget);
  });

  testWidgets('language menu switches the visitor screens to Sinhala and Tamil', (t) async {
    final lang = C4Lang();
    await t.pumpWidget(MaterialApp(home: Component4Home(api: FakeApi(), lang: lang)));
    await t.pumpAndSettle();
    await t.tap(find.text('Plan & book'));
    await t.pumpAndSettle();
    expect(find.text('When do you want to visit?'), findsOneWidget);
    await t.tap(find.byIcon(Icons.translate));
    await t.pumpAndSettle();
    await t.tap(find.text('සිංහල').last);
    await t.pumpAndSettle();
    expect(lang.code, 'si');
    expect(find.text('ඔබ පැමිණීමට කැමති කවදාද?'), findsOneWidget);
    await lang.set('ta');
    await t.pumpAndSettle();
    expect(find.text('எப்போது வர விரும்புகிறீர்கள்?'), findsOneWidget);
    expect(find.text('கண்ணோட்டம்'), findsOneWidget);   // navigation label too
  });

  testWidgets('map shows the routes and the legend', (t) async {
    final api = FakeApi()..usePark('adams_peak');
    await t.pumpWidget(wrap(const Scaffold(body: MapScreen(showTiles: false)), api));
    await t.pumpAndSettle();
    expect(find.textContaining('Nallathanniya (Hatton) · 4.5 km'), findsOneWidget);
    expect(find.byIcon(Icons.flag), findsOneWidget);           // summit
    expect(find.byIcon(Icons.directions_walk), findsOneWidget); // trail head
  });

  test('safe-limit model parses the API JSON', () {
    final c = DayCapacity.fromJson(capacityJson(mainLevel: 'muddy'));
    expect(c.weatherBasis, 'weather forecast');
    expect(c.groundRainMm, 67.8);
    final main = c.forTrail('main')!;
    expect(main.safeLimit, 107);
    expect(main.overLimit, isTrue);
    expect(main.condition.label, 'muddy');
    expect(main.factors.first.pct, 58);
    expect(c.forTrail('thotupola')!.condition.isGood, isTrue);
  });

  testWidgets('day screen shows the safe limit and why it is that low', (t) async {
    final api = FakeApi()..mainLevel = 'muddy';
    await t.pumpWidget(wrap(DayScreen(day: visit), api));
    await t.pumpAndSettle();
    expect(find.text('Safe limit for this day'), findsOneWidget);
    expect(find.text('about 290 expected · safe 107'), findsOneWidget);   // expected / safe limit
    expect(find.text('muddy'), findsOneWidget);                  // reported condition
    expect(find.textContaining('More people expected than is safe'), findsOneWidget);
    expect(find.textContaining('68 mm of forecast rain in the last 3 days (wet ground)'), findsWidgets);
    await t.tap(find.text('Why this limit?'));
    await t.pumpAndSettle();
    expect(find.text("Why the limit on World's End loop is 107"), findsOneWidget);
    expect(find.text('Rain during opening hours'), findsOneWidget);
    expect(find.text('−58 %'), findsOneWidget);
    expect(find.text('Trail condition'), findsOneWidget);       // −20 % from the officer's report
  });

  testWidgets('officer reports a muddy trail and sees the new limits and affected bookings', (t) async {
    final api = FakeApi(role: 'officer');
    await t.pumpWidget(wrap(const Scaffold(body: ConditionTab()), api));
    await t.pumpAndSettle();
    expect(find.text('Report a trail condition'), findsOneWidget);
    await t.tap(find.text('Muddy'));
    await t.enterText(find.widgetWithText(TextField, 'Note (optional, shown to visitors)'), 'wet boardwalk');
    await t.tap(find.text('Save and re-plan tickets'));
    await t.pumpAndSettle();
    expect(api.mainLevel, 'muddy');
    await t.dragUntilVisible(find.textContaining('now over the limit'), find.byType(ListView).first, const Offset(0, -200));
    expect(find.textContaining('291 expected / 107 safe'), findsOneWidget);
    expect(find.textContaining('1 booked slot(s) now over the limit'), findsOneWidget);
  });

  testWidgets('officer at another park (Yala) sees and acts on its own trails', (t) async {
    final api = _YalaOfficerApi();
    await t.pumpWidget(wrap(const Scaffold(body: ConditionTab()), api));
    await t.pumpAndSettle();
    expect(find.text('Patanangala and Buthawa'), findsOneWidget);          // the park's first circuit is preselected
    expect(find.text("World's End loop"), findsNothing);
    await t.tap(find.text('Muddy'));
    await t.tap(find.text('Save and re-plan tickets'));
    await t.pumpAndSettle();
    expect(api.conditionTrail, 'patanangala');
  });

  testWidgets('tomorrow: the ST-GNN runs on the device, and keeps working offline from the stored pack', (t) async {
    final api = _EdgeApi();
    final card = find.text('Forecast made on this phone', skipOffstage: false);
    Future<void> open() async {
      await t.pumpWidget(wrap(DayScreen(key: UniqueKey(), day: DateTime(2025, 4, 11)), api));
      for (var i = 0; i < 40 && card.evaluate().isEmpty; i++) {     // real time for file reading + the forecast
        await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
        await t.pump();
      }
    }

    await open();
    expect(card, findsOneWidget);
    expect(find.textContaining('ms on this device', skipOffstage: false), findsOneWidget);
    expect(find.textContaining('people at', skipOffstage: false), findsWidgets);
    expect(find.text('offline copy', skipOffstage: false), findsNothing);
    api.online = false;                                    // no connection: the stored pack is used
    await open();
    expect(card, findsOneWidget);
    expect(find.text('offline copy', skipOffstage: false), findsOneWidget);
    api.airplane = true;                                   // airplane mode: the server cannot be reached at all
    await open();
    expect(card, findsOneWidget);
    expect(find.text('offline copy', skipOffstage: false), findsOneWidget);
    expect(find.textContaining('Cannot reach the park server', skipOffstage: false), findsOneWidget);
    await t.pumpWidget(wrap(DayScreen(key: UniqueKey(), day: DateTime(2025, 4, 20)), api)); // another day: no card
    for (var i = 0; i < 10; i++) {
      await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
      await t.pump();
    }
    expect(card, findsNothing);
  });

  testWidgets('bottleneck map: every section coloured by tomorrow\'s forecast, safe numbers per section, offline',
      (t) async {
    t.view.physicalSize = const Size(1179, 2556);
    t.view.devicePixelRatio = 3;
    addTearDown(t.view.reset);
    final api = _EdgeApi();
    final tab = find.byKey(const Key('tab_bottleneck_map'));
    Future<void> open() async {
      await t.pumpWidget(wrap(BottleneckScreen(key: UniqueKey(), showTiles: false), api));
      for (var i = 0; i < 40 && tab.evaluate().isEmpty; i++) {       // real time: read the pack, run the ST-GNN
        await t.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 100)));
        await t.pump();
      }
    }

    await open();
    expect(tab, findsOneWidget);
    expect(find.textContaining('ST-GNN on this phone'), findsOneWidget);
    expect(find.byKey(const Key('day_picker')), findsOneWidget);              // today + 6 days
    expect(find.text('Today'), findsOneWidget);
    expect(find.text('Tomorrow'), findsOneWidget);
    await t.tap(find.text('Sat 12 Apr'));                                    // day 3: planning model, saved
    await t.pump();
    expect(find.textContaining('Planning outlook'), findsOneWidget);
    await t.tap(find.text('Today'));
    await t.pump();
    expect(find.textContaining('ST-GNN on this phone'), findsOneWidget);
    expect(find.byKey(const Key('hour_slider')), findsOneWidget);
    expect(find.textContaining('of 48 sections'), findsOneWidget);
    expect(find.textContaining(' people'), findsWidgets);              // the fullest sections at that hour
    final before = find.textContaining('of 48 sections').evaluate().single.widget as Text;
    await t.drag(find.byKey(const Key('hour_slider')), const Offset(-400, 0)); // early morning: quieter
    await t.pump();
    final after = find.textContaining('of 48 sections').evaluate().single.widget as Text;
    expect(after.data, isNot(before.data));

    await t.tap(find.text('Safe numbers'));
    await t.pumpAndSettle();
    expect(find.text('Safe number of visitors that day'), findsOneWidget);
    expect(find.byKey(const Key('park_safe_number')), findsOneWidget);
    expect(find.text("World's End loop"), findsOneWidget);
    await t.tap(find.text("World's End loop"));
    await t.pumpAndSettle();
    expect(find.text('ECC/day'), findsOneWidget);
    final row = find.descendant(of: find.byType(ExpansionTile), matching: find.text("World's End"));
    await t.ensureVisible(row);
    await t.pumpAndSettle();
    await t.tap(row);                                                    // one section: hourly bars + PCC/RCC/ECC
    await t.pumpAndSettle();
    expect(find.text('Effective (ECC)'), findsOneWidget);
    expect(find.textContaining('Holds safely at once'), findsOneWidget);
    Navigator.of(t.element(find.text('Effective (ECC)'))).pop();          // close the section sheet
    await t.pumpAndSettle();
    await t.tap(find.text('Your walk'));                                  // offline walk advice (spread, not herd)
    await t.pumpAndSettle();
    expect(find.byKey(const Key('walk_pick')), findsOneWidget);
    expect(find.text('What most visitors will do'), findsOneWidget);
    expect(find.textContaining('Fullest place on the way'), findsWidgets);

    api.online = false;                                                  // airplane mode: the stored pack
    await open();
    expect(tab, findsOneWidget);
    expect(find.text('offline copy'), findsOneWidget);
  });

  testWidgets('ranger counts walkers with no signal; the counts are sent once the signal is back', (t) async {
    t.view.physicalSize = const Size(1179, 2556);
    t.view.devicePixelRatio = 3;
    addTearDown(t.view.reset);
    final api = _CountApi()..online = false;
    await t.pumpWidget(wrap(Scaffold(body: CountTab(now: () => DateTime(2026, 10, 22, 10, 15))), api));
    await t.pumpAndSettle();
    await t.tap(find.byKey(const Key('count_plus')));
    await t.tap(find.byKey(const Key('count_plus')));
    await t.tap(find.byKey(const Key('count_plus5')));
    await t.pump();
    expect(find.text('7'), findsOneWidget);
    await t.tap(find.byKey(const Key('count_save')));
    await t.pumpAndSettle();
    expect(find.text('1 waiting to be sent'), findsOneWidget);                // kept on the phone
    expect(api.received, isEmpty);
    api.online = true;
    await t.tap(find.text('Send now'));
    await t.pumpAndSettle();
    expect(find.text('All counts sent'), findsOneWidget);
    final c = api.received.values.single;
    expect((c.segId, c.count, c.time), (3, 7, '10:15'));
  });

  testWidgets('safari sightings: report a leopard, see the jeep rule and the circuits that avoid it, end it', (t) async {
    t.view.physicalSize = const Size(1179, 2556);
    t.view.devicePixelRatio = 3;
    addTearDown(t.view.reset);
    final api = _SightingApi();
    await t.pumpWidget(wrap(Scaffold(body: SightingsTab(now: () => DateTime(2026, 11, 10, 7, 10))), api));
    await t.pumpAndSettle();
    expect(find.text('No active sightings'), findsOneWidget);
    await t.tap(find.byKey(const Key('sighting_report')));
    await t.pumpAndSettle();
    expect(api.reported, (12, '07:10', 'leopard'));
    expect(find.text('Leopard at Heenwewa Tank · since 07:10'), findsOneWidget);
    expect(find.text('About 14 jeeps near · at most 10 stopped, 10 min each'), findsOneWidget);
    expect(find.textContaining('send new jeeps on Southern tanks'), findsOneWidget);
    await t.tap(find.text('Animal gone'));
    await t.pumpAndSettle();
    expect(find.text('No active sightings'), findsOneWidget);
  });

  testWidgets('gate advice: hold entries to a trail or send groups elsewhere; all clear when quiet', (t) async {
    final busy = GateAdvice.fromJson({
      'time': '08:00', 'inside': 480, 'basis': 'From the 40 groups through the gate so far',
      'over': [
        {'seg_id': 25, 'name': "World's End", 'trail': 'main', 'at': '09:30', 'people': 61.0, 'capacity': 30.0}
      ],
      'advice': [
        {'trail': 'main', 'trail_name': "World's End loop", 'hold_min': 60, 'send_to': ['Kirigalpotta'],
          'text': "Hold new entries to the World's End loop for 60 min, or send the next groups to Kirigalpotta"}
      ],
    });
    await t.pumpWidget(MaterialApp(home: Scaffold(body: GateAdviceCard(busy))));
    expect(find.text('Next 2 hours: act at the gate'), findsOneWidget);
    expect(find.textContaining('Hold new entries'), findsOneWidget);
    expect(find.textContaining("World's End: about 61 people at 09:30"), findsOneWidget);
    final quiet = GateAdvice.fromJson({'time': '08:00', 'inside': 20, 'basis': 'b', 'over': [], 'advice': []});
    await t.pumpWidget(MaterialApp(home: Scaffold(body: GateAdviceCard(quiet))));
    expect(find.text('Next 2 hours: keep the gate open'), findsOneWidget);
  });

  testWidgets('rest of today: updated with the spot counts, sections now over capacity, what changed', (t) async {
    final u = TodayUpdate.fromJson({
      'from_hour': 11, 'counts_used': 3, 'basis': 'Updated from 3 ranger counts at the counted places',
      'biggest_changes': [
        {'seg_id': 25, 'name': "World's End", 'change': 14.2, 'over_hours': [11, 12]},
        {'seg_id': 3, 'name': 'Section 3', 'change': 0.2, 'over_hours': []},
      ],
      'over_capacity': [
        {'seg_id': 25, 'name': "World's End", 'over_hours': [11, 12, 14], 'capacity_at_once': 30.0}
      ],
    });
    await t.pumpWidget(MaterialApp(home: Scaffold(body: TodayUpdateCard(u))));
    expect(find.textContaining('updated with 3 counts'), findsOneWidget);
    expect(find.text("World's End: over capacity 11–13 h, 14–15 h"), findsOneWidget);
    expect(find.text("World's End: busiest hour +14 people"), findsOneWidget);
    expect(find.textContaining('Section 3'), findsNothing);                 // tiny changes are not listed
  });

  testWidgets('officer forecast check: counts next to the forecast, error and bottlenecks called', (t) async {
    t.view.physicalSize = const Size(1179, 2556);
    t.view.devicePixelRatio = 3;
    addTearDown(t.view.reset);
    await t.pumpWidget(wrap(const Scaffold(body: ForecastCheckTab()), _CountApi()));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('check_summary')), findsOneWidget);
    expect(find.text('6.5'), findsOneWidget);
    expect(find.text('50 %'), findsOneWidget);
    expect(find.textContaining('counted 40 · forecast 44'), findsOneWidget);
  });

  testWidgets('officer daily quota: forecast vs weather vs fixed, why, and choosing a rule or a number', (t) async {
    t.view.physicalSize = const Size(1179, 2556);
    t.view.devicePixelRatio = 3;
    addTearDown(t.view.reset);
    final api = _QuotaApi();
    await t.pumpWidget(wrap(const Scaffold(body: CapacityTab()), api));
    await t.pumpAndSettle();
    expect(find.byKey(const Key('quota_main')), findsOneWidget);
    expect(find.text('175'), findsWidgets);                                   // forecast-driven quota applied
    expect(find.text('351'), findsOneWidget);                                 // weather only
    expect(find.text('400'), findsOneWidget);                                 // the same all year
    expect(find.textContaining('expected over capacity 10-12 h'), findsOneWidget);
    expect(find.textContaining('No counters inside the trail'), findsOneWidget);   // A6: the basis
    expect(find.textContaining('10–12 h'), findsOneWidget);
    await t.tap(find.byKey(const Key('rule_main_classic')));
    await t.pumpAndSettle();
    expect(api.rule, 'classic');
    await t.tap(find.byKey(const Key('rule_main_manual')));
    await t.pumpAndSettle();
    await t.enterText(find.byKey(const Key('quota_number')), '120');
    await t.tap(find.text('Use'));
    await t.pumpAndSettle();
    expect((api.rule, api.manual), ('manual', 120));
    expect(find.text('120'), findsWidgets);
  });

  testWidgets('officer records: daily visitors past / today / future, filter by trail and dates, copy as CSV', (t) async {
    t.view.physicalSize = const Size(1179, 2556);
    t.view.devicePixelRatio = 3;
    addTearDown(t.view.reset);
    String? copied;
    t.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
      if (call.method == 'Clipboard.setData') copied = (call.arguments as Map)['text'] as String;
      return null;
    });
    final api = _RecordsApi();
    await t.pumpWidget(wrap(const Scaffold(body: RecordsTab()), api));
    await t.pumpAndSettle();
    // default: past 30 days + next week, all trails
    expect(api.start, today.subtract(const Duration(days: 30)));
    expect(api.end, today.add(const Duration(days: 6)));
    expect(api.trailAsked, isNull);
    expect(find.text('Past'), findsOneWidget);
    expect(find.text('Today'), findsOneWidget);
    expect(find.text('Expected'), findsOneWidget);
    expect(find.byKey(const Key('records_summary')), findsOneWidget);
    expect(find.textContaining('people counted at the gate'), findsOneWidget);
    // all trails added up per day: 300 + 20 + 2 x day of month
    final todayTotal = 320 + 2 * today.day;
    expect(find.text('$todayTotal'), findsWidgets);
    // date filter
    await t.tap(find.text('Today + 6 days'));
    await t.pumpAndSettle();
    expect(api.start, today);
    expect(api.end, today.add(const Duration(days: 6)));
    expect(find.textContaining('~'), findsWidgets);                         // future days show the forecast range
    // trail filter
    await t.tap(find.byKey(const Key('records_trail')));
    await t.pumpAndSettle();
    await t.tap(find.text('Kirigalpotta').last);
    await t.pumpAndSettle();
    expect(api.trailAsked, 'kirigalpotta');
    // keep the records: CSV with one line per day and trail
    await t.tap(find.byKey(const Key('records_csv')));
    await t.pump();
    expect(copied, startsWith(RecordRow.csvHeader));
    expect(copied!.split('\n').length, 1 + 7);                               // header + 7 days, one trail
    expect(copied, contains('Kirigalpotta'));
    t.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null);
  });

  test('offline-first: a screen seen once opens again with no connection, from the stored copy', () async {
    var online = true;
    final client = MockClient((r) async {
      if (!online) throw const SocketException('airplane mode');
      if (r.url.path.endsWith('/status')) {
        return http.Response(jsonEncode({'site': 'Horton Plains National Park', 'today': '2026-10-20'}), 200);
      }
      return http.Response('{"detail": "not here"}', 404);
    });
    final api = C4Api(baseUrl: 'http://park', client: client, park: 'horton_plains');
    expect((await api.status()).site, 'Horton Plains National Park');
    expect(api.offline.value, isNull);
    online = false;                                                    // airplane mode
    final s = await api.status();
    expect(s.site, 'Horton Plains National Park');                     // the stored copy
    expect(api.offline.value, isNotNull);                              // ... and the app knows it is offline
    await expectLater(api.trails(), throwsA(isA<ApiException>()));      // never seen: still a clear error
    await expectLater(api.book(DateTime(2026, 10, 21), 'main', '07:00', 2), throwsA(isA<ApiException>())); // no offline booking
    online = true;
    await api.status();
    expect(api.offline.value, isNull);                                 // back online
  });

  testWidgets('app home lists the modules', (t) async {
    await t.pumpWidget(const HikingAssistantApp());
    expect(find.text('Plan your visit'), findsOneWidget);
    expect(find.textContaining('coming soon'), findsNWidgets(3));
  });
}

/// Safari park: one section; a sighting appears when reported and goes when ended.
class _SightingApi extends FakeApi {
  (int, String, String)? reported;
  bool active = false;

  Map<String, dynamic> get _json => {
        'time': '07:10', 'note': 'estimated from the gate entries',
        'sightings': [
          if (active)
            {'id': 1, 'seg_id': 12, 'place': 'Heenwewa Tank', 'since': '07:10', 'species': 'leopard', 'jeeps_near': 14,
              'cap_jeeps': 10, 'rotation_min': 10, 'circuits_avoiding': ['Southern tanks'],
              'advice': 'Leopard at Heenwewa Tank since 07:10: at most 10 jeeps stopped at once, 10 min each; others '
                  'move on. About 14 jeeps near it: send new jeeps on Southern tanks.'}
        ],
      };

  @override
  Future<List<SegmentInfo>> segments() async =>
      [SegmentInfo(segId: 12, name: 'Heenwewa Tank', trail: 'patanangala', trailName: 'Patanangala and Buthawa')];

  @override
  Future<SightingStatus> sightings(DateTime d, {String? at}) async => SightingStatus.fromJson(_json);

  @override
  Future<SightingStatus> reportSighting(DateTime d, int segId, String time, String species, String clientId) async {
    reported = (segId, time, species);
    active = true;
    return SightingStatus.fromJson(_json);
  }

  @override
  Future<void> endSighting(int id, String time) async => active = false;
}

/// An officer at Yala: three safari circuits; remembers which trail a condition was reported for.
class _YalaOfficerApi extends FakeApi {
  _YalaOfficerApi() : super(role: 'officer');

  String? conditionTrail;

  @override
  Future<List<TrailInfo>> trails() async => [
        TrailInfo(id: 'patanangala', name: 'Patanangala and Buthawa', lengthKm: 22.7, about: ''),
        TrailInfo(id: 'southern', name: 'Southern tanks (Bembewa, Maliththa)', lengthKm: 7.2, about: ''),
        TrailInfo(id: 'katagamuwa', name: 'Katagamuwa circuit', lengthKm: 11.8, about: ''),
      ];

  @override
  Future<List<Map<String, dynamic>>> setCondition(String trail, DateTime from, DateTime to, String level, String note) async {
    conditionTrail = trail;
    return [];
  }
}
