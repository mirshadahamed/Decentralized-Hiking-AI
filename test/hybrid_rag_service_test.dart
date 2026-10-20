import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:decentralized_hiking_ai/features/hiking_assistant/models/rag_response.dart';
import 'package:decentralized_hiking_ai/features/hiking_assistant/models/rag_retrieval_result.dart';
import 'package:decentralized_hiking_ai/features/hiking_assistant/services/hybrid_rag_service.dart';
import 'package:decentralized_hiking_ai/features/hiking_assistant/services/offline_knowledge_database.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    sqfliteFfiInit();
    databaseFactory = databaseFactoryFfi;
  });

  // ------------------------------------------------------------
  // TEST 1
  // Real Sri Lankan emergency evidence must use the verified
  // deterministic route.
  // ------------------------------------------------------------
  test('Sri Lanka emergency uses verified deterministic route', () async {
    final database = OfflineKnowledgeDatabase();

    final service = HybridRagService(database: database);

    final response = await service.prepare(
      question: 'How can I request an emergency ambulance in Sri Lanka?',
      category: 'sri_lanka_emergency',
    );

    expect(response.answerMode, RagAnswerMode.verifiedDeterministic);

    expect(response.fallbackUsed, isFalse);

    expect(response.answer.contains('1990'), isTrue);

    expect(
      response.sources.any((source) => source.sourceId == 'EXP_015'),
      isTrue,
    );

    await database.close();
  });

  // ------------------------------------------------------------
  // TEST 2
  // Allergic-reaction evidence must be prepared for the future
  // local LLM without foreign emergency/localization details.
  // ------------------------------------------------------------
  test('allergic reaction uses sanitized local LLM RAG route', () async {
    final database = OfflineKnowledgeDatabase();

    final service = HybridRagService(database: database);

    final response = await service.prepare(
      question:
          'What should I do if a hiker develops a serious allergic reaction?',
      category: 'allergic_reaction',
    );

    expect(response.answerMode, RagAnswerMode.localLlmRag);

    expect(response.fallbackUsed, isFalse);

    expect(response.context.trim(), isNotEmpty);

    expect(response.context.toLowerCase().contains('adrenaline'), isTrue);

    expect(response.context.toLowerCase().contains('auto-injector'), isTrue);

    // Foreign emergency numbers must not reach
    // the future local LLM.
    expect(RegExp(r'\b999\b').hasMatch(response.context), isFalse);

    expect(RegExp(r'\b111\b').hasMatch(response.context), isFalse);

    // UK-specific source branding must also be removed.
    expect(response.context.toLowerCase().contains('nhs'), isFalse);

    // Real allergic-reaction evidence must still be present.
    expect(
      response.sources.any((source) => source.sourceId == 'EXP_017'),
      isTrue,
    );

    await database.close();
  });

  // ------------------------------------------------------------
  // TEST 3
  // Lost-navigation evidence may contain transferable guidance,
  // but New Zealand-specific localization must be removed.
  // ------------------------------------------------------------
  test('lost navigation removes foreign localization markers', () async {
    final database = OfflineKnowledgeDatabase();

    final service = HybridRagService(database: database);

    final response = await service.prepare(
      question: 'What should I do if I become lost while hiking?',
      category: 'lost_navigation',
    );

    expect(response.answerMode, RagAnswerMode.localLlmRag);

    expect(response.context.trim(), isNotEmpty);

    final lower = response.context.toLowerCase();

    expect(lower.contains('new zealand'), isFalse);

    expect(lower.contains('linz'), isFalse);

    expect(lower.contains('topo50'), isFalse);

    expect(RegExp(r'\b111\b').hasMatch(response.context), isFalse);

    await database.close();
  });

  // ------------------------------------------------------------
  // TEST 4
  // Merely mentioning Sri Lanka + 1990 + ambulance is NOT enough.
  // The evidence must come from approved source EXP_015.
  // ------------------------------------------------------------
  test('unapproved source cannot verify Sri Lanka 1990 route', () {
    final database = OfflineKnowledgeDatabase();

    final service = HybridRagService(database: database);

    const fakeEvidence = [
      RagRetrievalResult(
        chunkId: 'TEST_001',
        sourceId: 'UNVERIFIED_SOURCE',
        sourceChunkIndex: 0,
        content: 'For an emergency ambulance in Sri Lanka dial 1990.',
        categories: 'sri_lanka_emergency',
        title: 'Unverified test source',
        organization: 'Test',
        countryContext: 'Sri Lanka',
      ),
    ];

    final verified = service.verifySriLanka1990Evidence(fakeEvidence);

    expect(verified, isFalse);
  });

  // ------------------------------------------------------------
  // TEST 5
  // Even EXP_015 must not verify the route if its country
  // metadata does not identify Sri Lanka.
  // ------------------------------------------------------------
  test('foreign evidence cannot verify Sri Lanka 1990 route', () {
    final database = OfflineKnowledgeDatabase();

    final service = HybridRagService(database: database);

    const fakeEvidence = [
      RagRetrievalResult(
        chunkId: 'TEST_002',
        sourceId: 'EXP_015',
        sourceChunkIndex: 0,
        content: 'For an emergency ambulance dial 1990.',
        categories: 'sri_lanka_emergency',
        title: 'Test evidence',
        organization: 'Test',
        countryContext: 'United Kingdom (England)',
      ),
    ];

    final verified = service.verifySriLanka1990Evidence(fakeEvidence);

    expect(verified, isFalse);
  });

  // ------------------------------------------------------------
  // TEST 6
  // Approved source + Sri Lanka metadata is still insufficient
  // when the evidence does not explicitly contain 1990.
  // ------------------------------------------------------------
  test('Sri Lanka emergency evidence without 1990 cannot verify route', () {
    final database = OfflineKnowledgeDatabase();

    final service = HybridRagService(database: database);

    const fakeEvidence = [
      RagRetrievalResult(
        chunkId: 'TEST_003',
        sourceId: 'EXP_015',
        sourceChunkIndex: 0,
        content:
            'This source describes a pre-hospital emergency ambulance service.',
        categories: 'sri_lanka_emergency',
        title: 'Sri Lanka emergency source',
        organization: 'Test',
        countryContext: 'Sri Lanka',
      ),
    ];

    final verified = service.verifySriLanka1990Evidence(fakeEvidence);

    expect(verified, isFalse);
  });
}
