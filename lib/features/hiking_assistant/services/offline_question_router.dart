import '../models/question_route.dart';
import '../models/rag_retrieval_result.dart';
import 'offline_knowledge_database.dart';

/// Selects hiking knowledge categories from retrieved offline evidence.
///
/// The vocabulary signals only supplement database evidence for common hiking
/// terms and paraphrases; they never contain answers or bypass retrieval.
class OfflineQuestionRouter {
  static const _categories = <String>[
    'general_first_aid',
    'hypothermia',
    'heat_illness',
    'heavy_rain',
    'strong_wind',
    'water_safety',
    'remote_emergency',
    'snakebite',
    'insect_bites_stings',
    'fracture_sprain',
    'burns',
    'poisoning',
    'allergic_reaction',
    'animal_encounter',
    'lost_navigation',
    'landslide',
    'lightning',
    'sri_lanka_emergency',
  ];

  static const _signals = <String, List<String>>{
    'general_first_aid': ['first aid', 'bleeding', 'cut', 'wound', 'injured'],
    'hypothermia': [
      'hypothermia',
      'shivering',
      'shaking',
      'soaked',
      'very cold',
    ],
    'heat_illness': [
      'heatstroke',
      'heat exhaustion',
      'overheated',
      'heat illness',
    ],
    'heavy_rain': ['heavy rain', 'downpour', 'flood', 'monsoon'],
    'strong_wind': ['strong wind', 'high wind', 'gale', 'windy'],
    'water_safety': [
      'drowning',
      'river crossing',
      'swift water',
      'water safety',
    ],
    'remote_emergency': [
      'remote emergency',
      'rescue',
      'evacuation',
      'emergency plan',
    ],
    'snakebite': ['snakebite', 'snake bite', 'snake bit', 'venomous snake'],
    'insect_bites_stings': [
      'insect sting',
      'bee sting',
      'wasp sting',
      'bite or sting',
    ],
    'fracture_sprain': [
      'fracture',
      'broken',
      'broke',
      'broken bone',
      'sprain',
      'ankle',
      'twisted ankle',
      'cannot walk',
      'swollen ankle',
      'ankle is badly swollen',
      'badly swollen',
    ],
    'burns': ['burn', 'scald', 'burning'],
    'poisoning': ['poison', 'poisoning', 'toxic'],
    'allergic_reaction': [
      'anaphylaxis',
      'allergic reaction',
      'cannot breathe',
      'swelling',
    ],
    'animal_encounter': [
      'wild animal',
      'wildlife',
      'animal encounter',
      'aggressive animal',
    ],
    'lost_navigation': [
      'lost',
      'lost trail',
      'disoriented',
      'cannot find my way',
      'navigation',
      'do not know where we are',
    ],
    'landslide': ['landslide', 'mudslide', 'slope collapse'],
    'lightning': ['lightning', 'thunderstorm', 'thunder', 'exposed ridge'],
    'sri_lanka_emergency': [
      'sri lanka',
      'ambulance',
      'emergency number',
      'medical transport',
    ],
  };

  final OfflineKnowledgeDatabase database;
  final int maxCategories;

  const OfflineQuestionRouter({required this.database, this.maxCategories = 3});

  Future<QuestionRoute> route(String question) async {
    final normalized = question.trim().toLowerCase();
    if (normalized.isEmpty) return const QuestionRoute.unsupported();

    final evidence = await database.retrieveRoutingCandidates(
      question: normalized,
      limit: 48,
    );
    if (evidence.isEmpty) return const QuestionRoute.unsupported();

    final scores = <String, double>{
      for (final category in _categories) category: 0,
    };
    for (final result in evidence) {
      final resultCategories = _resultCategories(result);
      if (resultCategories.isEmpty) continue;
      final evidenceScore = _evidenceScore(normalized, result);
      if (evidenceScore == 0) continue;
      final share = evidenceScore / resultCategories.length;
      for (final category in resultCategories) {
        scores[category] = (scores[category] ?? 0) + share;
      }
    }

    for (final entry in _signals.entries) {
      final matches = entry.value.where(normalized.contains).length;
      if (matches > 0) {
        scores[entry.key] = (scores[entry.key] ?? 0) + matches * 6;
      }
    }

    final ranked = scores.entries.where((entry) => entry.value >= 4).toList()
      ..sort((left, right) {
        final score = right.value.compareTo(left.value);
        return score != 0 ? score : left.key.compareTo(right.key);
      });
    if (ranked.isEmpty) return const QuestionRoute.unsupported();

    final strongest = ranked.first.value;
    final selected = ranked
        .where((entry) => entry.value >= strongest * 0.45)
        .take(maxCategories)
        .map((entry) => entry.key)
        .toList(growable: false);
    return QuestionRoute(
      categories: selected,
      categoryScores: Map.unmodifiable({
        for (final entry in ranked) entry.key: entry.value,
      }),
      hasSufficientEvidence: true,
    );
  }

  List<String> _resultCategories(RagRetrievalResult result) {
    return result.categories
        .split(';')
        .map((category) => category.trim())
        .where(_categories.contains)
        .toList();
  }

  double _evidenceScore(String question, RagRetrievalResult result) {
    final terms = question
        .replaceAll(RegExp(r'[^a-z0-9\\s-]'), ' ')
        .split(RegExp(r'\\s+'))
        .where((word) => word.length >= 4)
        .toSet();
    final title = result.title.toLowerCase();
    final content = result.content.toLowerCase();
    var score = 0.0;
    for (final term in terms) {
      if (title.contains(term)) score += 4;
      if (content.contains(term)) score += 1;
    }
    return score;
  }
}
