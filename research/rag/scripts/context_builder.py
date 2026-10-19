"""Country-aware bounded context construction for local RAG generation."""
import re
import sqlite3

import pandas as pd

from .retrieval import DATABASE_PATH


FOREIGN_EMERGENCY_NUMBERS = {"111", "911", "999"}
FOREIGN_MARKERS = {
    "united kingdom": ("united kingdom", "nhs", "met office", "mountain weather information service"),
    "united states": ("united states", "national weather service", "nps.gov"),
    "new zealand": ("new zealand", "linz", "topo50", "doc visitor", "mountain safety council"),
}


def normalize_country_context(country_context):
    if country_context is None or pd.isna(country_context):
        return "not specified"
    country = str(country_context).strip().lower()
    if not country or "not specified" in country:
        return "not specified"
    if "sri lanka" in country: return "sri lanka"
    if "united kingdom" in country or country == "uk" or country.startswith("uk "): return "united kingdom"
    if "united states" in country or country in {"us", "usa"}: return "united states"
    if "new zealand" in country: return "new zealand"
    if "international" in country: return "international"
    return country


def filter_foreign_evidence(content, country_context):
    country = normalize_country_context(country_context)
    if country in {"sri lanka", "international", "not specified"}:
        return str(content).strip()
    retained = []
    for sentence in re.split(r"(?<=[.!?])\s+", str(content)):
        lowered = sentence.lower()
        if sentence.strip() and not any(re.search(rf"\b{number}\b", sentence) for number in FOREIGN_EMERGENCY_NUMBERS) and not any(marker in lowered for marker in FOREIGN_MARKERS.get(country, ())):
            retained.append(sentence.strip())
    return " ".join(retained)


def expand_with_adjacent_chunks(retrieval_results, neighbor_distance=1):
    """Add immediate same-document neighbors while retaining primary FTS seeds."""
    if retrieval_results.empty:
        return retrieval_results.copy()
    seed_ids = retrieval_results["chunk_id"].drop_duplicates().tolist()
    with sqlite3.connect(DATABASE_PATH) as connection:
        seeds = pd.read_sql_query("SELECT chunk_id, source_id, source_chunk_index FROM knowledge_chunks WHERE chunk_id IN (%s)" % ",".join("?" * len(seed_ids)), connection, params=seed_ids)
        parts = []
        for source_id, group in seeds.groupby("source_id"):
            wanted = sorted({int(index) + offset for index in group["source_chunk_index"] for offset in range(-neighbor_distance, neighbor_distance + 1) if int(index) + offset >= 0})
            parts.append(pd.read_sql_query("""SELECT kc.chunk_id, kc.source_id, d.organization, d.title, d.country_context, kc.categories, kc.content, kc.word_count, kc.source_chunk_index FROM knowledge_chunks kc JOIN documents d ON d.source_id = kc.source_id WHERE kc.source_id = ? AND kc.source_chunk_index IN (%s) ORDER BY kc.source_chunk_index""" % ",".join("?" * len(wanted)), connection, params=[source_id, *wanted]))
    return pd.concat(parts, ignore_index=True).drop_duplicates("chunk_id").sort_values(["source_id", "source_chunk_index"]).reset_index(drop=True)


def prepare_bounded_localized_context(retrieval_results, neighbor_distance=1, max_words=1200):
    """Preserve seed chunks first, then add nearest neighbors within the word budget."""
    expanded = expand_with_adjacent_chunks(retrieval_results, neighbor_distance)
    if expanded.empty:
        return {"bounded_results": expanded, "localized_results": expanded, "localized_context": ""}
    seed_ids = set(retrieval_results["chunk_id"])
    ranks = dict(zip(retrieval_results["chunk_id"], retrieval_results["rank"]))
    expanded["is_seed"] = expanded["chunk_id"].isin(seed_ids)
    expanded["retrieval_rank"] = expanded["chunk_id"].map(ranks)
    chosen, total = [], 0
    for _, row in expanded[expanded["is_seed"]].sort_values("retrieval_rank").iterrows():
        if total + int(row["word_count"]) <= max_words:
            chosen.append(row["chunk_id"]); total += int(row["word_count"])
    seed_positions = expanded[expanded["is_seed"]][["source_id", "source_chunk_index"]]
    candidates = expanded[~expanded["is_seed"]].copy()
    if not candidates.empty:
        candidates["seed_distance"] = candidates.apply(lambda row: min(abs(int(row["source_chunk_index"]) - int(index)) for index in seed_positions[seed_positions["source_id"] == row["source_id"]]["source_chunk_index"]), axis=1)
        for _, row in candidates.sort_values(["seed_distance", "source_id", "source_chunk_index"]).iterrows():
            if total + int(row["word_count"]) <= max_words:
                chosen.append(row["chunk_id"]); total += int(row["word_count"])
    bounded = expanded[expanded["chunk_id"].isin(chosen)].sort_values(["source_id", "source_chunk_index"]).reset_index(drop=True)
    localized = bounded.copy()
    localized["content"] = localized.apply(lambda row: filter_foreign_evidence(row["content"], row["country_context"]), axis=1)
    localized = localized[localized["content"].str.strip().astype(bool)].reset_index(drop=True)
    return {"bounded_results": bounded, "localized_results": localized, "localized_context": "\n\n".join(localized["content"])}
