"""System routing checks; no local LLM server is required."""
from research.rag.scripts.hybrid_rag import offline_hybrid_rag_answer, verify_sri_lanka_1990_evidence
from research.rag.scripts.retrieval import retrieve_offline_knowledge


EMERGENCY_QUESTION = "What ambulance service can I contact for a medical emergency in Sri Lanka?"


def test_verified_sri_lanka_emergency_route_uses_authoritative_evidence():
    results = retrieve_offline_knowledge(EMERGENCY_QUESTION, "sri_lanka_emergency", limit=4)
    assert verify_sri_lanka_1990_evidence(results)
    response = offline_hybrid_rag_answer(EMERGENCY_QUESTION, "sri_lanka_emergency", limit=4)
    assert response["answer_mode"] == "verified_deterministic"
    assert response["fallback_used"] is False
    assert "1990" in response["answer"]
    assert "EXP_015" in response["source_ids"]


def test_verified_route_does_not_activate_without_exp_015():
    results = retrieve_offline_knowledge(EMERGENCY_QUESTION, "sri_lanka_emergency", limit=4)
    assert not verify_sri_lanka_1990_evidence(results[results["source_id"] != "EXP_015"])


def test_successful_local_llm_response_normalizes_fallback_without_a_server(monkeypatch):
    import research.rag.scripts.hybrid_rag as hybrid_rag

    monkeypatch.setattr(
        hybrid_rag,
        "generate_with_local_server",
        lambda *args, **kwargs: {"success": True, "content": "Keep the hiker warm.", "time_seconds": 0},
    )
    response = hybrid_rag.offline_hybrid_rag_answer(
        "What should I do if a hiker shows signs of hypothermia?", "hypothermia", limit=4
    )
    assert response["success"] is True
    assert response["answer_mode"] == "local_llm_rag"
    assert response["fallback_used"] is False
