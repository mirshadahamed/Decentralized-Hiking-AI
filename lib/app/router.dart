// Named routes for the whole app. Each module adds its own entry; screens inside a module
// navigate on their own (MaterialPageRoute), so this file stays small.
import 'package:flutter/material.dart';

import '../features/component_2/presentation/component_2_home.dart';
import '../features/component_4/presentation/component4_home.dart';

class AppRoutes {
  static const home = '/';
  static const component4 = '/crowds'; // Component 4: crowd forecasts, slot booking, entry control
  static const component2 = '/litter-trail-damage';

  static Map<String, WidgetBuilder> get routes => {
        component4: (_) => const Component4Home(),
        component2: (_) => const Component2Home(),
      };
}

/// Modules listed on the home screen. Route null = not available yet.
class ModuleEntry {
  const ModuleEntry(this.title, this.subtitle, this.icon, this.route);

  final String title, subtitle;
  final IconData icon;
  final String? route;
}

const modules = [
  ModuleEntry('Plan your visit', 'How busy it will be, book an entry time, staff tools', Icons.groups, AppRoutes.component4),
  ModuleEntry('Terrain & effort', 'Module 1', Icons.terrain, null),
  ModuleEntry('Litter & trail damage', 'On-device photo observations (development models)', Icons.cleaning_services, AppRoutes.component2),
  ModuleEntry('Hiker safety assistant', 'Module 3', Icons.health_and_safety, null),
];
