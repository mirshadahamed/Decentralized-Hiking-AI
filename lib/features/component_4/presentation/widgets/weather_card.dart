import 'package:flutter/material.dart';

import '../../models/models.dart';
import '../theme/c4_theme.dart';

/// The weather of the chosen date (PP1 panel): the day at a glance, rain and temperature through the open hours,
/// the best dry hours to walk, what kind of weather it is, and what it does to the crowd and the safe limit.
class WeatherCard extends StatelessWidget {
  const WeatherCard({super.key, required this.weather, this.compact = false});

  final DayWeather weather;
  final bool compact; // one line (week views)

  static IconData icon(DayWeather w) => const [Icons.wb_sunny_outlined, Icons.cloud_outlined, Icons.grain, Icons.thunderstorm_outlined][w.wetness];

  static String _h(int h) => '${h.toString().padLeft(2, '0')}:00';

  @override
  Widget build(BuildContext context) {
    final w = weather;
    final text = Theme.of(context).textTheme;
    final headline = '${w.tempMin.round()}–${w.tempMax.round()} °C · '
        '${w.basis == 'typical' && w.typicalLow != null ? 'usually ${w.typicalLow!.toStringAsFixed(0)}–${w.typicalHigh!.toStringAsFixed(0)} mm' : '${w.rainMm.toStringAsFixed(1)} mm'} rain'
        ' · ${(w.rainShare * 100).round()} % of hours wet';
    if (compact) {
      return Row(key: const Key('weather_compact'), children: [
        Icon(icon(w), size: 18),
        const SizedBox(width: C4Space.s),
        Expanded(child: Text(headline, style: text.bodySmall)),
        _BasisChip(w),
      ]);
    }
    final maxRain = [2.0, for (final h in w.hours) h.rainMm].reduce((a, b) => a > b ? a : b);
    return Card(
      key: const Key('weather_card'),
      child: Padding(
        padding: const EdgeInsets.all(C4Space.m),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Icon(icon(w), size: 28),
            const SizedBox(width: C4Space.s),
            Expanded(child: Text('Weather', style: text.titleMedium)),
            _BasisChip(w),
          ]),
          const SizedBox(height: C4Space.xs),
          Text(headline, style: text.bodyMedium?.copyWith(fontWeight: FontWeight.w600)),
          if (w.chanceWetDay != null)
            Text('In past years ${(w.chanceWetDay! * 100).round()} % of these dates had rain during opening hours.',
                style: text.bodySmall),
          const SizedBox(height: C4Space.s),
          SizedBox(
            height: 64,
            child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
              for (final h in w.hours)
                Expanded(
                  child: Tooltip(
                    message: '${_h(h.hour)}: ${h.rainMm.toStringAsFixed(1)} mm, ${h.tempC.round()} °C',
                    child: Column(mainAxisAlignment: MainAxisAlignment.end, children: [
                      Text('${h.tempC.round()}°', style: const TextStyle(fontSize: 9)),
                      Container(
                        margin: const EdgeInsets.symmetric(horizontal: 1),
                        height: 4 + 30 * (h.rainMm / maxRain).clamp(0.0, 1.0),
                        color: h.rainMm >= 0.5 ? const Color(0xFF3B6FB6) : const Color(0xFFCFD8DC),
                      ),
                      Text('${h.hour}', style: const TextStyle(fontSize: 9)),
                    ]),
                  ),
                ),
            ]),
          ),
          const SizedBox(height: C4Space.s),
          if (w.dryWindows.isNotEmpty)
            Text(
                'Best to walk (${w.dryBasis}): ${w.dryWindows.take(2).map((d) => '${_h(d.$1)}–${_h(d.$2)}').join(', ')}',
                key: const Key('weather_dry'),
                style: text.bodyMedium),
          if (w.effect.isNotEmpty) ...[
            const SizedBox(height: C4Space.xs),
            Text(w.effect, key: const Key('weather_effect'), style: text.bodySmall),
          ],
        ]),
      ),
    );
  }
}

class _BasisChip extends StatelessWidget {
  const _BasisChip(this.w);

  final DayWeather w;

  @override
  Widget build(BuildContext context) => Chip(
        visualDensity: VisualDensity.compact,
        label: Text(switch (w.basis) { 'observed' => 'measured', 'forecast' => 'forecast', _ => 'typical' },
            style: const TextStyle(fontSize: 11)),
      );
}
