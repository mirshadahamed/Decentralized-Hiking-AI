import 'dart:io';

import 'package:llama_flutter_android/llama_flutter_android.dart';

import '../models/local_llm_generation_result.dart';

typedef LocalLlmGenerationRunner = Future<String> Function({
  required String prompt,
  required int maxTokens,
});

class LocalLlmPromptPreparation {
  final String? prompt;
  final String evidence;
  final String? error;
  final int inputTokenBudget;
  final int estimatedPromptTokens;
  final bool evidenceWasTruncated;

  const LocalLlmPromptPreparation({
    required this.prompt,
    required this.evidence,
    required this.error,
    required this.inputTokenBudget,
    required this.estimatedPromptTokens,
    required this.evidenceWasTruncated,
  });

  bool get canGenerate => prompt != null && error == null;
}

/// Android-only local GGUF generation service.
///
/// This is deliberately independent of retrieval and HybridRagService. A
/// future caller can supply already-localized, bounded offline evidence.
class LocalLlmGenerationService {
  // This is an engineering guard for a 4–6 GB Android target, not a medical
  // threshold. Native tokenization can differ from this English-text estimate,
  // so the margin deliberately leaves capacity beyond requested output tokens.
  static const int _safetyMarginTokens = 192;
  static const int _charactersPerEstimatedToken = 3;

  final String modelPath;
  final int threads;
  final int contextSize;
  final int maxTokens;

  LlamaController? _controller;
  bool _isInitializing = false;
  String? _initializationError;
  Duration? _modelLoadDuration;
  final bool _testingInitialized;
  final LocalLlmGenerationRunner? _testingGenerationRunner;

  LocalLlmGenerationService({
    required this.modelPath,
    this.threads = 4,
    this.contextSize = 1024,
    this.maxTokens = 128,
  }) : _testingInitialized = false,
       _testingGenerationRunner = null;

  /// Test-only construction path that never creates or loads a native model.
  LocalLlmGenerationService.forTesting({
    required LocalLlmGenerationRunner generationRunner,
    this.contextSize = 1024,
    this.maxTokens = 128,
    this.threads = 4,
  }) : modelPath = 'test-only.gguf',
       _testingInitialized = true,
       _testingGenerationRunner = generationRunner;

  bool get isInitialized => _controller != null || _testingInitialized;
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
      final preparedPrompt = prepareGroundedPrompt(
        question: question,
        context: context,
        contextSize: contextSize,
        maxTokens: maxTokens,
      );
      if (!preparedPrompt.canGenerate) {
        stopwatch.stop();
        return LocalLlmGenerationResult.failure(
          error: preparedPrompt.error!,
          generationDuration: stopwatch.elapsed,
        );
      }

      final testRunner = _testingGenerationRunner;
      if (testRunner != null) {
        output.write(
          await testRunner(
            prompt: preparedPrompt.prompt!,
            maxTokens: maxTokens,
          ),
        );
      } else {
        await for (final token in _controller!.generate(
          prompt: preparedPrompt.prompt!,
          maxTokens: maxTokens,
          temperature: 0.2,
          topP: 0.9,
          topK: 40,
        )) {
          output.write(token);
        }
      }
      stopwatch.stop();

