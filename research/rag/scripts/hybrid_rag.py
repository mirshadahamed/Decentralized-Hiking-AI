"""Evidence-gated hybrid routing for offline hiking RAG."""
import re

from .context_builder import prepare_bounded_localized_context
from .generation import SAFE_FALLBACK, apply_output_guardrails, build_localized_grounded_prompt, generate_with_local_server
from .retrieval import retrieve_offline_knowledge


def verify_sri_lanka_1990_evidence(results):
    for _, row in results.iterrows():
        content = str(row["content"]).lower()
        if str(row["source_id"]) == "EXP_015" and str(row["country_context"]).strip().lower() == "sri lanka" and re.search(r"\b1990\b", content) and any(term in content for term in ("ambulance", "pre hospital", "pre-hospital")):
            return True
    return False


def offline_hybrid_rag_answer(question, category, limit=4):
    results = retrieve_offline_knowledge(question, category, limit)
    if results.empty:
        return {"success": False, "answer": SAFE_FALLBACK, "final_output": SAFE_FALLBACK, "answer_mode": "fallback", "source_ids": [], "retrieved_chunks": 0, "fallback_used": True}
    source_ids = results["source_id"].drop_duplicates().tolist()
    if category == "sri_lanka_emergency" and verify_sri_lanka_1990_evidence(results):
        answer = "For a medical emergency in Sri Lanka, you can request the 1990 Suwa Seriya pre-hospital emergency ambulance service by dialing 1990."
        return {"success": True, "answer": answer, "final_output": answer + "\n\nSources: " + ", ".join(source_ids), "answer_mode": "verified_deterministic", "source_ids": source_ids, "retrieved_chunks": len(results), "fallback_used": False}
    prepared = prepare_bounded_localized_context(results)
    if not prepared["localized_context"]:
        return {"success": False, "answer": SAFE_FALLBACK, "final_output": SAFE_FALLBACK + "\n\nSources: " + ", ".join(source_ids), "answer_mode": "fallback", "source_ids": source_ids, "retrieved_chunks": len(results), "fallback_used": True}
    generation = generate_with_local_server(build_localized_grounded_prompt(question, prepared["localized_context"]), max_tokens=180, temperature=0.0, timeout_seconds=60)
    if not generation["success"]:
        return {"success": False, "answer": "Local generation failed.", "final_output": "Local generation failed.", "answer_mode": "local_llm_rag", "source_ids": source_ids, "retrieved_chunks": len(results), "fallback_used": False}
    cleaned = re.sub(r"<think>.*?</think>", "", generation["content"], flags=re.IGNORECASE | re.DOTALL).strip()
    fallback_used = "INSUFFICIENT_OFFLINE_EVIDENCE" in cleaned
    guarded = apply_output_guardrails(SAFE_FALLBACK if fallback_used else cleaned, source_ids, category)
    return {"success": bool(guarded["answer"].strip()) and not fallback_used, "answer": guarded["answer"], "final_output": guarded["answer"] + "\n\nSources: " + ", ".join(source_ids), "answer_mode": "local_llm_rag", "source_ids": source_ids, "retrieved_chunks": len(results), "foreign_numbers_detected": guarded["foreign_numbers_found"], "fallback_used": fallback_used}
