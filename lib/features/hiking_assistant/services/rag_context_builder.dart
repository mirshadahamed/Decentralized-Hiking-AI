import '../models/rag_retrieval_result.dart';
import 'offline_knowledge_database.dart';

class RagContextResult {
  final List<RagRetrievalResult> seedResults;
  final List<RagRetrievalResult> contextResults;
  final String context;
  final int wordCount;

  const RagContextResult({
    required this.seedResults,
    required this.contextResults,
    required this.context,
    required this.wordCount,
  });
}

class RagContextBuilder {
  final OfflineKnowledgeDatabase database;

  const RagContextBuilder({required this.database});

  Future<RagContextResult> buildBoundedContext({
    required List<RagRetrievalResult> seedResults,
    int neighborDistance = 1,
    int maxWords = 1200,
  }) async {
    if (seedResults.isEmpty) {
      return const RagContextResult(
        seedResults: [],
        contextResults: [],
        context: '',
        wordCount: 0,
      );
    }

    final selected = <String, RagRetrievalResult>{};
    var totalWords = 0;

    // ----------------------------------------------------------
    // 1. Preserve all original FTS seed chunks first.
    // ----------------------------------------------------------

    for (final seed in seedResults) {
      if (selected.containsKey(seed.chunkId)) {
        continue;
      }

      final words = seed.wordCount;

      if (totalWords + words > maxWords) {
        continue;
      }

      selected[seed.chunkId] = seed;
      totalWords += words;
    }

    // ----------------------------------------------------------
    // 2. Group FTS seeds by source while preserving the order in
    //    which each source first appeared in the FTS ranking.
    //
    // This prevents one source with multiple top-k chunks from
    // consuming several continuity slots before another source
    // gets an opportunity to contribute adjacent evidence.
    // ----------------------------------------------------------

    final seedsBySource = <String, List<RagRetrievalResult>>{};

    final sourceOrder = <String>[];

    for (final seed in seedResults) {
      if (!seedsBySource.containsKey(seed.sourceId)) {
        seedsBySource[seed.sourceId] = <RagRetrievalResult>[];

        sourceOrder.add(seed.sourceId);
      }

      seedsBySource[seed.sourceId]!.add(seed);
    }

    // ----------------------------------------------------------
    // 3. Build adjacent candidates for each unique source.
    // ----------------------------------------------------------

    final candidatesBySource = <String, List<RagRetrievalResult>>{};

    for (final sourceId in sourceOrder) {
      final sourceSeeds = seedsBySource[sourceId] ?? const [];

      final sourceCandidates = <String, RagRetrievalResult>{};

      for (final seed in sourceSeeds) {
        final neighbors = await database.getAdjacentChunks(
          sourceId: seed.sourceId,
          sourceChunkIndex: seed.sourceChunkIndex,
          distance: neighborDistance,
        );

        for (final neighbor in neighbors) {
          if (selected.containsKey(neighbor.chunkId)) {
            continue;
          }

          sourceCandidates.putIfAbsent(neighbor.chunkId, () => neighbor);
        }
      }

      final candidates = sourceCandidates.values.toList();

      candidates.sort((a, b) {
        final aDistance = _nearestSeedDistance(a, sourceSeeds);

        final bDistance = _nearestSeedDistance(b, sourceSeeds);

        final distanceComparison = aDistance.compareTo(bDistance);

        if (distanceComparison != 0) {
          return distanceComparison;
        }

        final aFollowing = _isFollowingAnySeed(a, sourceSeeds);

        final bFollowing = _isFollowingAnySeed(b, sourceSeeds);

        // Prefer continuation after a seed when distance is tied.
        if (aFollowing != bFollowing) {
          return aFollowing ? -1 : 1;
        }

        return a.sourceChunkIndex.compareTo(b.sourceChunkIndex);
      });

      candidatesBySource[sourceId] = candidates;
    }

    // ----------------------------------------------------------
    // 4. Source-balanced round-robin expansion.
    //
    // Each unique source gets one opportunity before a source
    // receives another adjacent chunk.
    // ----------------------------------------------------------

    var round = 0;
    var candidatesRemaining = true;

    while (candidatesRemaining) {
      candidatesRemaining = false;

      for (final sourceId in sourceOrder) {
        final candidates = candidatesBySource[sourceId] ?? const [];

        if (round >= candidates.length) {
          continue;
        }

        candidatesRemaining = true;

        final candidate = candidates[round];

        if (selected.containsKey(candidate.chunkId)) {
          continue;
        }

        final words = candidate.wordCount;

        if (totalWords + words > maxWords) {
          continue;
        }

        selected[candidate.chunkId] = candidate;
        totalWords += words;
      }

      round++;
    }

    // ----------------------------------------------------------
    // 5. Present selected chunks in source/document order.
    // ----------------------------------------------------------

    final contextResults = selected.values.toList()
      ..sort((a, b) {
        final sourceComparison = a.sourceId.compareTo(b.sourceId);

        if (sourceComparison != 0) {
          return sourceComparison;
        }

        return a.sourceChunkIndex.compareTo(b.sourceChunkIndex);
      });

    final context = contextResults
        .map((result) => result.content.trim())
        .where((content) => content.isNotEmpty)
        .join('\n\n');

    return RagContextResult(
      seedResults: List.unmodifiable(seedResults),
      contextResults: List.unmodifiable(contextResults),
      context: context,
      wordCount: totalWords,
    );
  }

  int _nearestSeedDistance(
    RagRetrievalResult candidate,
    List<RagRetrievalResult> seeds,
  ) {
    var minimumDistance = 1 << 30;

    for (final seed in seeds) {
      final distance = (candidate.sourceChunkIndex - seed.sourceChunkIndex)
          .abs();

      if (distance < minimumDistance) {
        minimumDistance = distance;
      }
    }

    return minimumDistance;
  }

  bool _isFollowingAnySeed(
    RagRetrievalResult candidate,
    List<RagRetrievalResult> seeds,
  ) {
    for (final seed in seeds) {
      if (candidate.sourceChunkIndex == seed.sourceChunkIndex + 1) {
        return true;
      }
    }

    return false;
  }
}
