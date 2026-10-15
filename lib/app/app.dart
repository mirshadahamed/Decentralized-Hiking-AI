import 'package:flutter/material.dart';

import 'router.dart';

class HikingAssistantApp extends StatelessWidget {
  const HikingAssistantApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI Hiking Assistant',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.green),
        useMaterial3: true,
      ),
      routes: AppRoutes.routes,
      home: const _HomeScreen(),
    );
  }
}

class _HomeScreen extends StatelessWidget {
  const _HomeScreen();

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(title: const Text('AI Hiking Assistant')),
        body: ListView(padding: const EdgeInsets.all(16), children: [
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Text('AI Hiking Assistant and Emergency Coordination System',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          for (final m in modules)
            Card(
              child: ListTile(
                leading: Icon(m.icon, size: 32),
                title: Text(m.title),
                subtitle: Text(m.route == null ? '${m.subtitle} · coming soon' : m.subtitle),
                enabled: m.route != null,
                trailing: const Icon(Icons.chevron_right),
                onTap: m.route == null ? null : () => Navigator.of(context).pushNamed(m.route!),
              ),
            ),
        ]),
      );
}
