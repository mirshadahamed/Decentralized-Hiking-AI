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

  Future<Database> get database async {
    if (_database != null) {
      return _database!;
    }

    _database = await _openDatabase();
    return _database!;
  }

  Future<Database> _openDatabase() async {
    final databasesPath = await getDatabasesPath();

    final databasePath = p.join(databasesPath, _databaseName);

    final file = File(databasePath);

    if (!await file.exists()) {
      await Directory(p.dirname(databasePath)).create(recursive: true);

      final data = await rootBundle.load(_assetPath);

      final bytes = data.buffer.asUint8List(
        data.offsetInBytes,
        data.lengthInBytes,
      );

      await file.writeAsBytes(bytes, flush: true);
    }

    return openDatabase(databasePath, readOnly: true);
  }

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

  Future<List<RagRetrievalResult>> retrieve({
    required String question,
    required String category,
    int limit = 4,
  }) async {
    final db = await database;

    final ftsQuery = _buildFtsQuery(question);

    if (ftsQuery.isEmpty) {
      return [];
    }

    final rows = await db.rawQuery(
      '''
      SELECT
        kc.chunk_id,
        kc.source_id,
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

  String _buildFtsQuery(String question) {
    final words = question
        .toLowerCase()
        .replaceAll(RegExp(r'[^a-z0-9\s]'), ' ')
        .split(RegExp(r'\s+'))
        .where((word) => word.length >= 3)
        .toSet()
        .toList();

    if (words.isEmpty) {
      return '';
    }

    return words.map((word) => '"$word"').join(' OR ');
  }

  Future<void> close() async {
    await _database?.close();
    _database = null;
  }
}
