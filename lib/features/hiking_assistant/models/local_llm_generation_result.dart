class LocalLlmGenerationResult {
  final bool success;
  final String answer;
  final String? error;
  final Duration generationDuration;

  const LocalLlmGenerationResult({
    required this.success,
    required this.answer,
    required this.error,
    required this.generationDuration,
  });

  factory LocalLlmGenerationResult.failure({
    required String error,
    required Duration generationDuration,
  }) {
    return LocalLlmGenerationResult(
      success: false,
      answer: '',
      error: error,
      generationDuration: generationDuration,
    );
  }
}
