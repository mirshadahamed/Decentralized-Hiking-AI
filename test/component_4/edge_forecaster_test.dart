// Parity: the Dart on-device forecast must give the same numbers as PyTorch for the same pack.
// Fixture: research/component_4 -> python -m src.edge.pack --fixture ../../test/component_4/fixtures/edge_pack.json
import 'dart:convert';
import 'dart:io';

import 'package:decentralized_hiking_ai/features/component_4/domain/bottleneck.dart';
import 'package:decentralized_hiking_ai/features/component_4/domain/edge_forecaster.dart';
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
}
