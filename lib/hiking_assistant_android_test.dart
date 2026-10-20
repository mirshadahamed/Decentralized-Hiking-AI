import 'dart:async';

import 'package:flutter/material.dart';

import 'features/hiking_assistant/presentation/hiking_assistant_screen.dart';
import 'features/hiking_assistant/services/hybrid_rag_service.dart';
import 'features/hiking_assistant/services/local_llm_generation_service.dart';
import 'features/hiking_assistant/services/offline_knowledge_database.dart';
import 'features/hiking_assistant/services/rag_context_builder.dart';
import 'features/hiking_assistant/services/rag_localization_filter.dart';

const _modelPath =
    '/data/user/0/com.mirshadahamed.decentralized_hiking_ai/files/Qwen3.5-0.8B-Q4_0.gguf';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const HikingAssistantAndroidTestApp());
}

/// Temporary Android-only composition root for validating the real offline
/// Hiking Assistant with the app-private Qwen model.
class HikingAssistantAndroidTestApp extends StatelessWidget {
  const HikingAssistantAndroidTestApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Hiking Assistant Android Test',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.green),
        useMaterial3: true,
      ),
      home: const _HikingAssistantBootstrap(),
    );
  }
}

class _HikingAssistantBootstrap extends StatefulWidget {
  const _HikingAssistantBootstrap();

  @override
  State<_HikingAssistantBootstrap> createState() =>
      _HikingAssistantBootstrapState();
}

class _HikingAssistantBootstrapState extends State<_HikingAssistantBootstrap> {
  OfflineKnowledgeDatabase? _database;
  LocalLlmGenerationService? _localLlm;
  HybridRagService? _ragService;
  String? _initializationError;

  @override
  void initState() {
    super.initState();
    unawaited(_initialize());
  }

  Future<void> _initialize() async {
    final database = OfflineKnowledgeDatabase();
    final localLlm = LocalLlmGenerationService(modelPath: _modelPath);
    _database = database;
    _localLlm = localLlm;

    try {
      // Open the bundled read-only database before exposing the assistant.
      await database.database;

      final modelLoaded = await localLlm.initialize();
      if (!modelLoaded) {
        throw StateError(
          localLlm.initializationError ??
              'The local Qwen model could not load.',
        );
      }

      final ragService = HybridRagService(
        database: database,
        contextBuilder: RagContextBuilder(database: database),
        localizationFilter: const RagLocalizationFilter(),
        localLlmGenerationService: localLlm,
      );

      if (!mounted) {
        return;
      }
      setState(() => _ragService = ragService);
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _initializationError =
            'Offline assistant validation could not be initialized. '
            'Confirm the bundled database and app-private Qwen model are available.';
      });
    }
  }

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

  @override
  Widget build(BuildContext context) {
    final ragService = _ragService;
    if (ragService != null) {
      return HikingAssistantScreen(ragService: ragService);
    }

    final error = _initializationError;
    if (error != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Hiking Assistant Android Test')),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(error, textAlign: TextAlign.center),
          ),
        ),
      );
    }

    return const Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text('Preparing offline knowledge and local Qwen model…'),
          ],
        ),
      ),
    );
  }
}
