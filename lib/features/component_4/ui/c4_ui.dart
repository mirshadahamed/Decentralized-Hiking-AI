import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../data/api_client.dart';

/// Gives every Component 4 screen the same API client (and lets tests inject a fake).
class C4Scope extends InheritedWidget {
  const C4Scope({super.key, required this.api, required super.child});

  final C4Api api;

  static C4Api of(BuildContext context) => context.dependOnInheritedWidgetOfExactType<C4Scope>()!.api;

  @override
  bool updateShouldNotify(C4Scope old) => old.api != api;
}

/// A page route that keeps the Component 4 API available on the new screen
/// (routes are built by the app's Navigator, outside the scope of the screen that pushed them).
MaterialPageRoute<T> c4Route<T>(BuildContext context, Widget page) {
  final api = C4Scope.of(context);
  return MaterialPageRoute<T>(builder: (_) => C4Scope(api: api, child: page));
}

/// Same traffic-light colours everywhere (outlook, slots, live status).
class C4Colors {
  static const levels = [Color(0xFF2E8B57), Color(0xFF8BBF5A), Color(0xFFE0C341), Color(0xFFE08A2C), Color(0xFFC0392B)];
  static const green = Color(0xFF2E8B57), amber = Color(0xFFE0A100), red = Color(0xFFC0392B);

  static Color level(int crowdLevel) => levels[(crowdLevel - 1).clamp(0, 4)];

  static Color light(String light) => switch (light) { 'red' => red, 'amber' => amber, _ => green };

  static Color onColor(Color c) => c.computeLuminance() > 0.45 ? Colors.black87 : Colors.white;
}

const crowdLabels = {1: 'Very quiet', 2: 'Quiet', 3: 'Moderate', 4: 'Busy', 5: 'Very busy'};

String niceDate(DateTime d) => DateFormat('EEE d MMM yyyy').format(d);
String shortDate(DateTime d) => DateFormat('EEE d MMM').format(d);
String about(int n) => n >= 100 ? 'about ${(n / 10).round() * 10}' : 'about $n';

/// Rounded "people" figure with its basis, e.g. "about 870 people (660 – 1,100)".
String peopleRange(int p10, int p50, int p90) {
  final f = NumberFormat.decimalPattern();
  return p10 == p90 ? '${about(p50)} people' : '${about(p50)} people (${f.format(p10)} – ${f.format(p90)})';
}

class CrowdChip extends StatelessWidget {
  const CrowdChip(this.level, {super.key});

  final int level;

  @override
  Widget build(BuildContext context) {
    final c = C4Colors.level(level);
    return Chip(
      label: Text(crowdLabels[level] ?? '', style: TextStyle(color: C4Colors.onColor(c), fontWeight: FontWeight.w600)),
      backgroundColor: c,
      side: BorderSide.none,
      visualDensity: VisualDensity.compact,
    );
  }
}

class ErrorRetry extends StatelessWidget {
  const ErrorRetry({super.key, required this.error, required this.onRetry});

  final Object error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            const Icon(Icons.cloud_off, size: 48),
            const SizedBox(height: 12),
            Text('$error', textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton.tonal(onPressed: onRetry, child: const Text('Try again')),
          ]),
        ),
      );
}

/// Small grey line that says what an estimate is based on (every estimate carries its basis).
class BasisNote extends StatelessWidget {
  const BasisNote(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(top: 4),
        child: Row(children: [
          Icon(Icons.info_outline, size: 14, color: Theme.of(context).colorScheme.outline),
          const SizedBox(width: 4),
          Expanded(child: Text(text, style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Theme.of(context).colorScheme.outline))),
        ]),
      );
}
