from __future__ import annotations

import json
import re
from typing import Dict, Callable, Any

from config import client, GATE_MODEL
from rag import normalize_text


def _to_text(v: Any) -> str:
    """Return a plain string; join lists with blank lines."""
    if isinstance(v, list):
        return "\n\n".join(str(x) for x in v)
    return str(v) if v is not None else ""


def parse_json_loose(text: str) -> Dict:
    """
    Parse JSON even if the model wrapped it with extra text.
    Returns {} on failure.
    """
    try:
        return json.loads(text or "")
    except Exception:
        m = re.search(r"\{[\s\S]*\}", text or "")
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}


def get_summary_by_title_local_factory(
    books_ext: list, _books_small_unused: list
) -> Callable[[str], str]:
    """
    Build a callable that returns the extended summary for a given title
    (exact or normalized match) or 'NOT_FOUND' when missing.
    """
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


def normalize_for_moderation(s: str) -> str:
    """Light normalization for safety checks (casefold, strip repeats, keep a–z0–9)."""
    if not s:
        return ""
    t = normalize_text(s)
    t = re.sub(r"(.)\1{2,}", r"\1\1", t)  # fuuuu -> fuu
    t = re.sub(r"[^a-z0-9]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def is_offensive(text: str) -> bool:
    """
    OpenAI Moderation (multilingual).
    Returns True if flagged; returns False on SDK/network errors (fail-open).
    """
    try:
        resp = client.moderations.create(model="omni-moderation-latest", input=text)
        r = resp.results[0]
        if getattr(r, "flagged", False):
            return True
        cats = getattr(r, "categories", {}) or {}
        keys = ["harassment", "harassment/threats", "hate", "hate/threatening"]
        return any(bool(cats.get(k, False)) for k in keys)
    except Exception:
        return False  # fail-open


def insult_gate_llm(user_text: str) -> bool:
    """
    LLM-based profanity/harassment gate.
    Returns True to allow, False to block. On errors returns True (fail-open).
    """
    cleaned = normalize_for_moderation(user_text)
    tokens = cleaned.split()

    system = (
        "You are a multilingual profanity/insult/harassment detector for a BOOK chatbot. "
        'Return STRICT JSON: {"block": true|false}. '
        "BLOCK only if the message clearly contains insult/profanity/slur/harassment/hate speech "
        "(even if obfuscated or within a longer sentence). If uncertain, set block=false. Output JSON only."
    )
    user = f"RAW:\n{user_text}\n\nNORMALIZED:\n{cleaned}\n\nTOKENS:\n{tokens}\n"

    try:
        resp = client.chat.completions.create(
            model=GATE_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.0,
        )
        data = parse_json_loose(resp.choices[0].message.content)
        return not bool(data.get("block", False))
    except Exception:
        return True  # fail-open


def intent_gate(user_text: str) -> Dict[str, str]:
    """
    Intent router: returns {'action': one of greet/clarify/offtopic/proceed, 'reply': str}.
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
        temperature=0.0,
    )
    data = parse_json_loose(resp.choices[0].message.content)
    action = (data.get("action") or "").lower()
    reply = (data.get("reply") or "").strip()
    if action not in {"greet", "clarify", "offtopic", "proceed"}:
        action, reply = "proceed", ""
    return {"action": action, "reply": reply}


def clean_reply(text: str) -> str:
    """Trim boilerplate labels the model may add and strip whitespace."""
    if not text:
        return text
    for lab in ("Extended summary:", "extended summary:", "Summary:", "summary:"):
        text = text.replace(lab, "")
    return text.strip()
