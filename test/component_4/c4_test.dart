// Widget tests for Component 4 with a fake API (no server needed).
import 'package:decentralized_hiking_ai/app/app.dart';
import 'package:decentralized_hiking_ai/features/component_4/component4_home.dart';
import 'package:decentralized_hiking_ai/features/component_4/data/api_client.dart';
import 'package:decentralized_hiking_ai/features/component_4/data/models.dart';
import 'package:decentralized_hiking_ai/features/component_4/screens/staff/halfway_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/screens/visitor/day_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/screens/visitor/map_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/screens/visitor/start_times_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/ui/c4_i18n.dart';
import 'package:decentralized_hiking_ai/features/component_4/ui/c4_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
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
  'summit': {'peak_queue_people': 2140, 'peak_wait_min': 86, 'peak_at': '05:15'},
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
        {'route': 'nallathanniya', 'name': 'Nallathanniya (Hatton)', 'release_per_10_min': hold ? 194 : null, 'walk_to_summit_min': 143, 'counted_today': hold ? 900 : 0},
        {'route': 'palabaddala', 'name': 'Palabaddala (Ratnapura)', 'release_per_10_min': hold ? 30 : null, 'walk_to_summit_min': 142, 'counted_today': 0},
      ],
    };

class FakeApi extends C4Api {
  FakeApi({this.full = false, this.loginOk = true, this.withParks = false}) : super(baseUrl: 'http://fake');

  final bool full, loginOk, withParks;
  int bookings = 0, recorded = 0;

  bool get _ap => park == 'adams_peak';

  @override
  Future<List<ParkInfo>?> parks() async => withParks
      ? [
          ParkInfo(id: 'horton_plains', name: 'Horton Plains', bookingMode: 'required', trails: {'main': "World's End loop"}),
          ParkInfo(id: 'adams_peak', name: "Adam's Peak (Sri Pada)", bookingMode: 'advisory', trails: {'nallathanniya': 'Nallathanniya (Hatton)'}),
        ]
      : null;

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
  Future<Outlook> outlook() async => Outlook(
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
    return session = StaffSession(token: 't', username: username, role: 'ranger');
  }

  @override
  Future<List<WalkInSlot>> walkIns(DateTime d) async => [WalkInSlot(slot: '07:00', trail: 'main', left: 5)];

  @override
  Future<List<LiveSegment>> live(DateTime d, {String? at}) async => [];
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

  testWidgets('with several parks the visitor picks one; Adam\'s Peak shows start times, not tickets', (t) async {
    await t.pumpWidget(MaterialApp(home: Component4Home(api: FakeApi(withParks: true), lang: C4Lang())));
    await t.pumpAndSettle();
    expect(find.text('Choose a place'), findsOneWidget);
    expect(find.text('No tickets: recommended start times'), findsOneWidget);
    await t.tap(find.text("Adam's Peak (Sri Pada)"));
    await t.pumpAndSettle();
    expect(find.text('When will you climb?'), findsOneWidget);
    expect(find.text('Start times'), findsOneWidget);
    expect(find.text('My tickets'), findsNothing);
    expect(find.byIcon(Icons.swap_horiz), findsOneWidget); // change park
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
    await t.scrollUntilVisible(find.text('Palabaddala (Ratnapura)'), -200);
    await t.tap(find.text('Palabaddala (Ratnapura)'));
    await t.pumpAndSettle();
    expect(find.text('05:30'), findsOneWidget);
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
  });

  testWidgets('map shows the routes and the legend', (t) async {
    final api = FakeApi()..usePark('adams_peak');
    await t.pumpWidget(wrap(const Scaffold(body: MapScreen(showTiles: false)), api));
    await t.pumpAndSettle();
    expect(find.textContaining('Nallathanniya (Hatton) · 4.5 km'), findsOneWidget);
    expect(find.byIcon(Icons.flag), findsOneWidget);           // summit
    expect(find.byIcon(Icons.directions_walk), findsOneWidget); // trail head
  });

  testWidgets('app home lists the modules', (t) async {
    await t.pumpWidget(const HikingAssistantApp());
    expect(find.text('Plan your visit'), findsOneWidget);
    expect(find.textContaining('coming soon'), findsNWidgets(3));
  });
}
