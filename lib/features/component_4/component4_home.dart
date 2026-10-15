import 'package:flutter/material.dart';

import 'data/api_client.dart';
import 'screens/staff/login_screen.dart';
import 'screens/visitor/my_tickets_screen.dart';
import 'screens/visitor/outlook_screen.dart';
import 'ui/c4_ui.dart';

/// Entry point of Component 4 (crowd forecasting, booking, entry control) inside the team app.
class Component4Home extends StatefulWidget {
  const Component4Home({super.key, this.api});

  final C4Api? api; // injected in tests

  @override
  State<Component4Home> createState() => _Component4HomeState();
}

class _Component4HomeState extends State<Component4Home> {
  late final C4Api _api = widget.api ?? C4Api();
  int _tab = 0;

  @override
  Widget build(BuildContext context) => C4Scope(
        api: _api,
        child: Builder(
          builder: (context) => Scaffold(
            appBar: AppBar(
              title: const Text('Horton Plains · visit planner'),
              actions: [
                TextButton.icon(
                  onPressed: () => Navigator.of(context).push(c4Route(context, const StaffLoginScreen())),
                  icon: const Icon(Icons.badge_outlined),
                  label: const Text('Staff'),
                ),
              ],
            ),
            body: IndexedStack(index: _tab, children: const [OutlookScreen(), MyTicketsScreen()]),
            bottomNavigationBar: NavigationBar(
              selectedIndex: _tab,
              onDestinationSelected: (i) => setState(() => _tab = i),
              destinations: const [
                NavigationDestination(icon: Icon(Icons.calendar_month), label: 'Plan & book'),
                NavigationDestination(icon: Icon(Icons.confirmation_number_outlined), label: 'My tickets'),
              ],
            ),
          ),
        ),
      );
}
