"""Prompt templates for compaction evaluation LLM operations."""

FACT_EXTRACTION_PROMPT = (
    "You are analyzing a conversation to extract discrete facts. Extract every "
    "specific, verifiable piece of information from the conversation below.\n"
    "\n"
    "For each fact, output a JSON object with these fields:\n"
    '- "text": the fact statement (one sentence)\n'
    '- "category": one of "file_path", "tool_call", "decision", "error", '
    '"data_value", "code_detail", "url", "finding", "other"\n'
    "\n"
    "Output ONLY a JSON array of these objects. No commentary, no markdown fences.\n"
    "\n"
    "CONVERSATION:\n"
    "{conversation_text}"
)

FACT_MATCHING_PROMPT = (
    "Given the following summary and list of facts, determine which facts are "
    "preserved in the summary. For each fact, answer true if the summary contains "
    "this information (even if paraphrased) or false if the information is missing.\n"
    "\n"
    "SUMMARY:\n"
    "{summary_text}\n"
    "\n"
    "FACTS:\n"
    "{facts_json}\n"
    "\n"
    "Output ONLY a JSON array of booleans, one per fact, in the same order. "
    "No commentary."
)

JUDGE_PROMPT = (
    "You are evaluating the quality of a conversation summary. You will be given "
    "the original conversation and the summary that was generated from it.\n"
    "\n"
    "Score the summary on these dimensions (1-5 scale):\n"
    "\n"
    "1. **Completeness** (1-5): Does the summary capture all important facts, "
    "decisions, and data from the conversation? Are file paths, URLs, numbers, "
    "and specific details preserved?\n"
    "2. **Accuracy** (1-5): Is everything in the summary factually correct "
    "relative to the source? Are there any hallucinated or distorted details?\n"
    "3. **Conciseness** (1-5): Is the summary appropriately compact without "
    "unnecessary repetition or filler? Does it achieve good information density?\n"
    "4. **Usefulness for continuation** (1-5): Could an AI assistant continue "
    "the task effectively using only this summary? Does it capture current state, "
    "pending work, and key context?\n"
    "\n"
    "Respond with a JSON object:\n"
    '{{\n'
    '  "completeness": {{"score": N, "reasoning": "..."}},\n'
    '  "accuracy": {{"score": N, "reasoning": "..."}},\n'
    '  "conciseness": {{"score": N, "reasoning": "..."}},\n'
    '  "usefulness": {{"score": N, "reasoning": "..."}}\n'
    '}}\n'
    "\n"
    "No commentary outside the JSON.\n"
    "\n"
    "ORIGINAL CONVERSATION:\n"
    "{conversation_text}\n"
    "\n"
    "SUMMARY:\n"
    "{summary_text}"
)

PROBE_GENERATION_PROMPT = (
    "You are generating test questions to evaluate whether a conversation summary "
    "preserves enough information for an AI to continue working.\n"
    "\n"
    "Given the following conversation, generate 5-8 specific questions that:\n"
    "- Require knowledge of concrete facts from the conversation (file paths, "
    "function names, URLs, numbers, error messages, decisions made)\n"
    "- Would be answerable by someone who read the full conversation\n"
    "- Would be UNANSWERABLE if the summary dropped important details\n"
    "\n"
    "For each question, include the expected answer from the source conversation.\n"
    "\n"
    "Output a JSON array of objects:\n"
    '[{{"question": "...", "expected_answer": "..."}}]\n'
    "\n"
    "No commentary outside the JSON.\n"
    "\n"
    "CONVERSATION:\n"
    "{conversation_text}"
)

PROBE_ANSWER_PROMPT = (
    "You are an AI assistant that has been given a summary of a previous "
    "conversation. Answer each question based ONLY on what is in the summary. "
    "If the summary does not contain enough information to answer, say "
    '"INSUFFICIENT INFORMATION".\n'
    "\n"
    "SUMMARY:\n"
    "{summary_text}\n"
    "\n"
    "QUESTIONS:\n"
    "{questions_json}\n"
    "\n"
    "Output a JSON array of strings, one answer per question, in order. "
    "No commentary."
)
