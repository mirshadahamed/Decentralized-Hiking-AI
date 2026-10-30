import 'package:flutter/material.dart';

import '../data/api_client.dart';
import '../models/models.dart';
import '../services/edge_store.dart';
import 'screens/bottleneck_screen.dart';
import 'screens/destinations_screen.dart';
import 'screens/staff/login_screen.dart';
import 'screens/visitor/map_screen.dart';
import 'screens/visitor/my_tickets_screen.dart';
import 'screens/visitor/outlook_screen.dart';
import 'screens/visitor/overview_screen.dart';
import 'l10n/c4_i18n.dart';
import 'widgets/c4_ui.dart';

/// Entry point of Component 4 (crowd forecasting, trip planning, crowd control) inside the team app.
/// Trip planner: with the gateway the visitor first chooses a destination, then sees everything about it;
/// a single-park server opens that park directly.
class Component4Home extends StatefulWidget {
  const Component4Home({super.key, this.api, this.lang});

  final C4Api? api; // injected in tests
  final C4Lang? lang;

  @override
  State<Component4Home> createState() => _Component4HomeState();
}

class _Component4HomeState extends State<Component4Home> {
  late final C4Api _api = widget.api ?? C4Api();
  late final C4Lang _lang = widget.lang ?? C4Lang();
  late Future<List<ParkInfo>?> _parks;

  @override
  void initState() {
    super.initState();
    if (widget.lang == null) C4Lang.load().then((l) => _lang.set(l.code));
    _parks = _api.parks();
  }

  void _pick(String? id) => setState(() => _api.usePark(id));

  @override
  Widget build(BuildContext context) => C4Frame(
        api: _api,
        lang: _lang,
        child: FutureBuilder<List<ParkInfo>?>(
          future: _parks,
          builder: (context, snap) {
            if (snap.hasError) {
              return Scaffold(
                appBar: AppBar(),
                body: ErrorRetry(error: snap.error!, onRetry: () => setState(() { _parks = _api.parks(); })),
              );
            }
            if (snap.connectionState != ConnectionState.done) {
              return const Scaffold(body: Center(child: CircularProgressIndicator()));
            }
            final parks = snap.data;
            if (parks != null && _api.park == null) {
              return DestinationsScreen(parks: parks, onPick: _pick, actions: const [LanguageButton()]);
            }
            final back = parks != null && parks.length > 1;
            return PopScope(
              canPop: !back, // system back returns to the destinations, not out of the module
              onPopInvokedWithResult: (didPop, _) {
                if (!didPop) _pick(null);
              },
              child: ParkHome(key: ValueKey(_api.park), onChangePark: back ? () => _pick(null) : null),
            );
          },
        ),
      );
}

/// Menu to switch between English, Sinhala and Tamil.
class LanguageButton extends StatelessWidget {
  const LanguageButton({super.key});

  @override
  Widget build(BuildContext context) {
    final lang = C4Scope.langOf(context);
    if (lang == null) return const SizedBox.shrink();
    return PopupMenuButton<String>(
      tooltip: tr(context, 'language'),
      icon: const Icon(Icons.translate),
      initialValue: lang.code,
      onSelected: lang.set,
      itemBuilder: (_) => [for (final e in C4Lang.languages.entries) PopupMenuItem(value: e.key, child: Text(e.value))],
    );
  }
}

/// One destination: overview first, then booking parks get the calendar, map and tickets; pilgrim sites the
/// start-time planner and map.
class ParkHome extends StatefulWidget {
  const ParkHome({super.key, this.onChangePark});

  final VoidCallback? onChangePark;

  @override
  State<ParkHome> createState() => _ParkHomeState();
}

class _ParkHomeState extends State<ParkHome> {
  late Future<ServerStatus> _status;
  int _tab = 0;
  final _visited = <int>{0}; // build tabs when first opened

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final api = C4Scope.of(context);
    _status = api.status();
    _status.then((_) {
      if (api.offline.value == null) {
        api.prefetch(); // online: keep this park's screens for offline use
        EdgeStore.load(api).catchError((_) => null); // and tomorrow's forecast pack (bottleneck map offline)
      }
    }, onError: (_) {});
  }

  void _open(int i) => setState(() {
        _tab = i;
        _visited.add(i);
      });

  @override
  Widget build(BuildContext context) => FutureBuilder<ServerStatus>(
        future: _status,
        builder: (context, snap) {
          final s = snap.data;
          final advisory = s?.isAdvisory ?? false;
          final pages = s == null
              ? <(Widget, IconData, String)>[]
              : [
                  (OverviewScreen(onPlan: () => _open(1)), Icons.explore_outlined, 'nav_overview'),
                  (OutlookScreen(site: s.site, advisory: advisory), Icons.calendar_month, advisory ? 'nav_start_times' : 'nav_plan_book'),
                  (const BottleneckView(), Icons.groups_outlined, 'nav_crowding'), // tomorrow per section, offline
                  (const MapScreen(), Icons.map_outlined, 'nav_map'),
                  if (s.hasTickets) (const MyTicketsScreen(), Icons.confirmation_number_outlined, 'nav_tickets'),
                ];
          return Scaffold(
            appBar: AppBar(
              leading: widget.onChangePark == null
                  ? null
                  : IconButton(tooltip: tr(context, 'change_park'), icon: const Icon(Icons.arrow_back), onPressed: widget.onChangePark),
              title: Text(s?.site ?? ''),
              actions: [
                const LanguageButton(),
                TextButton.icon(
                  onPressed: () => Navigator.of(context).push(c4Route(context, StaffLoginScreen(advisory: advisory))),
                  icon: const Icon(Icons.badge_outlined),
                  label: Text(tr(context, 'staff')),
                ),
              ],
            ),
            body: snap.hasError
                ? ErrorRetry(error: snap.error!, onRetry: () => setState(() { _status = C4Scope.of(context).status(); }))
                : s == null
                    ? const Center(child: CircularProgressIndicator())
                    : IndexedStack(
                        index: _tab,
                        children: [for (var i = 0; i < pages.length; i++) _visited.contains(i) ? pages[i].$1 : const SizedBox.shrink()],
                      ),
            bottomNavigationBar: pages.isEmpty
                ? null
                : NavigationBar(
                    selectedIndex: _tab,
                    onDestinationSelected: _open,
                    destinations: [for (final p in pages) NavigationDestination(icon: Icon(p.$2), label: tr(context, p.$3))],
                  ),
          );
        },
      );
}
