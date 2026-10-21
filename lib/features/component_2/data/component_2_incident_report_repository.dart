import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import '../domain/component_2_incident_report.dart';

abstract interface class Component2IncidentReportRepository {
  Future<List<Component2IncidentReport>> all();
  Future<void> save(Component2IncidentReport report);
}

class SharedPreferencesComponent2IncidentReportRepository
    implements Component2IncidentReportRepository {
  static const _key = 'component2_offline_reports_v1';

  @override
  Future<List<Component2IncidentReport>> all() async {
    final preferences = await SharedPreferences.getInstance();
    final reports = (preferences.getStringList(_key) ?? const <String>[])
        .map(
          (encoded) => Component2IncidentReport.fromJson(
            (jsonDecode(encoded) as Map<String, dynamic>)
                .cast<String, Object?>(),
          ),
        )
        .toList();
    reports.sort((a, b) => b.createdAt.compareTo(a.createdAt));
    return reports;
  }

  @override
  Future<void> save(Component2IncidentReport report) async {
    final preferences = await SharedPreferences.getInstance();
    final reports = await all();
    reports.removeWhere((existing) => existing.id == report.id);
    reports.insert(0, report);
    await preferences.setStringList(
      _key,
      reports.map((item) => jsonEncode(item.toJson())).toList(growable: false),
    );
  }
}
