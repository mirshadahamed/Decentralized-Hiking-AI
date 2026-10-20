import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:decentralized_hiking_ai/features/hiking_assistant/services/offline_knowledge_database.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  // Initialize SQLite for Flutter tests running on macOS/desktop VM.
  // The Android application itself continues to use normal sqflite.
  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  // ------------------------------------------------------------
  // TEST 1
  // Verify that Flutter can open the real offline knowledge DB.
  // ------------------------------------------------------------
  test(
    'offline knowledge database contains expected data',
    () async {
      final database = OfflineKnowledgeDatabase();

      final documents = await database.getDocumentCount();
      final chunks = await database.getChunkCount();
      final ftsChunks = await database.getFtsChunkCount();

      expect(documents, 27);
      expect(chunks, 1795);
      expect(ftsChunks, 1795);

      await database.close();
    },
  );

  // ------------------------------------------------------------
  // TEST 2
  // Verify real FTS5 retrieval for allergic reaction guidance.
  // ------------------------------------------------------------
  test(
    'retrieves allergic reaction evidence from offline FTS5 database',
    () async {
      final database = OfflineKnowledgeDatabase();

      final results = await database.retrieve(
        question:
            'What should I do if a hiker develops a serious allergic reaction?',
        category: 'allergic_reaction',
        limit: 4,
      );

      // Retrieval must return evidence.
      expect(
        results,
        isNotEmpty,
      );

      // Primary retrieval is intentionally limited to top 4.
      expect(
        results.length,
        4,
      );

      // EXP_017 is the authoritative allergic-reaction source
      // currently stored in our offline knowledge base.
      expect(
        results.any(
          (result) => result.sourceId == 'EXP_017',
        ),
        isTrue,
      );

      // Ensure retrieved chunks actually contain content.
      expect(
        results.every(
          (result) => result.content.trim().isNotEmpty,
        ),
        isTrue,
      );

      // Ensure the retrieval remains category-consistent.
      expect(
        results.every(
          (result) =>
              result.categories.contains('allergic_reaction'),
        ),
        isTrue,
      );

      await database.close();
    },
  );

  test(
  'retrieves Sri Lanka emergency evidence from offline FTS5 database',
  () async {
    final database = OfflineKnowledgeDatabase();

    final results = await database.retrieve(
      question:
          'How can I request an emergency ambulance in Sri Lanka?',
      category: 'sri_lanka_emergency',
      limit: 4,
    );

    expect(
      results,
      isNotEmpty,
    );

    expect(
      results.length,
      4,
    );

    // EXP_015 is the authoritative Sri Lankan emergency
    // ambulance source in the offline knowledge base.
    expect(
      results.any(
        (result) => result.sourceId == 'EXP_015',
      ),
      isTrue,
    );

    expect(
      results.every(
        (result) =>
            result.categories.contains('sri_lanka_emergency'),
      ),
      isTrue,
    );

    // At least one retrieved chunk must contain the
    // evidence-supported Sri Lankan emergency number.
    expect(
      results.any(
        (result) => result.content.contains('1990'),
      ),
      isTrue,
    );

    await database.close();
  },
);
}