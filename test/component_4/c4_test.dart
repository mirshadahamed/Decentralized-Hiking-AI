// Widget tests for Component 4 with a fake API (no server needed).
import 'package:decentralized_hiking_ai/app/app.dart';
import 'package:decentralized_hiking_ai/features/component_4/component4_home.dart';
import 'package:decentralized_hiking_ai/features/component_4/data/api_client.dart';
import 'package:decentralized_hiking_ai/features/component_4/data/models.dart';
import 'package:decentralized_hiking_ai/features/component_4/screens/visitor/day_screen.dart';
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

class FakeApi extends C4Api {
  FakeApi({this.full = false, this.loginOk = true}) : super(baseUrl: 'http://fake');

  final bool full, loginOk;
  int bookings = 0;

  @override
  Future<ServerStatus> status() async => ServerStatus(today: today, refreshedAt: '', note: '');

  @override
  Future<Outlook> outlook() async => Outlook(
        issueDate: today,
        days: [OutlookDay.fromJson(outlookDay(today.add(const Duration(days: 1)), 2)), OutlookDay.fromJson(outlookDay(visit, 4))],
        trailNames: {'main': "World's End loop"},
        disclaimer: 'Estimated.',
      );

  @override
  Future<List<TrailInfo>> trails() async => [
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

  testWidgets('app home lists the modules', (t) async {
    await t.pumpWidget(const HikingAssistantApp());
    expect(find.text('Plan your visit'), findsOneWidget);
    expect(find.textContaining('coming soon'), findsNWidgets(3));
  });
}
