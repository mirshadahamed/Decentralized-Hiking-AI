import 'dart:io';

import 'package:llama_flutter_android/llama_flutter_android.dart';

import '../models/local_llm_generation_result.dart';

/// Android-only local GGUF generation service.
///
/// This is deliberately independent of retrieval and HybridRagService. A
/// future caller can supply already-localized, bounded offline evidence.
class LocalLlmGenerationService {
  final String modelPath;
  final int threads;
  final int contextSize;
  final int maxTokens;

  LlamaController? _controller;
  bool _isInitializing = false;
  String? _initializationError;
  Duration? _modelLoadDuration;

  LocalLlmGenerationService({
    required this.modelPath,
    this.threads = 4,
    this.contextSize = 1024,
    this.maxTokens = 128,
  });

  bool get isInitialized => _controller != null;
  bool get isInitializing => _isInitializing;
  String? get initializationError => _initializationError;
  Duration? get modelLoadDuration => _modelLoadDuration;

  /// Loads the configured GGUF exactly once per service instance.
  ///
  /// Returns false rather than propagating model/file/native failures so UI
  /// callers can display [initializationError] safely.
  Future<bool> initialize() async {
    if (isInitialized) {
      return true;
    }
    if (_isInitializing) {
      return false;
    }

    _isInitializing = true;
    _initializationError = null;
    _modelLoadDuration = null;
    final controller = LlamaController();
    final stopwatch = Stopwatch()..start();

    try {
      if (!await File(modelPath).exists()) {
        throw FileSystemException('Model file was not found.', modelPath);
      }

      await controller.loadModel(
        modelPath: modelPath,
        threads: threads,
        contextSize: contextSize,
        // CPU-first benchmark configuration. This service does not force
        // Vulkan/GPU acceleration for the initial RAG integration step.
        gpuLayers: 0,
      );

      if (!await controller.isModelLoaded()) {
        throw StateError('The local model did not report a loaded state.');
      }

      _controller = controller;
      return true;
    } catch (error) {
      _initializationError = error.toString();
      try {
        await controller.dispose();
      } catch (_) {
        // Preserve the original loading error.
      }
      return false;
    } finally {
      stopwatch.stop();
      _modelLoadDuration = stopwatch.elapsed;
      _isInitializing = false;
    }
  }

  Future<LocalLlmGenerationResult> generateGroundedAnswer({
    required String question,
    required String context,
  }) async {
    final validationError = validateGenerationInput(
      question: question,
      context: context,
      isInitialized: isInitialized,
    );
    if (validationError != null) {
      return LocalLlmGenerationResult.failure(
        error: validationError,
        generationDuration: Duration.zero,
      );
    }

    final stopwatch = Stopwatch()..start();
    final output = StringBuffer();

    try {
      await for (final token in _controller!.generate(
        prompt: buildGroundedPrompt(question: question, context: context),
        maxTokens: maxTokens,
        temperature: 0.2,
        topP: 0.9,
        topK: 40,
      )) {
        output.write(token);
      }
      stopwatch.stop();

      final answer = sanitizeGeneratedOutput(output.toString());
      if (answer.isEmpty) {
        return LocalLlmGenerationResult.failure(
          error: 'Generation produced no usable answer from offline evidence.',
          generationDuration: stopwatch.elapsed,
        );
      }

      return LocalLlmGenerationResult(
        success: true,
        answer: answer,
        error: null,
        generationDuration: stopwatch.elapsed,
      );
    } catch (error) {
      stopwatch.stop();
      return LocalLlmGenerationResult.failure(
        error: error.toString(),
        generationDuration: stopwatch.elapsed,
      );
    }
  }

  Future<void> dispose() async {
    final controller = _controller;
    _controller = null;
    _initializationError = null;
    _modelLoadDuration = null;

    if (controller == null) {
      return;
    }

    try {
      await controller.dispose();
    } catch (_) {
      // Disposal is intentionally idempotent and must not crash the app.
    }
  }

  static String? validateGenerationInput({
    required String question,
    required String context,
    required bool isInitialized,
  }) {
    if (!isInitialized) {
      return 'Local model is not initialized.';
    }
    if (question.trim().isEmpty) {
      return 'Question is empty.';
    }
    if (context.trim().isEmpty) {
      return 'Offline evidence context is empty.';
    }
    return null;
  }

  static String buildGroundedPrompt({
    required String question,
    required String context,
  }) {
    return '''You are an offline hiking-safety assistant.

Answer ONLY from the OFFLINE EVIDENCE below. Do not invent facts or use
knowledge that is not present in the evidence. If the evidence is insufficient,
say that the offline evidence is insufficient. Do not introduce emergency phone
numbers unless they appear in the evidence. Keep the answer concise and give
practical hiking-safety guidance. Do not output reasoning, analysis,
chain-of-thought, or <think> content.

OFFLINE EVIDENCE:
$context

QUESTION:
$question

FINAL ANSWER:''';
  }

  /// Removes model reasoning blocks. An unterminated opening tag discards the
  /// remainder to avoid exposing reasoning text to the application.
  static String sanitizeGeneratedOutput(String rawOutput) {
    var cleaned = rawOutput.replaceAll(
      RegExp(
        r'<think\b[^>]*>.*?</think\s*>',
        caseSensitive: false,
        dotAll: true,
      ),
      '',
    );

    final unterminatedThink = RegExp(
      r'<think\b[^>]*>',
      caseSensitive: false,
    ).firstMatch(cleaned);
    if (unterminatedThink != null) {
      cleaned = cleaned.substring(0, unterminatedThink.start);
    }

    return cleaned.replaceAll(RegExp(r'\s+'), ' ').trim();
  }
}
