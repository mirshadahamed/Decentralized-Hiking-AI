"""System checks against the real, read-only offline knowledge database."""
import sqlite3

from research.rag.scripts.retrieval import DATABASE_PATH


def test_database_integrity_and_fts_coverage():
    with sqlite3.connect(DATABASE_PATH) as connection:
        assert connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 27
        assert connection.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0] == 1795
        assert connection.execute("SELECT COUNT(*) FROM knowledge_chunks_fts").fetchone()[0] == 1795
        assert connection.execute("""SELECT COUNT(*) FROM knowledge_chunks kc LEFT JOIN documents d ON d.source_id = kc.source_id WHERE d.source_id IS NULL""").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM knowledge_chunks WHERE source_id = 'EXP_016'").fetchone()[0] == 9
        assert connection.execute("SELECT COUNT(*) FROM knowledge_chunks WHERE source_id = 'EXP_017'").fetchone()[0] == 7
