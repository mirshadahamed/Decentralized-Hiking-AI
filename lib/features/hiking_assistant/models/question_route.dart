class QuestionRoute {
  final List<String> categories;
  final Map<String, double> categoryScores;
  final bool hasSufficientEvidence;

  const QuestionRoute({
    required this.categories,
    required this.categoryScores,
    required this.hasSufficientEvidence,
  });

  const QuestionRoute.unsupported()
    : categories = const [],
      categoryScores = const {},
      hasSufficientEvidence = false;
}
