import 'package:flutter/material.dart';

import '../features/component_2/presentation/component_2_home.dart';
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
      home: const Component2Home(),
    );
  }
}
