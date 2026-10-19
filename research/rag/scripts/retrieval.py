"""SQLite FTS5 retrieval for the offline hiking knowledge base."""
from pathlib import Path
import re
import sqlite3

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATABASE_PATH = PROJECT_ROOT / "research" / "rag" / "database" / "offline_hiking_knowledge.db"


def build_fts_query(question):
    """Build the notebook's deterministic OR query from meaningful terms."""
    terms = [term for term in re.findall(r"[A-Za-z0-9]+", question.lower()) if len(term) >= 3]
    return " OR ".join(dict.fromkeys(terms))


def retrieve_offline_knowledge(question, category=None, limit=4):
    """Retrieve top FTS5 chunks, optionally constrained to a RAG category."""
    fts_query = build_fts_query(question)
    if not fts_query:
        return pd.DataFrame()
    category_filter = "" if category is None else "AND (',' || REPLACE(kc.categories, ' ', '') || ',') LIKE ?"
    sql = f"""
        SELECT kc.chunk_id, kc.source_id, d.organization, d.title, d.country_context,
               kc.categories, kc.content, kc.word_count, kc.source_chunk_index,
               bm25(knowledge_chunks_fts) AS rank
        FROM knowledge_chunks_fts
        JOIN knowledge_chunks kc ON knowledge_chunks_fts.chunk_id = kc.chunk_id
        JOIN documents d ON d.source_id = kc.source_id
        WHERE knowledge_chunks_fts MATCH ? {category_filter}
        ORDER BY rank
        LIMIT ?
    """
    params = [fts_query] + ([f"%,{category},%"] if category is not None else []) + [limit]
    with sqlite3.connect(DATABASE_PATH) as connection:
        return pd.read_sql_query(sql, connection, params=params)
