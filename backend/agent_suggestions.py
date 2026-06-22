import json
import re
import time
from typing import Optional

CACHE_TTL_SECONDS = 3600
_suggestion_cache: dict[str, dict] = {}

SUGGESTION_PROMPT = """You are a Microsoft Fabric Data Agent assistant.

{description_line}

Based ONLY on the actual data sources, tables, columns, and metrics you have access to, generate exactly 4 example questions that a business user could naturally ask you in plain English.

Requirements:
- Each question must be answerable using your connected data
- Use natural language only (no SQL)
- Be specific to your available datasets where possible
- Questions should be diverse (overview, aggregation, comparison, drill-down)

Return ONLY a valid JSON array containing exactly 4 strings. No markdown, no numbering, no extra text.

Example: ["What is the total sales this month?", "Which products have the lowest inventory?", "Compare revenue by region", "Show me recent order trends"]"""

FOLLOWUP_SUGGESTION_PROMPT = """You are a Microsoft Fabric Data Agent assistant.

{description_line}

The user just had this conversation with you:

{conversation_block}

Based on this conversation and ONLY on data you can actually query, generate exactly 4 natural follow-up questions the user might ask next.

Requirements:
- Each question must logically follow from what was just discussed
- Use natural language only (no SQL)
- Be specific to the topics, metrics, or entities mentioned in the conversation
- Questions should be diverse (drill-down, comparison, related metric, broader view)
- Do NOT repeat questions the user already asked

Return ONLY a valid JSON array containing exactly 4 strings. No markdown, no numbering, no extra text."""


def _description_line(agent: dict) -> str:
    desc = (agent.get("description") or "").strip()
    name = (agent.get("name") or "Data Agent").strip()
    if desc:
        return f"Agent name: {name}\nAgent description: {desc}"
    return f"Agent name: {name}"


def _parse_suggestions(text: str) -> list[str]:
    if not text:
        return []

    cleaned = text.strip()

    try:
        match = re.search(r"\[[\s\S]*?\]", cleaned)
        if match:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                items = [str(item).strip() for item in parsed if str(item).strip()]
                if items:
                    return items[:4]
    except json.JSONDecodeError:
        pass

    lines: list[str] = []
    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        line = re.sub(r"^\d+[\.\)]\s*", "", line)
        line = re.sub(r"^[-*•]\s*", "", line)
        line = line.strip("\"'")
        if not line or len(line) < 10:
            continue
        if not line.endswith("?"):
            line = f"{line}?"
        lines.append(line)

    return lines[:4]


def _fallback_suggestions(agent: dict) -> list[str]:
    desc = (agent.get("description") or "").strip()
    name = (agent.get("name") or "this data").strip()

    suggestions: list[str] = []
    if desc:
        primary = desc.split(",")[0].strip()
        suggestions.append(f"What data is available about {primary}?")
        suggestions.append(f"Give me a summary overview of {primary}")
    else:
        suggestions.append(f"What data sources does {name} have access to?")
        suggestions.append("What kind of questions can I ask you?")

    suggestions.append("Show me the top records from the main dataset")
    suggestions.append("What are the key metrics or totals I can explore?")

    return suggestions[:4]


def _format_conversation_block(exchanges: list[dict], max_answer_chars: int = 800) -> str:
    lines: list[str] = []
    for exchange in exchanges:
        question = (exchange.get("question") or "").strip()
        answer = (exchange.get("answer") or "").strip()
        if len(answer) > max_answer_chars:
            answer = f"{answer[:max_answer_chars]}..."
        if question:
            lines.append(f"User: {question}")
        if answer:
            lines.append(f"Assistant: {answer}")
        lines.append("")
    return "\n".join(lines).strip()


def _fallback_followup_suggestions(exchanges: list[dict], agent: dict) -> list[str]:
    latest = exchanges[-1] if exchanges else {}
    question = (latest.get("question") or "").strip()
    answer = (latest.get("answer") or "").strip()

    suggestions: list[str] = []
    if question and len(question) > 12:
        short = f"{question[:55]}..." if len(question) > 55 else question
        suggestions.append(f"Can you break this down further: {short}")
        suggestions.append(f"What else can you tell me about: {short}")

    if "|" in answer or "row" in answer.lower():
        suggestions.append("Can I get more rows from this result?")
        suggestions.append("Summarize the key totals from this data")

    suggestions.append("What related metrics should I look at next?")
    suggestions.append("Show me a comparison based on this answer")

    unique: list[str] = []
    for item in suggestions:
        if item not in unique:
            unique.append(item)

    if len(unique) < 4:
        unique.extend(_fallback_suggestions(agent))

    return unique[:4]


def _user_cache_key(agent_id: str, user_email: Optional[str]) -> str:
    email = (user_email or "anonymous").strip().lower()
    return f"{email}:{agent_id}"


def _user_thread_suffix(user_email: Optional[str]) -> str:
    email = (user_email or "anonymous").strip().lower()
    safe = re.sub(r"[^a-z0-9]+", "-", email).strip("-")
    return safe or "anonymous"


def generate_followup_suggestions(
    client,
    agent: dict,
    exchanges: list[dict],
    user_email: Optional[str] = None,
    timeout: int = 90,
) -> list[str]:
    if not exchanges:
        return _fallback_suggestions(agent)

    conversation_block = _format_conversation_block(exchanges)
    prompt = FOLLOWUP_SUGGESTION_PROMPT.format(
        description_line=_description_line(agent),
        conversation_block=conversation_block,
    )
    thread_name = f"suggestions-followup-{agent['id']}-{_user_thread_suffix(user_email)}"

    try:
        answer = client.ask(
            prompt,
            timeout=timeout,
            thread_name=thread_name,
            preserve_thread=True,
        )
        if answer and not str(answer).startswith("Error:"):
            suggestions = _parse_suggestions(str(answer))
            if len(suggestions) >= 2:
                return suggestions[:4]
    except Exception:
        pass

    return _fallback_followup_suggestions(exchanges, agent)


def generate_agent_suggestions(
    client,
    agent: dict,
    user_email: Optional[str] = None,
    timeout: int = 120,
    force_refresh: bool = False,
) -> list[str]:
    agent_id = agent["id"]
    cache_key = _user_cache_key(agent_id, user_email)

    if not force_refresh:
        cached = _suggestion_cache.get(cache_key)
        if cached and (time.time() - cached["cached_at"]) < CACHE_TTL_SECONDS:
            return cached["suggestions"]

    prompt = SUGGESTION_PROMPT.format(description_line=_description_line(agent))
    thread_name = f"suggestions-{agent_id}-{_user_thread_suffix(user_email)}"

    try:
        answer = client.ask(
            prompt,
            timeout=timeout,
            thread_name=thread_name,
            preserve_thread=True,
        )
        if answer and not str(answer).startswith("Error:"):
            suggestions = _parse_suggestions(str(answer))
            if len(suggestions) >= 2:
                result = suggestions[:4]
                _suggestion_cache[cache_key] = {
                    "suggestions": result,
                    "cached_at": time.time(),
                }
                return result
    except Exception:
        pass

    fallback = _fallback_suggestions(agent)
    _suggestion_cache[cache_key] = {
        "suggestions": fallback,
        "cached_at": time.time(),
    }
    return fallback


def clear_suggestion_cache(agent_id: Optional[str] = None) -> None:
    if agent_id:
        _suggestion_cache.pop(agent_id, None)
    else:
        _suggestion_cache.clear()
