import '../models/rag_response.dart';
import '../models/rag_retrieval_result.dart';
import 'local_llm_generation_service.dart';
import 'offline_knowledge_database.dart';
import 'rag_context_builder.dart';
import 'rag_localization_filter.dart';

class HybridRagService {
  final OfflineKnowledgeDatabase database;
  final RagContextBuilder contextBuilder;
  final RagLocalizationFilter localizationFilter;
  final LocalLlmGenerationService? localLlmGenerationService;

  HybridRagService({
    required this.database,
    RagContextBuilder? contextBuilder,
    RagLocalizationFilter? localizationFilter,
    this.localLlmGenerationService,
  }) : contextBuilder = contextBuilder ?? RagContextBuilder(database: database),
       localizationFilter = localizationFilter ?? const RagLocalizationFilter();

  Future<RagResponse> prepare({
    required String question,
    required String category,
  }) async {
    // ----------------------------------------------------------
    // 1. Primary offline FTS5 retrieval.
    // ----------------------------------------------------------

    final seeds = await database.retrieve(
      question: question,
      category: category,
      limit: 4,
    );

    if (seeds.isEmpty) {
      return _safeFallback();
    }

    // ----------------------------------------------------------
    // 2. Bounded adjacent-chunk continuity.
    // ----------------------------------------------------------

    final boundedContext = await contextBuilder.buildBoundedContext(
      seedResults: seeds,
      neighborDistance: 1,
      maxWords: 1200,
    );

    if (boundedContext.contextResults.isEmpty) {
      return _safeFallback();
    }

    // ----------------------------------------------------------
    // 3. Critical Sri Lankan emergency route.
    //
    // 1990 is returned only when authoritative offline evidence
    // satisfies the verification conditions below.
    // ----------------------------------------------------------

    if (category == 'sri_lanka_emergency') {
      final verified = verifySriLanka1990Evidence(
        boundedContext.contextResults,
      );

      if (verified) {
        return RagResponse(
          answerMode: RagAnswerMode.verifiedDeterministic,
          answer:
              'For a medical emergency in Sri Lanka, '
              'you can request the 1990 Suwa Seriya '
              'pre-hospital emergency ambulance service '
              'by dialing 1990. The retrieved offline '
              'Sri Lankan source states that the hotline '
              'is toll-free and the service covers all '
              'districts of the country.',
          context: boundedContext.context,
          sources: _uniqueSources(boundedContext.contextResults),
          fallbackUsed: false,
        );
      }

      // Critical emergency route must fail closed.
      return _safeFallback(
        sources: _uniqueSources(boundedContext.contextResults),
      );
    }

    // ----------------------------------------------------------
    // 4. Sanitize foreign localization before giving evidence
    //    to the local LLM.
    // ----------------------------------------------------------

    final sanitizedChunks = <RagRetrievalResult>[];

    for (final chunk in boundedContext.contextResults) {
      final sanitizedContent = localizationFilter.sanitizeEvidence(
        content: chunk.content,
        countryContext: chunk.countryContext,
      );

      if (sanitizedContent.trim().isEmpty) {
        continue;
      }

      sanitizedChunks.add(
        RagRetrievalResult(
          chunkId: chunk.chunkId,
          sourceId: chunk.sourceId,
          sourceChunkIndex: chunk.sourceChunkIndex,
          content: sanitizedContent,
          categories: chunk.categories,
          title: chunk.title,
          organization: chunk.organization,
          countryContext: chunk.countryContext,
        ),
      );
    }

    if (sanitizedChunks.isEmpty) {
      return _safeFallback(
        sources: _uniqueSources(boundedContext.contextResults),
      );
    }

    final sanitizedContext = sanitizedChunks
        .map((chunk) => chunk.content.trim())
        .where((content) => content.isNotEmpty)
        .join('\n\n');

    if (sanitizedContext.trim().isEmpty) {
      return _safeFallback(
        sources: _uniqueSources(boundedContext.contextResults),
      );
    }

    // ----------------------------------------------------------
    // 5. Normal RAG route. The model lifecycle is owned externally;
    //    an uninitialized or unavailable generator fails closed.
    // ----------------------------------------------------------

    final generator = localLlmGenerationService;
    if (generator == null) {
      return _groundedGenerationFallback(
        sources: _uniqueSources(sanitizedChunks),
      );
    }

    try {
      final generation = await generator.generateGroundedAnswer(
        question: question,
        context: sanitizedContext,
      );

      if (!generation.success || generation.answer.trim().isEmpty) {
        return _groundedGenerationFallback(
          sources: _uniqueSources(sanitizedChunks),
        );
      }

      return RagResponse(
        answerMode: RagAnswerMode.localLlmRag,
        answer: generation.answer.trim(),
        context: sanitizedContext,
        sources: _uniqueSources(sanitizedChunks),
        fallbackUsed: false,
      );
    } catch (_) {
      return _groundedGenerationFallback(
        sources: _uniqueSources(sanitizedChunks),
      );
    }
  }

  RagResponse _groundedGenerationFallback({
    required List<RagRetrievalResult> sources,
  }) {
    return RagResponse(
      answerMode: RagAnswerMode.safeFallback,
      answer:
          'Offline evidence was retrieved, but a grounded local answer '
          'could not be generated safely.',
      context: '',
      sources: sources,
      fallbackUsed: true,
    );
  }

  bool verifySriLanka1990Evidence(List<RagRetrievalResult> evidence) {
    for (final chunk in evidence) {
      // Only the authoritative Sri Lankan emergency source
      // currently approved for this deterministic route.
      if (chunk.sourceId != 'EXP_015') {
        continue;
      }

      final country = localizationFilter.normalizeCountryContext(
        chunk.countryContext,
      );

      if (country != 'Sri Lanka') {
        continue;
      }

      final content = chunk.content.toLowerCase();

      if (!RegExp(r'\b1990\b').hasMatch(content)) {
        continue;
      }

      final hasEmergencyContext =
          content.contains('ambulance') ||
          content.contains('pre-hospital') ||
          content.contains('emergency');

      if (!hasEmergencyContext) {
        continue;
      }

      return true;
    }

    return false;
  }

  List<RagRetrievalResult> _uniqueSources(List<RagRetrievalResult> chunks) {
    final sources = <String, RagRetrievalResult>{};

    for (final chunk in chunks) {
      sources.putIfAbsent(chunk.sourceId, () => chunk);
    }

    return List.unmodifiable(sources.values);
  }

  RagResponse _safeFallback({List<RagRetrievalResult> sources = const []}) {
    return RagResponse(
      answerMode: RagAnswerMode.safeFallback,
      answer:
          'I do not have enough verified offline evidence '
          'to provide this guidance safely.',
      context: '',
      sources: sources,
      fallbackUsed: true,
    );
  }
}
