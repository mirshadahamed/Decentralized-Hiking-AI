import 'dart:async';

import 'package:flutter/material.dart';

import 'features/hiking_assistant/models/rag_response.dart';
import 'features/hiking_assistant/services/hybrid_rag_service.dart';
import 'features/hiking_assistant/services/local_llm_generation_service.dart';
import 'features/hiking_assistant/services/offline_knowledge_database.dart';

const _modelPath =
    '/data/user/0/com.mirshadahamed.decentralized_hiking_ai/files/Qwen3.5-0.8B-Q4_0.gguf';

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
  LocalLlmGenerationService? _localLlm;

  bool _busy = false;
  String _modelStatus = 'NOT LOADED';
  String _status = 'Ready';
  String _mode = '';
  String _sources = '';
  String _answer = '';
  String _duration = '—';
  String _localGenerationStatus = 'Not requested';

  @override
  void dispose() {
    final localLlm = _localLlm;
    final database = _database;
    _localLlm = null;
    _database = null;
    if (localLlm != null) {
      unawaited(localLlm.dispose());
    }
    if (database != null) {
      unawaited(database.close());
    }
    super.dispose();
  }

  OfflineKnowledgeDatabase _getDatabase() =>
      _database ??= OfflineKnowledgeDatabase();

  LocalLlmGenerationService _getLocalLlm() =>
      _localLlm ??= LocalLlmGenerationService(modelPath: _modelPath);

  Future<void> _loadLocalQwen() async {
    if (_busy) return;

    setState(() {
      _busy = true;
      _modelStatus = 'LOADING';
      _status = 'Loading local Qwen model…';
    });

    final localLlm = _getLocalLlm();
    final loaded = await localLlm.initialize();

    if (!mounted) return;
    setState(() {
      _busy = false;
      _modelStatus = loaded ? 'LOADED' : 'FAILED';
      _status = loaded
          ? 'MODEL LOADED (${_formatDuration(localLlm.modelLoadDuration)})'
          : 'MODEL LOAD FAILED\n${localLlm.initializationError ?? 'Unknown error'}';
    });
  }

  Future<void> _runAllergicReactionTest() async {
    if (_busy || _localLlm?.isInitialized != true) return;

    await _runPipeline(
      question: 'What should I do if a hiker has a severe allergic reaction?',
      category: 'allergic_reaction',
      localGenerationStatusOnSuccess: 'Local generation completed.',
      localGenerationStatusOnFallback:
          'Local generation did not produce a usable grounded answer.',
    );
  }

  Future<void> _runSriLankaEmergencyTest() async {
    if (_busy) return;

    await _runPipeline(
      question: 'How can I request an emergency ambulance in Sri Lanka?',
      category: 'sri_lanka_emergency',
      localGenerationStatusOnSuccess:
          'Local generation bypassed by verified deterministic route.',
      localGenerationStatusOnFallback: 'Local generation was not used because the emergency route failed closed.',
    );
  }

  Future<void> _runPipeline({
    required String question,
    required String category,
    required String localGenerationStatusOnSuccess,
    required String localGenerationStatusOnFallback,
  }) async {
    setState(() {
      _busy = true;
      _status = 'Running end-to-end offline RAG…';
      _mode = '';
      _sources = '';
      _answer = '';
      _duration = '—';
      _localGenerationStatus = 'Running…';
    });

    final stopwatch = Stopwatch()..start();
    try {
      final service = HybridRagService(
        database: _getDatabase(),
        localLlmGenerationService: _getLocalLlm(),
      );
      final response = await service.prepare(
        question: question,
        category: category,
      );
      stopwatch.stop();

      if (!mounted) return;
      setState(() {
        _status = response.fallbackUsed ? 'SAFE FALLBACK' : 'SUCCESS';
        _mode = _modeName(response.answerMode);
        _sources = response.sources
            .map((source) => source.sourceId)
            .toSet()
            .join(', ');
        _answer = response.answer;
        _duration = _formatDuration(stopwatch.elapsed);
        _localGenerationStatus = response.fallbackUsed
            ? localGenerationStatusOnFallback
            : localGenerationStatusOnSuccess;
      });
    } catch (error, stackTrace) {
      stopwatch.stop();
      debugPrint('End-to-end offline RAG test failed: $error');
      debugPrintStack(stackTrace: stackTrace);

      if (!mounted) return;
      setState(() {
        _status = 'FAILED';
        _answer = error.toString();
        _duration = _formatDuration(stopwatch.elapsed);
        _localGenerationStatus =
            'Pipeline exception; generation status unavailable.';
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String _formatDuration(Duration? duration) {
    if (duration == null) return '—';
    return '${duration.inMilliseconds} ms';
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
    final modelLoaded = _localLlm?.isInitialized == true;

    return Scaffold(
      appBar: AppBar(title: const Text('Offline RAG Android Test')),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Android End-to-End Offline RAG Validation',
                style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 12),
              const Text('Model path:'),
              SelectableText(_modelPath),
              const SizedBox(height: 12),
              Text('Model status: $_modelStatus'),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : _loadLocalQwen,
                child: const Text('Load Local Qwen'),
              ),
              const SizedBox(height: 12),
              FilledButton.tonal(
                onPressed: _busy || !modelLoaded
                    ? null
                    : _runAllergicReactionTest,
                child: const Text('Test Full Allergic-Reaction RAG'),
              ),
              const SizedBox(height: 12),
              FilledButton.tonal(
                onPressed: _busy ? null : _runSriLankaEmergencyTest,
                child: const Text('Test Sri Lanka Emergency'),
              ),
              const SizedBox(height: 20),
              if (_busy) const Center(child: CircularProgressIndicator()),
              const SizedBox(height: 12),
              _ResultField(label: 'Status', value: _status),
              _ResultField(label: 'RAG mode', value: _mode),
              _ResultField(
                label: 'Local generation',
                value: _localGenerationStatus,
              ),
              _ResultField(label: 'Source IDs', value: _sources),
              _ResultField(label: 'End-to-end duration', value: _duration),
              const Text(
                'Answer',
                style: TextStyle(fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 4),
              SelectableText(_answer.isEmpty ? '—' : _answer),
            ],
          ),
        ),
      ),
    );
  }
}

class _ResultField extends StatelessWidget {
  final String label;
  final String value;

  const _ResultField({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: const TextStyle(fontWeight: FontWeight.bold)),
          const SizedBox(height: 3),
          SelectableText(value.isEmpty ? '—' : value),
        ],
      ),
    );
  }
}
