import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:decentralized_hiking_ai/features/hiking_assistant/services/offline_knowledge_database.dart';
import 'package:decentralized_hiking_ai/features/hiking_assistant/services/offline_question_router.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  test(
    'routes paraphrased hiking questions using bundled offline evidence',
    () async {
      final database = OfflineKnowledgeDatabase();
      final router = OfflineQuestionRouter(database: database);
      final cases = <String, List<String>>{
        'general_first_aid': ['A hiker has a cut that is bleeding.'],
        'hypothermia': [
          'My friend is extremely cold and shaking.',
          'Someone got soaked and is shivering badly.',
        ],
        'heat_illness': [
          'A walker is overheated with possible heat exhaustion.',
          'What helps with heatstroke on a trail?',
        ],
        'heavy_rain': ['Heavy rain is flooding the trail.'],
        'strong_wind': ['A gale is making hiking unsafe.'],
        'water_safety': ['How do we cross swift water safely?'],
        'remote_emergency': [
          'We need rescue during a remote hiking emergency.',
        ],
        'snakebite': [
          'A snake bit my hiking partner.',
          'What should we do after a snake bite?',
        ],
        'insect_bites_stings': ['My partner has a painful bee sting.'],
        'fracture_sprain': [
          'My friend fell and their ankle is badly swollen.',
          'I twisted my leg and cannot walk.',
        ],
        'burns': ['What first aid is needed for a burn?'],
        'poisoning': ['A hiker may have swallowed something poisonous.'],
        'allergic_reaction': [
          'My friend was stung and cannot breathe properly.',
          'What should I do for anaphylaxis?',
        ],
        'animal_encounter': [
          'How should we react to an aggressive wild animal?',
        ],
        'lost_navigation': [
          'We do not know where we are on the trail.',
          'I cannot find my way back after getting lost.',
        ],
        'landslide': ['There is a landslide on the mountain path.'],
        'lightning': [
          'There is lightning on an exposed ridge.',
          'What should hikers do in a thunderstorm?',
        ],
        'sri_lanka_emergency': [
          'How can I call an ambulance in Sri Lanka?',
          'We need emergency medical transport in Sri Lanka.',
        ],
      };
      for (final entry in cases.entries) {
        for (final question in entry.value) {
          final route = await router.route(question);
          expect(route.categories, contains(entry.key), reason: question);
        }
      }
      await database.close();
    },
  );

  test('does not route obvious non-hiking requests', () async {
    final database = OfflineKnowledgeDatabase();
    final route = await OfflineQuestionRouter(database: database)
        .route('Write Python code to sort a list.');
    expect(route.hasSufficientEvidence, isFalse);
    await database.close();
  });
}
