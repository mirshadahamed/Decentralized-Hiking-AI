"""Existing local llama-server interaction and response guardrails."""
import json
import re
import time
import urllib.request


LLAMA_SERVER_URL = "http://127.0.0.1:8080"
SAFE_FALLBACK = "The offline knowledge base does not contain enough information to answer this safely."


def build_localized_grounded_prompt(question, context):
    return f"""You are an offline hiking safety assistant intended for use in Sri Lanka.

Answer the QUESTION using only the AUTHORITATIVE CONTEXT below. Do not present foreign country-specific services, emergency numbers, organizations, websites, map products, or geographic instructions as recommendations for Sri Lanka. Do not invent emergency telephone numbers, mention source IDs, diagnose, or echo this prompt. Use exactly INSUFFICIENT_OFFLINE_EVIDENCE only when the retrieved context contains no useful evidence for answering the question safely.

AUTHORITATIVE CONTEXT:
{context}

QUESTION:
{question}

FINAL ANSWER:"""


def generate_with_local_server(prompt, max_tokens=180, temperature=0.0, timeout_seconds=60):
    request = urllib.request.Request(LLAMA_SERVER_URL + "/completion", data=json.dumps({"prompt": prompt, "n_predict": max_tokens, "temperature": temperature, "stream": False}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"success": True, "time_seconds": time.perf_counter() - started, "content": payload.get("content", "").strip(), "response": payload}
    except Exception as error:
        return {"success": False, "time_seconds": time.perf_counter() - started, "content": "", "error": repr(error)}


def apply_output_guardrails(answer, retrieved_source_ids, category):
    cleaned = re.sub(r"<think>.*?</think>", "", answer.strip(), flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"\b(?:SRC|EXP)_\d{3}\b", "[retrieved source]", cleaned, flags=re.IGNORECASE)
    foreign_numbers = []
    if category != "sri_lanka_emergency":
        for number in ("111", "911", "999"):
            if re.search(rf"\b{number}\b", cleaned):
                foreign_numbers.append(number)
                cleaned = re.sub(rf"\b{number}\b", "[foreign emergency number omitted]", cleaned)
        cleaned = re.sub(
            r"(?:\*{1,3}\s*)?\b(?:call|dial)\s+"
            r"\[foreign emergency number omitted\]"
            r"(?:\s+(?:immediately|now))?[\.,;:]?(?:\s*\*{1,3})?",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return {"answer": cleaned, "foreign_numbers_found": foreign_numbers, "retrieved_source_ids": retrieved_source_ids}
