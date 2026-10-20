import 'dart:io';

import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import '../models/rag_retrieval_result.dart';

class OfflineKnowledgeDatabase {
  static const String _assetPath =
      'assets/knowledge/offline_hiking_knowledge.db';

  static const String _databaseName = 'offline_hiking_knowledge.db';

  Database? _database;

  // null: not tested; true: supported; false: unavailable for this database
  // instance. Android SQLite builds can open the database but omit FTS5.
  bool? _fts5Available;

  // ------------------------------------------------------------
  // DATABASE INSTANCE
  // ------------------------------------------------------------

  Future<Database> get database async {
    if (_database != null) {
      return _database!;
    }

    _database = await _openDatabase();
    return _database!;
  }

  // ------------------------------------------------------------
  // OPEN OFFLINE DATABASE
  // ------------------------------------------------------------

  Future<Database> _openDatabase() async {
    final databasesPath = await getDatabasesPath();

    final databasePath = p.join(databasesPath, _databaseName);

    final file = File(databasePath);

    // Copy the bundled SQLite database into the application's
    // database directory the first time it is used.
    if (!await file.exists()) {
      await Directory(p.dirname(databasePath)).create(recursive: true);

      final data = await rootBundle.load(_assetPath);

      final bytes = data.buffer.asUint8List(
        data.offsetInBytes,
        data.lengthInBytes,
      );

      await file.writeAsBytes(bytes, flush: true);
    }

    // Knowledge database is read-only.
    return openDatabase(databasePath, readOnly: true);
  }

  // ------------------------------------------------------------
  // DATABASE VALIDATION
  // ------------------------------------------------------------

  Future<int> getDocumentCount() async {
    final db = await database;

    final result = await db.rawQuery('SELECT COUNT(*) AS count FROM documents');

    return Sqflite.firstIntValue(result) ?? 0;
  }

  Future<int> getChunkCount() async {
    final db = await database;

    final result = await db.rawQuery(
      'SELECT COUNT(*) AS count FROM knowledge_chunks',
    );

    return Sqflite.firstIntValue(result) ?? 0;
  }

  Future<int> getFtsChunkCount() async {
    final db = await database;

    final result = await db.rawQuery(
      'SELECT COUNT(*) AS count FROM knowledge_chunks_fts',
    );

    return Sqflite.firstIntValue(result) ?? 0;
  }

  // ------------------------------------------------------------
  // PRIMARY FTS5 RETRIEVAL
  // ------------------------------------------------------------

  Future<List<RagRetrievalResult>> retrieve({
    required String question,
    required String category,
    int limit = 4,
  }) async {
    final queryWords = _normalizeQueryWords(question);

    if (queryWords.isEmpty) {
      return [];
    }

    final db = await database;

    if (_fts5Available != false) {
      try {
        final results = await _retrieveWithFts5(
          db: db,
          queryWords: queryWords,
          category: category,
          limit: limit * 4,
        );
        _fts5Available = true;
        return _preferActionableResults(results, question).take(limit).toList();
      } on DatabaseException catch (error) {
        if (!_isFts5UnavailableError(error)) {
          rethrow;
        }

        _fts5Available = false;
      }
    }

    // Adaptive SQLite retrieval fallback. This is portable and fully offline,
    // but its deterministic Dart ranking is not equivalent to FTS5 BM25.
    final results = await _retrievePortable(
      db: db,
      queryWords: queryWords,
      category: category,
      limit: limit * 4,
    );
    return _preferActionableResults(results, question).take(limit).toList();
  }

  List<RagRetrievalResult> _preferActionableResults(
    List<RagRetrievalResult> results,
    String question,
  ) {
    final asksForAction = RegExp(
      r'\b(what\s+(should|can)\s+(i|we)\s+do|what\s+to\s+do|help\s+me)\b',
      caseSensitive: false,
    ).hasMatch(question);
    if (!asksForAction) return results;

    final ranked = results.toList()
      ..sort(
        (left, right) => _actionScore(right).compareTo(_actionScore(left)),
      );
    return ranked;
  }

