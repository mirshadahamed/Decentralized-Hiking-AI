import 'package:flutter/material.dart';

import 'features/hiking_assistant/models/rag_response.dart';
import 'features/hiking_assistant/services/hybrid_rag_service.dart';
import 'features/hiking_assistant/services/offline_knowledge_database.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const RagAndroidTestApp());
}

class RagAndroidTestApp extends StatelessWidget {
  const RagAndroidTestApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Offline RAG Android Test',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.green),
        useMaterial3: true,
      ),
      home: const RagAndroidTestPage(),
    );
  }
}

class RagAndroidTestPage extends StatefulWidget {
  const RagAndroidTestPage({super.key});

  @override
  State<RagAndroidTestPage> createState() => _RagAndroidTestPageState();
}

class _RagAndroidTestPageState extends State<RagAndroidTestPage> {
  OfflineKnowledgeDatabase? _database;

  bool _loading = false;
  String _status = 'Ready';
  String _answer = '';
  String _mode = '';
  String _sources = '';
  String _contextInfo = '';

  @override
  void dispose() {
    _database?.close();
    super.dispose();
  }

  Future<void> _runSriLankaEmergencyTest() async {
    setState(() {
      _loading = true;
      _status = 'Running offline RAG pipeline...';
      _answer = '';
      _mode = '';
      _sources = '';
      _contextInfo = '';
    });

    try {
      final database = _database ??= OfflineKnowledgeDatabase();

      final service = HybridRagService(database: database);

      final response = await service.prepare(
        question: 'How can I request an emergency ambulance in Sri Lanka?',
        category: 'sri_lanka_emergency',
      );

      if (!mounted) return;

      setState(() {
        _loading = false;
        _status = 'SUCCESS';
        _answer = response.answer;
        _mode = _modeName(response.answerMode);
        _sources = response.sources
            .map((source) => source.sourceId)
            .toSet()
            .join(', ');
        _contextInfo =
            '${response.context.split(RegExp(r"\s+")).where((word) => word.isNotEmpty).length} context words';
      });
    } catch (error, stackTrace) {
      debugPrint('Offline RAG Android test failed: $error');
      debugPrintStack(stackTrace: stackTrace);

      if (!mounted) return;

      setState(() {
        _loading = false;
        _status = 'FAILED';
        _answer = error.toString();
        _mode = '';
        _sources = '';
        _contextInfo = '';
      });
    }
  }

  Future<void> _runAllergicReactionTest() async {
    setState(() {
      _loading = true;
      _status = 'Running offline allergic-reaction retrieval...';
      _answer = '';
      _mode = '';
      _sources = '';
      _contextInfo = '';
    });

    try {
      final database = _database ??= OfflineKnowledgeDatabase();

      final service = HybridRagService(database: database);

      final response = await service.prepare(
        question:
            'What should I do if a hiker develops a serious allergic reaction?',
        category: 'allergic_reaction',
      );

      final lowerContext = response.context.toLowerCase();

      final hasAdrenaline = lowerContext.contains('adrenaline');

      final hasAutoInjector = lowerContext.contains('auto-injector');

      final has999 = RegExp(r'\b999\b').hasMatch(response.context);

      final has111 = RegExp(r'\b111\b').hasMatch(response.context);

      final hasNhs = lowerContext.contains('nhs');

      if (!mounted) return;

      setState(() {
        _loading = false;
        _status = 'SUCCESS';
        _mode = _modeName(response.answerMode);
        _sources = response.sources
            .map((source) => source.sourceId)
            .toSet()
            .join(', ');

        _answer = [
          'Adrenaline evidence: $hasAdrenaline',
          'Auto-injector evidence: $hasAutoInjector',
          'Contains foreign 999: $has999',
          'Contains foreign 111: $has111',
          'Contains NHS marker: $hasNhs',
        ].join('\n');

        _contextInfo =
            '${response.context.split(RegExp(r"\s+")).where((word) => word.isNotEmpty).length} context words';
      });
    } catch (error, stackTrace) {
      debugPrint('Offline allergic-reaction Android test failed: $error');
      debugPrintStack(stackTrace: stackTrace);

      if (!mounted) return;

      setState(() {
        _loading = false;
        _status = 'FAILED';
        _answer = error.toString();
        _mode = '';
        _sources = '';
        _contextInfo = '';
      });
    }
  }

  String _modeName(RagAnswerMode mode) {
    switch (mode) {
      case RagAnswerMode.verifiedDeterministic:
        return 'verified_deterministic';

      case RagAnswerMode.localLlmRag:
        return 'local_llm_rag';

      case RagAnswerMode.safeFallback:
        return 'safe_fallback';
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Offline RAG Android Test')),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              'Android Offline RAG Validation',
              style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
            ),

            const SizedBox(height: 12),

            const Text(
              'This screen tests the bundled SQLite database, '
              'FTS5 retrieval, bounded context, localization '
              'filtering, and hybrid safety routing.',
            ),

            const SizedBox(height: 24),

            ElevatedButton(
              onPressed: _loading ? null : _runSriLankaEmergencyTest,
              child: const Text('Test Sri Lanka Emergency'),
            ),

            const SizedBox(height: 12),

            ElevatedButton(
              onPressed: _loading ? null : _runAllergicReactionTest,
              child: const Text('Test Allergic Reaction'),
            ),

            const SizedBox(height: 24),

            if (_loading) const Center(child: CircularProgressIndicator()),

            const SizedBox(height: 16),

            Text(
              'Status: $_status',
              style: const TextStyle(fontWeight: FontWeight.bold),
            ),

            if (_mode.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('Mode: $_mode'),
            ],

            if (_sources.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('Sources: $_sources'),
            ],

            if (_contextInfo.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(_contextInfo),
            ],

            if (_answer.isNotEmpty) ...[
              const SizedBox(height: 16),
              const Text(
                'Result',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 6),
              SelectableText(_answer),
            ],
          ],
        ),
      ),
    );
  }
}
