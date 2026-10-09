import 'package:flutter/material.dart';

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
      home: const Scaffold(
        body: Center(
          child: Text('AI Hiking Assistant and Emergency Coordination System'),
        ),
      ),
    );
  }
}