  int _actionScore(RagRetrievalResult result) {
    final text = '${result.title} ${result.content}'.toLowerCase();
    const signals = [
      'first aid',
      'what to do',
      'immediate',
      'keep still',
      'avoid moving',
      'do not',
      'call',
    ];
    return signals.where(text.contains).length;
  }

  /// Broad offline evidence retrieval used only for category routing. It uses
  /// the same FTS5 capability detection and Android portable fallback as the
  /// final category-aware retrieval path.
  Future<List<RagRetrievalResult>> retrieveRoutingCandidates({
    required String question,
    int limit = 48,
  }) async {
    final queryWords = _normalizeQueryWords(question);
    if (queryWords.isEmpty) return [];
    final db = await database;

    if (_fts5Available != false) {
      try {
        final rows = await db.rawQuery(
          '''
          SELECT kc.chunk_id, kc.source_id, kc.source_chunk_index, kc.content,
                 kc.categories, d.title, d.organization, d.country_context
          FROM knowledge_chunks_fts
          JOIN knowledge_chunks kc ON kc.chunk_id = knowledge_chunks_fts.chunk_id
          JOIN documents d ON d.source_id = kc.source_id
          WHERE knowledge_chunks_fts MATCH ?
          ORDER BY bm25(knowledge_chunks_fts)
          LIMIT ?
          ''',
          [_buildFtsQuery(queryWords), limit],
        );
        _fts5Available = true;
        return rows.map(RagRetrievalResult.fromMap).toList();
      } on DatabaseException catch (error) {
        if (!_isFts5UnavailableError(error)) rethrow;
        _fts5Available = false;
      }
    }

    final conditions = List.filled(
      queryWords.length,
      'LOWER(kc.content) LIKE ? OR LOWER(d.title) LIKE ?',
    ).join(' OR ');
    final args = <Object?>[];
    for (final word in queryWords) {
      args
        ..add('%$word%')
        ..add('%$word%');
    }
    final rows = await db.rawQuery('''
      SELECT kc.chunk_id, kc.source_id, kc.source_chunk_index, kc.content,
             kc.categories, d.title, d.organization, d.country_context
      FROM knowledge_chunks kc JOIN documents d ON d.source_id = kc.source_id
      WHERE $conditions
      ''', args);
    final results = rows.map(RagRetrievalResult.fromMap).toList()
      ..sort(
        (a, b) => _portableScore(
          b,
          queryWords,
        ).compareTo(_portableScore(a, queryWords)),
      );
    return results.take(limit).toList();
  }

  Future<List<RagRetrievalResult>> _retrieveWithFts5({
    required Database db,
    required List<String> queryWords,
    required String category,
    required int limit,
  }) async {
    final ftsQuery = _buildFtsQuery(queryWords);

    final rows = await db.rawQuery(
      '''
      SELECT
        kc.chunk_id,
        kc.source_id,
        kc.source_chunk_index,
        kc.content,
        kc.categories,
        d.title,
        d.organization,
        d.country_context
      FROM knowledge_chunks_fts
      JOIN knowledge_chunks kc
        ON kc.chunk_id = knowledge_chunks_fts.chunk_id
      JOIN documents d
        ON d.source_id = kc.source_id
      WHERE knowledge_chunks_fts MATCH ?
        AND kc.categories LIKE ?
      ORDER BY bm25(knowledge_chunks_fts)
      LIMIT ?
      ''',
      [ftsQuery, '%$category%', limit],
    );

    return rows.map(RagRetrievalResult.fromMap).toList();
  }

