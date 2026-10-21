import 'dart:math' as math;

import 'bottleneck.dart';

/// One way to do tomorrow's walk: a trail, a start hour and (for loops) the direction.
class WalkOption {
  WalkOption({
    required this.trail,
    required this.startHour,
    required this.reverse,
    required this.worst,
    required this.worstSection,
    required this.worstHour,
    required this.mean,
  });

  final String trail;
  final int startHour;
  final bool reverse; // loop walked the other way round
  final double worst; // fullest a section will be when this walker is on it (people ÷ what it holds)
  final Section? worstSection;
  final int worstHour;
  final double mean; // average fullness along the walk

  String get key => '$trail/$startHour/$reverse';
}

class WalkAdvice {
  WalkAdvice({required this.usual, required this.good, required this.pick, required this.all});

  final WalkOption? usual; // what most visitors do (busiest trail, usual direction, usual start)
  final List<WalkOption> good; // options that avoid busy sections, best first
  final WalkOption? pick; // the one suggested on THIS phone (random among the good ones, weighted by room left)
  final List<WalkOption> all;
}

/// Offline walk advice from tomorrow's forecast on the phone (alignment plan B2; hiker guidance for Module 3).
/// For every trail, start hour and direction it works out when the walker reaches each section (walking minutes
/// from the pack) and how full that section is expected to be then. Options that never meet a busy section are
/// "good". Every phone then suggests ONE good option, drawn at random with weight = room left, so that people
/// who follow the advice spread out instead of all moving to the same quiet place (the herding problem: naive
/// advice made the Adam's Peak queue 22 % worse in the simulator).
WalkAdvice adviseWalk(BottleneckDay d, {required int seed, int usualStart = 7}) {
  final options = <WalkOption>[];
  final lastStart = d.lastEntryHour?.floor() ?? (d.openHours.last - 3);
  for (final t in d.trails.keys) {
    final secs = d.sections.where((s) => s.trail == t && s.minutesFromStart != null).toList();
    if (secs.isEmpty) continue;
    final loop = secs.map((s) => s.minutesFromStart! + (s.minutesOnSection ?? 0)).reduce(math.max);
    for (final reverse in [false, if (d.reversibleTrails.contains(t)) true]) {
      for (final h in d.openHours.where((h) => h <= lastStart)) {
        var worst = 0.0, sum = 0.0, worstHour = h;
        Section? worstSec;
        for (final s in secs) {
          final on = s.minutesOnSection ?? 0;
          final at = reverse ? loop - s.minutesFromStart! - on : s.minutesFromStart!;
          final hour = ((h * 60 + at + on / 2) / 60).floor();
          final u = s.utilisation(hour);
          sum += u;
          if (u > worst) (worst, worstSec, worstHour) = (u, s, hour);
        }
        options.add(WalkOption(
          trail: t, startHour: h, reverse: reverse, worst: worst, worstSection: worstSec,
          worstHour: worstHour, mean: sum / secs.length,
        ));
      }
    }
  }
  if (options.isEmpty) return WalkAdvice(usual: null, good: const [], pick: null, all: const []);
  options.sort((a, b) => a.worst.compareTo(b.worst));
  final main = d.mainTrail ?? d.trails.keys.first;
  final usual = options.where((o) => o.trail == main && !o.reverse && o.startHour == usualStart).firstOrNull;
  var good = options.where((o) => o.worst < d.busyUtilisation).toList();
  if (good.isEmpty) good = options.where((o) => o.worst <= options.first.worst + 0.1).toList();
  // main trail first (it is the walk people came for), then by how full it gets
  good.sort((a, b) => a.trail == b.trail ? a.worst.compareTo(b.worst) : (a.trail == main ? -1 : (b.trail == main ? 1 : 0)));
  final weights = [for (final o in good) math.max(0.05, 1 - o.worst) * (o.trail == main ? 1.0 : 0.5)];
  var r = math.Random(seed).nextDouble() * weights.fold<double>(0, (a, b) => a + b);
  var pick = good.last;
  for (var i = 0; i < good.length; i++) {
    r -= weights[i];
    if (r <= 0) {
      pick = good[i];
      break;
    }
  }
  return WalkAdvice(usual: usual, good: good, pick: pick, all: options);
}
