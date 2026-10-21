// Parity: the Dart on-device forecast must give the same numbers as PyTorch for the same pack.
// Fixture: research/component_4 -> python -m src.edge.pack --fixture ../../test/component_4/fixtures/edge_pack.json
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:decentralized_hiking_ai/features/component_4/domain/bottleneck.dart';
import 'package:decentralized_hiking_ai/features/component_4/domain/edge_forecaster.dart';
import 'package:decentralized_hiking_ai/features/component_4/domain/walk_advice.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  final pack = jsonDecode(File('test/component_4/fixtures/edge_pack.json').readAsStringSync()) as Map<String, dynamic>;
  final expected = [for (final r in pack['expected_people'] as List) [for (final x in r as List) (x as num).toDouble()]];

  test('on-device ST-GNN matches PyTorch to within 0.01 people', () {
    final f = EdgeForecaster.fromPack(pack).forecast();
    expect(f.people.length, expected.length);
    expect(f.people.first.length, expected.first.length);
    var maxDiff = 0.0;
    for (var t = 0; t < expected.length; t++) {
      for (var s = 0; s < expected[t].length; s++) {
        maxDiff = (f.people[t][s] - expected[t][s]).abs() > maxDiff ? (f.people[t][s] - expected[t][s]).abs() : maxDiff;
      }
    }
    expect(maxDiff, lessThan(0.01), reason: 'largest difference $maxDiff people');
  });

  test('it is fast enough for a phone (well under the 2 s target)', () {
    final m = EdgeForecaster.fromPack(pack);
    m.forecast(); // warm-up
    final f = m.forecast();
    expect(f.millis, lessThan(2000));
    final (hour, people) = f.peakOf(0);
    expect(hour, inInclusiveRange(0, 23));
    expect(people, greaterThanOrEqualTo(0));
  });

  test('rejects an unknown pack format', () {
    expect(() => EdgeForecaster.fromPack({...pack, 'schema': 'other'}), throwsFormatException);
  });

  test('bottleneck day: every section has its line, forecast and Cifuentes capacity from the pack', () {
    final f = EdgeForecaster.fromPack(pack).forecast();
    final d = BottleneckDay.fromPack(pack, f, offline: true);
    final map = pack['map'] as Map<String, dynamic>;
    expect(d.sections.length, (map['segments'] as List).length);
    expect(d.sections.every((s) => s.lines.isNotEmpty && s.capacityAtOnce > 0), isTrue);
    expect(d.sections.every((s) => s.ecc <= s.rcc && s.rcc <= s.pcc), isTrue); // the cascade only removes
    final s = d.sections[5];
    expect(s.peopleAt(9), closeTo(expected[9][s.id], 0.01)); // the phone's own forecast, per section
    expect(d.openHours, contains(d.worstHour));
    expect(d.recommendedQuota, map['recommended_daily_quota']);
    // A5: chance of really being over capacity grows with how full the forecast is
    expect(d.calibration, isNotNull);
    final ranked = d.rankedAt(d.worstHour);
    final pFull = d.chanceOver(ranked.first, d.worstHour)!, pEmpty = d.chanceOver(ranked.last, d.worstHour)!;
    expect(pFull, greaterThanOrEqualTo(pEmpty));
    expect(pEmpty, lessThan(0.05));
    // crowding levels follow forecast people / people the section holds at once
    for (final x in d.sections) {
      final u = x.utilisation(d.worstHour);
      expect(d.level(x, d.worstHour) == Crowding.over, u > 1);
    }
    expect(d.rankedAt(d.worstHour).first.utilisation(d.worstHour),
        greaterThanOrEqualTo(d.rankedAt(d.worstHour).last.utilisation(d.worstHour)));
    final main = d.trails['main']!;
    expect(d.sections.where((x) => x.trail == 'main').map((x) => x.ecc).reduce((a, b) => a < b ? a : b),
        main.recommended); // the trail's safe number is its most limiting section
    expect(d.nameOf(d.sections.firstWhere((x) => x.poi == 'worlds_end')), "World's End");
  });

  test('a week: today is also forecast on the phone (= PyTorch), later days come from the planning model', () {
    final m = EdgeForecaster.fromPack(pack);
    final days = BottleneckDay.packDays(pack);
    expect(days.length, 7);
    expect(days.take(2).map((d) => d.$2), everyElement('stgnn'));          // today + tomorrow: ST-GNN on the phone
    expect(days.skip(2).map((d) => d.$2), everyElement('planning'));
    final today = days.first.$1;
    expect(m.forecastDays, containsAll([today, pack['day']]));
    final f = m.forecast(forDay: today);
    final exp = [for (final r in pack['expected_people_today'] as List) [for (final x in r as List) (x as num).toDouble()]];
    var maxDiff = 0.0;
    for (var t = 0; t < exp.length; t++) {
      for (var s = 0; s < exp[t].length; s++) {
        maxDiff = math.max(maxDiff, (f.people[t][s] - exp[t][s]).abs());
      }
    }
    expect(maxDiff, lessThan(0.01));
    expect(() => m.forecast(forDay: '1999-01-01'), throwsArgumentError);
    // every day has its own capacity and safe numbers
    final d0 = BottleneckDay.fromPack(pack, f, date: today);
    final d5 = BottleneckDay.fromPack(pack, null, date: days[5].$1);
    expect(d0.source, 'phone');
    expect(d5.source, 'planning');
    expect(d5.sections.length, d0.sections.length);
    expect(d5.sections.every((s) => s.people.length == 24 && s.lines.isNotEmpty), isTrue);
    expect(d5.recommendedQuota, isNot(d0.recommendedQuota));                // the safe number changes with the day
  });

  test('walk advice: avoids busy sections, uses the other direction of the loop, and spreads people out', () {
    final d = BottleneckDay.fromPack(pack, EdgeForecaster.fromPack(pack).forecast());
    expect(d.sections.every((s) => s.minutesFromStart != null), isTrue);
    expect(d.reversibleTrails, contains('main'));
    final a = adviseWalk(d, seed: 1);
    expect(a.all, isNotEmpty);
    expect(a.all.any((o) => o.reverse), isTrue);                       // the loop the other way round is an option
    expect(a.good, isNotEmpty);
    for (final o in a.good) {
      expect(o.worst, lessThan(d.busyUtilisation));                    // good = never on a busy section
    }
    expect(a.good.map((o) => o.key), contains(a.pick!.key));
    if (a.usual != null) expect(a.pick!.worst, lessThanOrEqualTo(a.usual!.worst));
    // different phones (seeds) do not all get the same suggestion
    final picks = {for (var seed = 0; seed < 40; seed++) adviseWalk(d, seed: seed).pick!.key};
    if (a.good.length > 1) expect(picks.length, greaterThan(1));
    // ... and the same phone gets the same suggestion all day
    expect(adviseWalk(d, seed: 7).pick!.key, adviseWalk(d, seed: 7).pick!.key);
  });
}
