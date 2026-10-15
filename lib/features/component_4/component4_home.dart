import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'data/api_client.dart';
import 'data/models.dart';
import 'screens/park_picker.dart';
import 'screens/staff/login_screen.dart';
import 'screens/visitor/map_screen.dart';
import 'screens/visitor/my_tickets_screen.dart';
import 'screens/visitor/outlook_screen.dart';
import 'ui/c4_i18n.dart';
import 'ui/c4_ui.dart';

/// Entry point of Component 4 (crowd forecasting, booking, entry control) inside the team app.
/// With the gateway the visitor first picks a park (remembered); a single-park server opens directly.
class Component4Home extends StatefulWidget {
  const Component4Home({super.key, this.api, this.lang});

  final C4Api? api; // injected in tests
  final C4Lang? lang;

  @override
  State<Component4Home> createState() => _Component4HomeState();
}

const _parkKey = 'c4_park';

class _Component4HomeState extends State<Component4Home> {
  late final C4Api _api = widget.api ?? C4Api();
  late final C4Lang _lang = widget.lang ?? C4Lang();
  late Future<List<ParkInfo>?> _parks;

  @override
  void initState() {
    super.initState();
    if (widget.lang == null) C4Lang.load().then((l) => _lang.set(l.code));
    _parks = _loadParks();
  }

  Future<List<ParkInfo>?> _loadParks() async {
    final parks = await _api.parks();
    if (parks != null && _api.park == null) {
      final saved = (await SharedPreferences.getInstance()).getString(_parkKey);
      if (parks.any((p) => p.id == saved)) _api.usePark(saved);
    }
    return parks;
  }

  Future<void> _pick(String? id) async {
    setState(() => _api.usePark(id));
    final p = await SharedPreferences.getInstance();
    id == null ? await p.remove(_parkKey) : await p.setString(_parkKey, id);
  }

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
                body: ErrorRetry(error: snap.error!, onRetry: () => setState(() { _parks = _loadParks(); })),
              );
            }
            if (snap.connectionState != ConnectionState.done) {
              return const Scaffold(body: Center(child: CircularProgressIndicator()));
            }
            final parks = snap.data;
            if (parks != null && _api.park == null) {
              return ParkPicker(parks: parks, onPick: _pick, actions: const [LanguageButton()]);
            }
            return ParkHome(
              key: ValueKey(_api.park),
              onChangePark: parks != null && parks.length > 1 ? () => _pick(null) : null,
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

/// One park: booking parks get the calendar, map and tickets; pilgrim sites the start-time planner and map.
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
    _status = C4Scope.of(context).status();
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<ServerStatus>(
        future: _status,
        builder: (context, snap) {
          final s = snap.data;
          final advisory = s?.isAdvisory ?? false;
          final pages = s == null
              ? <(Widget, IconData, String)>[]
              : [
                  (OutlookScreen(site: s.site, advisory: advisory), Icons.calendar_month, advisory ? 'nav_start_times' : 'nav_plan_book'),
                  (const MapScreen(), Icons.map_outlined, 'nav_map'),
                  if (!advisory) (const MyTicketsScreen(), Icons.confirmation_number_outlined, 'nav_tickets'),
                ];
          return Scaffold(
            appBar: AppBar(
              title: Text(s == null ? '' : '${s.site} · ${tr(context, 'visit_planner')}'),
              actions: [
                if (widget.onChangePark != null)
                  IconButton(tooltip: tr(context, 'change_park'), icon: const Icon(Icons.swap_horiz), onPressed: widget.onChangePark),
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
                    onDestinationSelected: (i) => setState(() {
                      _tab = i;
                      _visited.add(i);
                    }),
                    destinations: [for (final p in pages) NavigationDestination(icon: Icon(p.$2), label: tr(context, p.$3))],
                  ),
          );
        },
      );
}