      final answer = sanitizeGeneratedOutput(output.toString());
      final qualityError = validateGeneratedAnswer(answer);
      if (qualityError != null) {
        return LocalLlmGenerationResult.failure(
          error: qualityError,
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

  /// Rejects incomplete local-model output rather than presenting a fragment
  /// as grounded hiking guidance. This is a format guard, not medical logic.
  static String? validateGeneratedAnswer(String answer) {
    final normalized = answer.trim();
    if (normalized.length < 24 || normalized.split(RegExp(r'\s+')).length < 5) {
      return 'Generation produced no usable answer from offline evidence.';
    }
    if (RegExp(
          r'^(the following is|here is|final answer|answer\s*:)',
          caseSensitive: false,
        ).hasMatch(normalized) ||
        RegExp(
          r'\b(final|answer)\.?$',
          caseSensitive: false,
        ).hasMatch(normalized)) {
      return 'Generation produced an incomplete answer from offline evidence.';
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

  /// Builds a bounded prompt while retaining all instructions and the original
  /// question. Only the end of the sanitized evidence is shortened.
  static LocalLlmPromptPreparation prepareGroundedPrompt({
    required String question,
    required String context,
    required int contextSize,
    required int maxTokens,
  }) {
    final inputTokenBudget = contextSize - maxTokens - _safetyMarginTokens;
    final normalizedQuestion = question.trim();
    final originalEvidence = context.trim();

    if (originalEvidence.isEmpty) {
      return LocalLlmPromptPreparation(
        prompt: null,
        evidence: '',
        error: 'Offline evidence context is empty.',
        inputTokenBudget: inputTokenBudget,
        estimatedPromptTokens: 0,
        evidenceWasTruncated: false,
      );
    }

    final promptWithoutEvidence = buildGroundedPrompt(
      question: normalizedQuestion,
      context: '',
    );
    final fixedPromptTokens = _estimateTokens(promptWithoutEvidence);
    if (inputTokenBudget <= 0 || fixedPromptTokens >= inputTokenBudget) {
      return LocalLlmPromptPreparation(
        prompt: null,
        evidence: '',
        error: 'Question and grounding instructions exceed the mobile input budget.',
        inputTokenBudget: inputTokenBudget,
        estimatedPromptTokens: fixedPromptTokens,
        evidenceWasTruncated: false,
      );
    }

    final remainingEvidenceCharacters =
        (inputTokenBudget - fixedPromptTokens) * _charactersPerEstimatedToken;
    var evidence = _truncateEvidenceAtWordBoundary(
      originalEvidence,
      remainingEvidenceCharacters,
    );
    var prompt = buildGroundedPrompt(
      question: normalizedQuestion,
      context: evidence,
    );

    // Ceiling effects in the approximation can leave a few extra estimated
    // tokens. Reduce only evidence until the guard is satisfied.
    while (evidence.isNotEmpty && _estimateTokens(prompt) > inputTokenBudget) {
      evidence = evidence.substring(0, evidence.length - 1).trimRight();
      prompt = buildGroundedPrompt(
        question: normalizedQuestion,
        context: evidence,
      );
    }

    if (evidence.isEmpty) {
      return LocalLlmPromptPreparation(
        prompt: null,
        evidence: '',
        error: 'Offline evidence cannot fit within the mobile input budget.',
        inputTokenBudget: inputTokenBudget,
        estimatedPromptTokens: _estimateTokens(prompt),
        evidenceWasTruncated: true,
      );
    }

    return LocalLlmPromptPreparation(
      prompt: prompt,
      evidence: evidence,
      error: null,
      inputTokenBudget: inputTokenBudget,
      estimatedPromptTokens: _estimateTokens(prompt),
      evidenceWasTruncated: evidence.length < originalEvidence.length,
    );
  }

  static int _estimateTokens(String text) {
    return (text.trim().length / _charactersPerEstimatedToken).ceil();
  }

  static String _truncateEvidenceAtWordBoundary(
    String evidence,
    int maxCharacters,
  ) {
    if (evidence.length <= maxCharacters) {
      return evidence;
    }
    if (maxCharacters <= 0) {
      return '';
    }

    final candidate = evidence.substring(0, maxCharacters);
    final boundary = candidate.lastIndexOf(RegExp(r'\s'));
    return (boundary > 0 ? candidate.substring(0, boundary) : candidate).trim();
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

    // A local model can occasionally echo the prompt instead of answering.
    // Prompt labels are reserved by this service, so never expose such an echo.
    final finalAnswer = RegExp(
      r'FINAL ANSWER\s*:',
      caseSensitive: false,
    ).allMatches(cleaned).toList();
    if (finalAnswer.isNotEmpty) {
      cleaned = cleaned.substring(finalAnswer.last.end);
    } else if (RegExp(
      r'(OFFLINE EVIDENCE\s*:|QUESTION\s*:|You are an offline hiking-safety assistant)',
      caseSensitive: false,
    ).hasMatch(cleaned)) {
      return '';
    }

    return cleaned.replaceAll(RegExp(r'\s+'), ' ').trim();
  }
}
