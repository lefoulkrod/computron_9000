"""LLM call helpers for compaction evaluation."""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from sdk.providers._ollama import OllamaProvider

from ._prompts import (
    FACT_EXTRACTION_PROMPT,
    FACT_MATCHING_PROMPT,
    JUDGE_PROMPT,
    PROBE_ANSWER_PROMPT,
    PROBE_GENERATION_PROMPT,
)
from ._serialization import serialize_messages

logger = logging.getLogger(__name__)

_CALL_TIMEOUT = 180.0


def _parse_json(text: str) -> Any:
    """Parse JSON from LLM output, stripping markdown fences if present."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


async def _call_llm(
    provider: OllamaProvider,
    model: str,
    system_prompt: str,
    user_content: str,
    options: dict[str, Any] | None = None,
) -> tuple[str, float]:
    """Call the LLM and return (response_text, elapsed_seconds)."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    t0 = time.monotonic()
    response = await provider.chat(
        model=model,
        messages=messages,
        options=options,
        think=False,
    )
    elapsed = time.monotonic() - t0
    return response.message.content or "", elapsed


async def extract_facts(
    provider: OllamaProvider,
    model: str,
    input_messages: list[dict[str, Any]],
    summary_text: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract facts from source messages and check which survived in summary."""
    conversation_text = serialize_messages(input_messages)

    # Step 1: Extract facts
    prompt = FACT_EXTRACTION_PROMPT.format(conversation_text=conversation_text)
    raw_facts, facts_elapsed = await _call_llm(
        provider, model, "You extract facts from conversations.", prompt, options,
    )
    try:
        facts = _parse_json(raw_facts)
    except (json.JSONDecodeError, ValueError):
        return {
            "error": "Failed to parse facts JSON",
            "raw_response": raw_facts,
            "elapsed_seconds": facts_elapsed,
        }

    if not facts:
        return {"facts": [], "elapsed_seconds": facts_elapsed}

    # Step 2: Check which facts are in the summary
    facts_json = json.dumps([f["text"] for f in facts], indent=2)
    match_prompt = FACT_MATCHING_PROMPT.format(
        summary_text=summary_text,
        facts_json=facts_json,
    )
    raw_matches, match_elapsed = await _call_llm(
        provider, model, "You check fact preservation.", match_prompt, options,
    )
    try:
        matches = _parse_json(raw_matches)
    except (json.JSONDecodeError, ValueError):
        # Return facts without match info
        matches = [None] * len(facts)

    # Combine
    for i, fact in enumerate(facts):
        fact["preserved"] = matches[i] if i < len(matches) else None

    return {
        "facts": facts,
        "elapsed_seconds": round(facts_elapsed + match_elapsed, 1),
    }


async def judge_summary(
    provider: OllamaProvider,
    model: str,
    input_messages: list[dict[str, Any]],
    summary_text: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """LLM-as-judge scoring of a summary."""
    conversation_text = serialize_messages(input_messages)
    prompt = JUDGE_PROMPT.format(
        conversation_text=conversation_text,
        summary_text=summary_text,
    )
    raw, elapsed = await _call_llm(
        provider, model, "You evaluate summary quality.", prompt, options,
    )
    try:
        scores = _parse_json(raw)
    except (json.JSONDecodeError, ValueError):
        return {
            "error": "Failed to parse judge JSON",
            "raw_response": raw,
            "elapsed_seconds": elapsed,
        }
    scores["elapsed_seconds"] = round(elapsed, 1)
    return scores


async def recompact(
    provider: OllamaProvider,
    model: str,
    input_messages: list[dict[str, Any]],
    prior_summary: str | None,
    options: dict[str, Any] | None = None,
    custom_prompt: str | None = None,
    objective: str = "",
) -> dict[str, Any]:
    """Re-run compaction with different model/params."""
    from sdk.context._strategy import _build_summarize_prompt

    system_prompt = custom_prompt or _build_summarize_prompt(objective)
    conversation_text = serialize_messages(input_messages)

    user_content = conversation_text
    if prior_summary:
        user_content = (
            "PRIOR SUMMARY (from a previous compaction — integrate into "
            "your output, re-condensing where possible):\n\n"
            + prior_summary
            + "\n\n---\n\nNEW MESSAGES since last compaction:\n\n"
            + conversation_text
        )

    raw, elapsed = await _call_llm(
        provider, model, system_prompt, user_content, options,
    )
    return {
        "summary_text": raw,
        "elapsed_seconds": round(elapsed, 1),
    }


async def continuation_probe(
    provider: OllamaProvider,
    model: str,
    input_messages: list[dict[str, Any]],
    summary_text: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate probe questions and test recall from summary."""
    conversation_text = serialize_messages(input_messages)

    # Step 1: Generate questions
    gen_prompt = PROBE_GENERATION_PROMPT.format(
        conversation_text=conversation_text,
    )
    raw_questions, gen_elapsed = await _call_llm(
        provider, model, "You generate test questions.", gen_prompt, options,
    )
    try:
        probes = _parse_json(raw_questions)
    except (json.JSONDecodeError, ValueError):
        return {
            "error": "Failed to parse probe questions JSON",
            "raw_response": raw_questions,
            "elapsed_seconds": gen_elapsed,
        }

    if not probes:
        return {"probes": [], "elapsed_seconds": gen_elapsed}

    # Step 2: Answer from summary only
    questions_json = json.dumps(
        [p["question"] for p in probes], indent=2,
    )
    answer_prompt = PROBE_ANSWER_PROMPT.format(
        summary_text=summary_text,
        questions_json=questions_json,
    )
    raw_answers, answer_elapsed = await _call_llm(
        provider, model, "You answer questions from a summary.", answer_prompt, options,
    )
    try:
        answers = _parse_json(raw_answers)
    except (json.JSONDecodeError, ValueError):
        answers = [None] * len(probes)

    # Combine
    for i, probe in enumerate(probes):
        probe["model_answer"] = answers[i] if i < len(answers) else None

    return {
        "probes": probes,
        "elapsed_seconds": round(gen_elapsed + answer_elapsed, 1),
    }
