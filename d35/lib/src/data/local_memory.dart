import 'dart:convert';
import 'dart:math';

import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

import '../models/models.dart';

class LocalMemory {
  LocalMemory({this.databaseName = 'snack_mind.db'});

  final String databaseName;
  Database? _database;

  Future<Database> get database async {
    if (_database != null) return _database!;
    _database = await openDatabase(
      p.join(await getDatabasesPath(), databaseName),
      version: 2,
      onCreate: (db, _) => _createSchema(db),
      onUpgrade: (db, oldVersion, _) async {
        if (oldVersion < 2) {
          await db.execute('''CREATE TABLE IF NOT EXISTS sessions(
            id TEXT PRIMARY KEY, status TEXT NOT NULL, case_state_json TEXT,
            started_at TEXT NOT NULL, finished_at TEXT)''');
          await db.execute(
            '''CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)''',
          );
          await db.execute('''CREATE TABLE IF NOT EXISTS memories(
            id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL,
            text TEXT NOT NULL, confidence REAL NOT NULL, status TEXT NOT NULL,
            source_episode_id INTEGER, evidence_count INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''');
          for (final statement in [
            'ALTER TABLE episodes ADD COLUMN data_json TEXT',
            'ALTER TABLE episodes ADD COLUMN retrieval_text TEXT',
          ]) {
            try {
              await db.execute(statement);
            } catch (_) {
              /* already exists */
            }
          }
        }
      },
    );
    return _database!;
  }

  Future<void> _createSchema(Database db) async {
    await db.execute('''CREATE TABLE sessions(
      id TEXT PRIMARY KEY, status TEXT NOT NULL, case_state_json TEXT,
      started_at TEXT NOT NULL, finished_at TEXT)''');
    await db.execute('''CREATE TABLE messages(
      id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
      role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)''');
    await db.execute('''CREATE TABLE episodes(
      id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT,
      summary TEXT NOT NULL, memory TEXT, vector TEXT, outcome TEXT,
      data_json TEXT, retrieval_text TEXT, created_at TEXT NOT NULL)''');
    await db.execute('''CREATE TABLE memories(
      id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL,
      text TEXT NOT NULL, confidence REAL NOT NULL, status TEXT NOT NULL,
      source_episode_id INTEGER, evidence_count INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''');
  }

  Future<void> startSession(CaseState state) async {
    final db = await database;
    await db.insert('sessions', {
      'id': state.id,
      'status': state.stage.name,
      'case_state_json': state.encode(),
      'started_at': DateTime.now().toUtc().toIso8601String(),
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<void> updateSession(CaseState state) async {
    final db = await database;
    await db.update(
      'sessions',
      {'status': state.stage.name, 'case_state_json': state.encode()},
      where: 'id = ?',
      whereArgs: [state.id],
    );
  }

  Future<void> failSession(String sessionId) async {
    final db = await database;
    await db.update(
      'sessions',
      {
        'status': 'failed',
        'finished_at': DateTime.now().toUtc().toIso8601String(),
      },
      where: 'id = ?',
      whereArgs: [sessionId],
    );
  }

  Future<void> saveMessage(String sessionId, ChatMessage message) async {
    final db = await database;
    await db.insert('messages', {
      'session_id': sessionId,
      'role': message.role,
      'content': message.text,
      'created_at': message.createdAt.toUtc().toIso8601String(),
    });
  }

  Future<int> saveDraft({
    required String sessionId,
    required MemoryDraft draft,
    required String outcome,
    List<double>? vector,
  }) async {
    final db = await database;
    return db.transaction((txn) async {
      final now = DateTime.now().toUtc().toIso8601String();
      final summary =
          draft.episode['summary'] as String? ?? draft.retrievalText;
      final episodeId = await txn.insert('episodes', {
        'session_id': sessionId,
        'summary': summary,
        'memory': draft.memoryCandidates
            .map((item) => item['text'])
            .join(' · '),
        'vector': vector == null ? null : jsonEncode(vector),
        'outcome': outcome,
        'data_json': jsonEncode(draft.episode),
        'retrieval_text': draft.retrievalText,
        'created_at': now,
      });
      for (final candidate in draft.memoryCandidates) {
        await txn.insert('memories', {
          'type': candidate['type'] ?? 'pattern',
          'text': candidate['text'] ?? '',
          'confidence': candidate['confidence'] ?? 0,
          'status': candidate['status'] ?? 'candidate',
          'source_episode_id': episodeId,
          'created_at': now,
          'updated_at': now,
        });
      }
      await txn.update(
        'sessions',
        {'status': SessionStage.completed.name, 'finished_at': now},
        where: 'id = ?',
        whereArgs: [sessionId],
      );
      return episodeId;
    });
  }

  Future<List<String>> relevant(List<double>? query, {int limit = 3}) async {
    final db = await database;
    final rows = await db.query(
      'episodes',
      orderBy: 'created_at DESC',
      limit: 60,
    );
    if (query == null) {
      // Без embedding нельзя доказать релевантность. Последний эпизод не должен
      // автоматически становиться контекстом новой ситуации.
      return const [];
    }
    final ranked = rows.map((row) {
      final raw = row['vector'] as String?;
      final vector = raw == null
          ? <double>[]
          : (jsonDecode(raw) as List)
                .map((value) => (value as num).toDouble())
                .toList();
      return (text: row['summary']! as String, score: _cosine(query, vector));
    }).toList()..sort((a, b) => b.score.compareTo(a.score));
    return ranked
        .where((item) => item.score >= .55)
        .take(limit)
        .map((item) => item.text)
        .toList();
  }

  Future<List<Map<String, Object?>>> recent({int limit = 20}) async {
    final db = await database;
    return db.query('episodes', orderBy: 'created_at DESC', limit: limit);
  }

  double _cosine(List<double> a, List<double> b) {
    if (a.isEmpty || a.length != b.length) return 0;
    var dot = 0.0, normA = 0.0, normB = 0.0;
    for (var i = 0; i < a.length; i++) {
      dot += a[i] * b[i];
      normA += a[i] * a[i];
      normB += b[i] * b[i];
    }
    final denominator = sqrt(normA) * sqrt(normB);
    return denominator == 0 ? 0 : dot / denominator;
  }
}
