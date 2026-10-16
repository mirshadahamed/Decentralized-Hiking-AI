import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../data/api_client.dart';
import '../data/models.dart';
import 'c4_i18n.dart';
import 'c4_theme.dart';

/// Gives every Component 4 screen the same API client and language (and lets tests inject a fake API).
/// Screens that use [tr] rebuild when the language changes.
class C4Scope extends InheritedNotifier<C4Lang> {
  const C4Scope({super.key, required this.api, C4Lang? lang, required super.child}) : super(notifier: lang);

  final C4Api api;

  static C4Scope _of(BuildContext context) => context.dependOnInheritedWidgetOfExactType<C4Scope>()!;

  static C4Api of(BuildContext context) => _of(context).api;

  static C4Lang? langOf(BuildContext context) => _of(context).notifier;
}

final _english = C4Lang();

/// Translated text (English when no language is set, e.g. in tests).
String tr(BuildContext context, String key, [Map<String, Object> args = const {}]) =>
    (C4Scope.langOf(context) ?? _english).t(key, args);

String crowdLabel(BuildContext context, int level) => tr(context, 'level_${level.clamp(1, 5)}');

/// Component 4 look (C4Theme) and scope around a page.
class C4Frame extends StatelessWidget {
  const C4Frame({super.key, required this.api, this.lang, required this.child});

  final C4Api api;
  final C4Lang? lang;
  final Widget child;

  @override
  Widget build(BuildContext context) => Theme(
        data: C4Theme.of(Theme.of(context).brightness),
        child: C4Scope(api: api, lang: lang, child: child),
      );
}

/// A page route that keeps the Component 4 API, language and theme on the new screen
/// (routes are built by the app's Navigator, outside the scope of the screen that pushed them).
MaterialPageRoute<T> c4Route<T>(BuildContext context, Widget page) {
  final api = C4Scope.of(context), lang = C4Scope.langOf(context);
  return MaterialPageRoute<T>(builder: (_) => C4Frame(api: api, lang: lang, child: page));
}

/// Same traffic-light colours everywhere (outlook, slots, live status).
class C4Colors {
  static const levels = [Color(0xFF2E8B57), Color(0xFF8BBF5A), Color(0xFFE0C341), Color(0xFFE08A2C), Color(0xFFC0392B)];
  static const green = Color(0xFF2E8B57), amber = Color(0xFFE0A100), red = Color(0xFFC0392B);

  static Color level(int crowdLevel) => levels[(crowdLevel - 1).clamp(0, 4)];

  static Color light(String light) => switch (light) { 'red' => red, 'amber' => amber, _ => green };

  static Color onColor(Color c) => c.computeLuminance() > 0.45 ? Colors.black87 : Colors.white;
}

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
      label: Text(crowdLabel(context, level), style: TextStyle(color: C4Colors.onColor(c), fontWeight: FontWeight.w600)),
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
            FilledButton.tonal(onPressed: onRetry, child: Text(tr(context, 'try_again'))),
          ]),
        ),
      );
}

// ---------- destinations ----------
IconData kindIcon(String kind) => switch (kind) {
      'pilgrimage' => Icons.temple_buddhist_outlined,
      'national_park' => Icons.forest_outlined,
      'waterfall' => Icons.water_outlined,
      _ => Icons.landscape_outlined,
    };

/// "national_park" -> translated label, or "National park" for kinds without a translation yet.
String kindLabel(BuildContext context, String kind) {
  final t = tr(context, 'kind_$kind');
  if (t != 'kind_$kind') return t;
  final s = kind.replaceAll('_', ' ');
  return s.isEmpty ? s : s[0].toUpperCase() + s.substring(1);
}

/// Coloured header of a destination (card and overview).
class DestinationBanner extends StatelessWidget {
  const DestinationBanner({super.key, required this.name, required this.kind, this.region = '', this.accent, this.height = 120});

  final String name, kind, region;
  final int? accent;
  final double height;

  @override
  Widget build(BuildContext context) {
    final base = accent != null ? Color(accent!) : Theme.of(context).colorScheme.primary;
    final dark = Color.lerp(base, Colors.black, 0.35)!;
    final text = Theme.of(context).textTheme;
    return Container(
      height: height,
      decoration: BoxDecoration(gradient: LinearGradient(colors: [base, dark], begin: Alignment.topLeft, end: Alignment.bottomRight)),
      child: Stack(children: [
        Positioned(right: -10, bottom: -18, child: Icon(kindIcon(kind), size: height * 0.95, color: Colors.white.withValues(alpha: 0.13))),
        Padding(
          padding: const EdgeInsets.all(16),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisAlignment: MainAxisAlignment.end, children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
              decoration: BoxDecoration(color: Colors.white.withValues(alpha: 0.2), borderRadius: BorderRadius.circular(12)),
              child: Row(mainAxisSize: MainAxisSize.min, children: [
                Icon(kindIcon(kind), size: 14, color: Colors.white),
                const SizedBox(width: 4),
                Text(kindLabel(context, kind), style: text.labelSmall?.copyWith(color: Colors.white)),
              ]),
            ),
            const SizedBox(height: 6),
            Text(name, style: text.titleLarge?.copyWith(color: Colors.white, fontWeight: FontWeight.w700), maxLines: 2, overflow: TextOverflow.ellipsis),
            if (region.isNotEmpty)
              Text(region, style: text.bodySmall?.copyWith(color: Colors.white.withValues(alpha: 0.85)), maxLines: 1, overflow: TextOverflow.ellipsis),
          ]),
        ),
      ]),
    );
  }
}

/// Coloured crowd level for each of the next days, with the weekday under it.
class WeekStrip extends StatelessWidget {
  const WeekStrip({super.key, required this.days});

  final List<OutlookDay> days;

  @override
  Widget build(BuildContext context) => Semantics(
        label: days.map((d) => '${shortDate(d.date)} ${crowdLabel(context, d.crowdLevel)}').join(', '),
        child: Row(children: [
          for (final d in days)
            Expanded(
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 2),
                child: Column(children: [
                  Container(height: 10, decoration: BoxDecoration(color: C4Colors.level(d.crowdLevel), borderRadius: BorderRadius.circular(5))),
                  const SizedBox(height: 2),
                  Text(DateFormat('E').format(d.date).substring(0, 2), style: Theme.of(context).textTheme.labelSmall),
                ]),
              ),
            ),
        ]),
      );
}

/// Day with the fewest expected visitors.
OutlookDay quietestOf(List<OutlookDay> days) => days.reduce((a, b) => b.p50 < a.p50 ? b : a);

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
