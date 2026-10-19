"""Pure unit tests for prompt and output-safety behavior."""
from research.rag.scripts.generation import apply_output_guardrails, build_localized_grounded_prompt


def test_prompt_carries_question_and_context():
    prompt = build_localized_grounded_prompt("Question?", "Authoritative evidence.")
    assert "Question?" in prompt
    assert "Authoritative evidence." in prompt


def test_guardrails_remove_thinking_source_ids_and_foreign_numbers():
    guarded = apply_output_guardrails("<think>hidden</think> EXP_017 **Call 999** immediately. Call 111.", ["EXP_017"], "allergic_reaction")
    assert "hidden" not in guarded["answer"]
    assert "EXP_017" not in guarded["answer"]
    assert set(guarded["foreign_numbers_found"]) == {"999", "111"}
    assert "999" not in guarded["answer"]
    assert "111" not in guarded["answer"]
    assert "call [foreign emergency number omitted]" not in guarded["answer"].lower()
    assert "****" not in guarded["answer"]


def test_sri_lanka_category_does_not_remove_1990():
    guarded = apply_output_guardrails("Dial 1990.", ["EXP_015"], "sri_lanka_emergency")
    assert guarded["answer"] == "Dial 1990."
