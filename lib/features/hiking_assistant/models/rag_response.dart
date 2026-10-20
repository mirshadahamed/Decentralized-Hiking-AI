import 'rag_retrieval_result.dart';

enum RagAnswerMode { verifiedDeterministic, localLlmRag, safeFallback }

class RagResponse {
  final RagAnswerMode answerMode;
  final String answer;
  final String context;
  final List<RagRetrievalResult> sources;
  final bool fallbackUsed;

  const RagResponse({
    required this.answerMode,
    required this.answer,
    required this.context,
    required this.sources,
    required this.fallbackUsed,
  });

  bool get hasEvidence => sources.isNotEmpty;
}
