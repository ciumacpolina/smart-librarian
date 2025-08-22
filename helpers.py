from __future__ import annotations

import json
import re
from typing import Dict, Callable, Any

from config import client, GATE_MODEL
from rag import normalize_text


def _to_text(v: Any) -> str:
    if isinstance(v, list):
        return "\n\n".join(str(x) for x in v)
    return str(v) if v is not None else ""


def parse_json_loose(text: str) -> Dict:
    try:
        return json.loads(text or "")
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text or "")
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}


def get_summary_by_title_local_factory(
    books_ext: list, _books_small_unused: list
) -> Callable[[str], str]:
    ext_map_norm = {normalize_text(b["title"]): _to_text(b["summary"]) for b in books_ext}
    ext_map_raw = {b["title"]: _to_text(b["summary"]) for b in books_ext}

    def _impl(title: str) -> str:
        if not title:
            return "NOT_FOUND"
        t_norm = normalize_text(title)
        if t_norm in ext_map_norm:
            return ext_map_norm[t_norm]
        if title in ext_map_raw:
            return ext_map_raw[title]
        return "NOT_FOUND"

    return _impl


# --- light normalization for logs / prompt context (LLM must judge by RAW text) ---
def normalize_for_moderation(s: str) -> str:
    if not s:
        return ""
    t = normalize_text(s)
    t = re.sub(r"(.)\1{2,}", r"\1\1", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_offensive(text: str) -> bool:
    """Focus on abuse/hate/threats; ignore generic 'violence' buckets."""
    try:
        resp = client.moderations.create(model="omni-moderation-latest", input=text)
        r = resp.results[0]
        cats = getattr(r, "categories", {}) or {}
        keys = (
            "harassment", "harassment/threats",
            "hate", "hate/threatening",
            "sexual/harassment", "sexual/minors",
        )
        return any(bool(cats.get(k, False)) for k in keys)
    except Exception:
        return False


def insult_gate_llm(user_text: str, *, context_hint: str = "") -> bool:
    """
    Return True to ALLOW, False to BLOCK.
    Strict rule: block if the message contains any insult/profanity/slur/harassment/hate,
    even when mixed with a normal book request. Language-agnostic.
    """
    cleaned = normalize_for_moderation(user_text)

    system = (
        "You are a multilingual profanity/insult/hate-speech detector for a BOOK chatbot. "
        'Return STRICT JSON: {"block": true|false}. '
        "Block if the message contains ANY insult, profanity, slur, harassment, or hate speech "
        "(even if it appears alongside a normal request). "
        "Output JSON only."
    )
    user = f"RAW:\n{user_text}\n\nNORMALIZED:\n{cleaned}\n"

    try:
        resp = client.chat.completions.create(
            model=GATE_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0,
            max_tokens=50,
        )
        data = parse_json_loose(resp.choices[0].message.content)
        return not bool(data.get("block", False))
    except Exception:
        return True


def safety_check(user_text: str, *, context_hint: str = "") -> tuple[bool, str]:
    """
    Returns (allow, reason).
    - informational: follow LLM gate (reduce false positives for neutral queries).
    - other: strict OR with Moderation API.
    """
    api_flagged = is_offensive(user_text)
    llm_allows = insult_gate_llm(user_text, context_hint=context_hint)

    if context_hint == "informational":
        return (llm_allows, "informational_pass" if llm_allows else "informational_block_llm")

    allow = not (api_flagged or (not llm_allows))
    return (allow, "strict_pass" if allow else "strict_or_block")


def intent_gate(user_text: str) -> Dict[str, str]:
    """
    Returns one of: greet / clarify / offtopic / proceed as JSON {action, reply}.
    """
    system = (
        "You are an intent gate for a BOOK recommendation chatbot. "
        "Always respond in English. Output STRICT JSON with keys: action, reply. "
        "Pick exactly one: 'greet', 'clarify', 'offtopic', 'proceed'.\n\n"
        "- 'greet' ONLY for standalone greetings.\n"
        "- 'offtopic' when not about books/literature.\n"
        "- 'proceed' when there is ANY book-related clue: title or high-level theme/genre/mood/audience.\n"
        "- 'clarify' only when the message is too vague.\n\n"
        "Replies (use exactly):\n"
        "- greet → 'Hi! What kind of books are you interested in?'\n"
        "- clarify → 'Please ask about books — a theme, mood, or a specific title from our small library.'\n"
        "- offtopic → 'I can only help with books from this small library. Please mention a title or themes.'\n"
        "- proceed → ''"
    )
    resp = client.chat.completions.create(
        model=GATE_MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user_text}],
        temperature=0,
        max_tokens=120,
    )
    data = parse_json_loose(resp.choices[0].message.content)
    action = (data.get("action") or "").lower()
    reply = (data.get("reply") or "").strip()
    if action not in {"greet", "clarify", "offtopic", "proceed"}:
        action, reply = "proceed", ""
    return {"action": action, "reply": reply}


def clean_reply(text: str) -> str:
    if not text:
        return text
    for lab in ("Extended summary:", "extended summary:", "Summary:", "summary:"):
        text = text.replace(lab, "")
    lines = [ln.strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return text.strip()
