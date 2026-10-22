import 'package:flutter/material.dart';

import 'pp1_home_page.dart';
import 'router.dart';

class HikingAssistantApp extends StatelessWidget {
  const HikingAssistantApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Hiking Safety & Environmental Monitoring',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.green),
        useMaterial3: true,
      ),
      routes: AppRoutes.routes,
      home: const Pp1HomePage(),
    );
  }
}