  Future<List<RagRetrievalResult>> _retrievePortable({
    required Database db,
    required List<String> queryWords,
    required String category,
    required int limit,
  }) async {
    final wordConditions = List.filled(
      queryWords.length,
      'LOWER(kc.content) LIKE ?',
    ).join(' OR ');

    final rows = await db.rawQuery(
      '''
      SELECT
        kc.chunk_id,
        kc.source_id,
        kc.source_chunk_index,
        kc.content,
        kc.categories,
        d.title,
        d.organization,
        d.country_context
      FROM knowledge_chunks kc
      JOIN documents d
        ON d.source_id = kc.source_id
      WHERE kc.categories LIKE ?
        AND ($wordConditions)
      ''',
      ['%$category%', ...queryWords.map((word) => '%$word%')],
    );

    final candidates = rows.map(RagRetrievalResult.fromMap).toList();

    candidates.sort((left, right) {
      final scoreComparison = _portableScore(
        right,
        queryWords,
      ).compareTo(_portableScore(left, queryWords));

      if (scoreComparison != 0) {
        return scoreComparison;
      }

      final sourceComparison = left.sourceId.compareTo(right.sourceId);

      if (sourceComparison != 0) {
        return sourceComparison;
      }

      return left.sourceChunkIndex.compareTo(right.sourceChunkIndex);
    });

    return candidates.take(limit).toList();
  }

  int _portableScore(RagRetrievalResult result, List<String> queryWords) {
    final title = result.title.toLowerCase();
    final content = result.content.toLowerCase();
    var score = 0;

    for (final word in queryWords) {
      if (title.contains(word)) {
        score += 4;
      }

      final firstMatch = content.indexOf(word);

      if (firstMatch == -1) {
        continue;
      }

      score += 2;
      var nextStart = firstMatch + word.length;

      while (nextStart <= content.length - word.length) {
        final nextMatch = content.indexOf(word, nextStart);

        if (nextMatch == -1) {
          break;
        }

        score += 1;
        nextStart = nextMatch + word.length;
      }
    }

    return score;
  }

  // ------------------------------------------------------------
  // ADJACENT-CHUNK RETRIEVAL
  // ------------------------------------------------------------
  //
  // Used after the primary FTS5 retrieval.
  //
  // Example:
  //
  // FTS retrieves chunk index 10.
  //
  // distance = 1
  //
  // Flutter can retrieve:
  //     9
  //    10
  //    11
  //
  // This helps recover important information split across
  // neighboring chunks while keeping the primary FTS retrieval
  // unchanged.
  // ------------------------------------------------------------

  Future<List<RagRetrievalResult>> getAdjacentChunks({
    required String sourceId,
    required int sourceChunkIndex,
    int distance = 1,
  }) async {
    final db = await database;

    final minimumIndex = sourceChunkIndex - distance;

    final maximumIndex = sourceChunkIndex + distance;

    final rows = await db.rawQuery(
      '''
      SELECT
        kc.chunk_id,
        kc.source_id,
        kc.source_chunk_index,
        kc.content,
        kc.categories,
        d.title,
        d.organization,
        d.country_context
      FROM knowledge_chunks kc
      JOIN documents d
        ON d.source_id = kc.source_id
      WHERE kc.source_id = ?
        AND kc.source_chunk_index BETWEEN ? AND ?
      ORDER BY kc.source_chunk_index
      ''',
      [sourceId, minimumIndex, maximumIndex],
    );

    return rows.map(RagRetrievalResult.fromMap).toList();
  }

  // ------------------------------------------------------------
  // QUERY NORMALIZATION AND FTS5 CAPABILITY
  // ------------------------------------------------------------

  List<String> _normalizeQueryWords(String question) {
    final words = question
        .toLowerCase()
        .replaceAll(RegExp(r'[^a-z0-9\s-]'), ' ')
        .split(RegExp(r'\s+'))
        .map((word) => word.trim())
        .where((word) => word.length >= 3);

    final uniqueWords = <String>[];
    final seenWords = <String>{};

    for (final word in words) {
      if (seenWords.add(word)) {
        uniqueWords.add(word);
      }
    }

    return uniqueWords;
  }

  String _buildFtsQuery(List<String> words) {
    return words.map((word) => '"$word"').join(' OR ');
  }

  bool _isFts5UnavailableError(DatabaseException error) {
    return error.toString().toLowerCase().contains('no such module: fts5');
  }

  // ------------------------------------------------------------
  // CLOSE DATABASE
  // ------------------------------------------------------------

  Future<void> close() async {
    await _database?.close();
    _database = null;
    _fts5Available = null;
  }
}
