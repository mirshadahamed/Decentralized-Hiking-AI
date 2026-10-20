// Phone-size screenshots of the Component 4 screens for slides and reports, rendered from saved API responses
// (no server needed). Skipped in normal test runs. Make the fixtures and the images with:
//   flutter test test/component_4/screenshots_test.dart --update-goldens
//     --dart-define=C4_FIXTURES=<folder with parks.json and one folder per park>
//     --dart-define=C4_SHOTS=<output folder>
import 'dart:convert';
import 'dart:io';

import 'package:decentralized_hiking_ai/features/component_4/presentation/component4_home.dart';
import 'package:decentralized_hiking_ai/features/component_4/data/api_client.dart';
import 'package:decentralized_hiking_ai/features/component_4/models/models.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/screens/staff/advisory_officer_home.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/screens/staff/halfway_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/screens/visitor/day_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/screens/visitor/start_times_screen.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/l10n/c4_i18n.dart';
import 'package:decentralized_hiking_ai/features/component_4/presentation/widgets/c4_ui.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

const fixtures = String.fromEnvironment('C4_FIXTURES');
const shots = String.fromEnvironment('C4_SHOTS');

class FixtureApi extends C4Api {
  FixtureApi({this.multi = true}) : super(baseUrl: 'http://fixture');

  final bool multi;

  String get _p => park ?? 'horton_plains';

  dynamic _j(String park, String name) => jsonDecode(File('$fixtures/$park/$name.json').readAsStringSync());

  @override
  Future<List<ParkInfo>?> parks() async => multi
      ? (jsonDecode(File('$fixtures/parks.json').readAsStringSync()) as List)
          .map((p) => ParkInfo.fromJson(p as Map<String, dynamic>))
          .toList()
      : null;

  @override
  Future<ServerStatus> status() async => ServerStatus.fromJson(_j(_p, 'status'));

  @override
  Future<ParkInfo> destination() async => ParkInfo.fromJson(_j(_p, 'destination'));

  @override
  Future<Outlook> outlook({String? forPark}) async => Outlook.fromJson(_j(forPark ?? _p, 'outlook'));

  @override
  Future<List<TrailInfo>> trails() async =>
      (_j(_p, 'trails') as List).map((t) => TrailInfo.fromJson(t as Map<String, dynamic>)).toList();

  @override
  Future<List<MapSegment>> geometry() async => MapSegment.fromGeoJson(_j(_p, 'geometry'));

  @override
  Future<DayPlan> plan(DateTime d) async => DayPlan.fromPlanJson(_j(_p, 'plan'));

  @override
  Future<DaySlots> slots(DateTime d) async => DaySlots.fromJson(_j(_p, 'slots'));

  @override
  Future<StartAdvice> advisory(DateTime d) async => StartAdvice.fromJson(_j(_p, 'advisory'));

  @override
  Future<CheckpointStatus> checkpoints(DateTime d, {String? at}) async => CheckpointStatus.fromJson(_j(_p, 'checkpoints'));

  @override
  Future<List<SeasonNight>> season() async =>
      ((_j(_p, 'season') as Map)['days'] as List).map((d) => SeasonNight.fromJson(d as Map<String, dynamic>)).toList();
}

Future<void> _loadFonts() async {
  final root = Platform.environment['FLUTTER_ROOT'] ?? r'C:\Users\Jhonny\dev\flutter';
  final dir = '$root/bin/cache/artifacts/material_fonts';
  Future<ByteData> f(String n) async => ByteData.view(File('$dir/$n').readAsBytesSync().buffer);
  final roboto = FontLoader('Roboto');
  for (final n in ['roboto-regular.ttf', 'roboto-medium.ttf', 'roboto-bold.ttf', 'roboto-light.ttf']) {
    roboto.addFont(f(n));
  }
  await roboto.load();
  await (FontLoader('MaterialIcons')..addFont(f('materialicons-regular.otf'))).load();
}

final _root = GlobalKey();

Widget _app(Widget home) => RepaintBoundary(key: _root, child: MaterialApp(debugShowCheckedModeBanner: false, home: home));

Widget _scoped(Widget page, C4Api api) =>
    _app(Builder(builder: (context) => C4Frame(api: api, lang: C4Lang(), child: page)));

Future<void> _shot(WidgetTester t, String name) async {
  await t.pumpAndSettle();
  await expectLater(find.byKey(_root), matchesGoldenFile(Uri.file('$shots/$name.png')));
}

void main() {
  final skip = fixtures.isEmpty || shots.isEmpty;

  setUpAll(() async {
    if (!skip) await _loadFonts();
  });

  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  Future<void> phone(WidgetTester t) async {
    t.view.physicalSize = const Size(1179, 2556); // 393 x 852 logical, 3x
    t.view.devicePixelRatio = 3;
    addTearDown(t.view.reset);
  }

  testWidgets('01 destinations and 02 Adam\'s Peak overview', (t) async {
    await phone(t);
    await t.pumpWidget(_app(Component4Home(api: FixtureApi(), lang: C4Lang())));
    await _shot(t, '01_destinations');
    await t.tap(find.text("Adam's Peak (Sri Pada)"));
    await _shot(t, '02_overview_adams_peak');
  }, skip: skip);

  testWidgets('03 Horton calendar', (t) async {
    await phone(t);
    await t.pumpWidget(_app(Component4Home(api: FixtureApi(), lang: C4Lang())));
    await t.pumpAndSettle();
    await t.tap(find.text('Horton Plains National Park'));
    await t.pumpAndSettle();
    await t.tap(find.text('Plan & book'));
    await _shot(t, '03_calendar_horton');
  }, skip: skip);

  testWidgets('04 Horton day and slots', (t) async {
    await phone(t);
    await t.pumpWidget(_scoped(DayScreen(day: DateTime(2026, 11, 24)), FixtureApi()..usePark('horton_plains')));
    await _shot(t, '04_day_horton');
  }, skip: skip);

  testWidgets('05 Adam\'s Peak start times', (t) async {
    await phone(t);
    final api = FixtureApi()..usePark('adams_peak');
    final o = await api.outlook();
    final night = o.days.firstWhere((d) => d.date == DateTime(2026, 12, 25));
    await t.pumpWidget(_scoped(StartTimesScreen(day: night.date, outlookDay: night), api));
    await _shot(t, '05_start_times');
  }, skip: skip);

  testWidgets('06 halfway check (ranger)', (t) async {
    await phone(t);
    final api = FixtureApi()..usePark('adams_peak');
    api.session = StaffSession(token: 't', username: 'ranger1', role: 'ranger');
    await t.pumpWidget(_scoped(HalfwayScreen(demo: DateTime(2026, 12, 25, 2, 15)), api));
    await _shot(t, '06_halfway_hold');
  }, skip: skip);

  testWidgets('07 officer season and 08 night plan', (t) async {
    await phone(t);
    final api = FixtureApi()..usePark('adams_peak');
    api.session = StaffSession(token: 't', username: 'officer1', role: 'officer');
    await t.pumpWidget(_scoped(const AdvisoryOfficerHome(), api));
    await _shot(t, '07_officer_tonight');
    await t.tap(find.text('Season'));
    await t.pumpAndSettle();
    await t.tap(find.byType(SwitchListTile));
    await _shot(t, '08_officer_season');
    final nights = await api.season();
    final n = nights.firstWhere((x) => x.date == DateTime(2026, 12, 25));
    await t.pumpWidget(_scoped(NightPlanScreen(day: n.date, night: n), api));
    await _shot(t, '09_night_plan');
  }, skip: skip);
}
