import 'package:flutter/material.dart';

import '../data/models.dart';
import '../ui/c4_theme.dart';
import '../ui/c4_ui.dart';

/// First screen when the server has several parks (gateway): pick where to go.
class ParkPicker extends StatelessWidget {
  const ParkPicker({super.key, required this.parks, required this.onPick, this.actions = const []});

  final List<ParkInfo> parks;
  final ValueChanged<String> onPick;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: Text(tr(context, 'choose_park')), actions: actions),
      body: ListView(padding: C4Space.page, children: [
        Text(tr(context, 'choose_park_sub'), style: text.bodyLarge),
        const SizedBox(height: C4Space.m),
        for (final p in parks)
          Card(
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: () => onPick(p.id),
              child: Padding(
                padding: C4Space.page,
                child: Row(children: [
                  CircleAvatar(
                    radius: 28,
                    backgroundColor: Theme.of(context).colorScheme.primaryContainer,
                    child: Icon(p.isAdvisory ? Icons.temple_buddhist_outlined : Icons.landscape_outlined, size: 30),
                  ),
                  const SizedBox(width: C4Space.l),
                  Expanded(
                    child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                      Text(p.name, style: text.titleLarge?.copyWith(fontWeight: FontWeight.w600)),
                      const SizedBox(height: C4Space.xs),
                      Row(children: [
                        Icon(p.isAdvisory ? Icons.schedule : Icons.confirmation_number_outlined, size: 16),
                        const SizedBox(width: C4Space.xs),
                        Expanded(child: Text(tr(context, p.isAdvisory ? 'start_times_advice' : 'tickets_needed'))),
                      ]),
                      const SizedBox(height: C4Space.xs),
                      Text(p.trails.values.join(' · '), style: text.bodySmall, maxLines: 2, overflow: TextOverflow.ellipsis),
                    ]),
                  ),
                  const Icon(Icons.chevron_right),
                ]),
              ),
            ),
          ),
      ]),
    );
  }
}
