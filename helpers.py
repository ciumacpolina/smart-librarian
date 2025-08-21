# helpers.py
import json, re
from typing import Dict
from config import client, CHAT_MODEL, GATE_MODEL
from rag import normalize_text



def _to_text(v):
    if isinstance(v, list):
        return "\n\n".join(str(x) for x in v)
    return str(v) if v is not None else ""

def parse_json_loose(text: str) -> Dict:
    """Extrage JSON chiar dacă modelul a pus text în jur."""
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

def get_summary_by_title_local_factory(books_ext, _books_small_unused):
    """Returnează DOAR summary-ul extins din baza mare (fără fallback)."""
    ext_map_norm = {normalize_text(b["title"]): _to_text(b["summary"]) for b in books_ext}
    ext_map_raw  = {b["title"]: _to_text(b["summary"]) for b in books_ext}

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
    if not s:
        return ""
    t = normalize_text(s)
    t = re.sub(r'(.)\1{2,}', r'\1\1', t)  # fuuuu -> fuu
    t = re.sub(r'[^a-z0-9]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def is_offensive(text: str) -> bool:
    """OpenAI Moderation (multilingual)."""
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
    Detector multilingv; True = allow, False = block.
    Fără liste hardcodate, fără exemple.
    """
    cleaned = normalize_for_moderation(user_text)
    tokens = cleaned.split()

    system = (
        "You are a multilingual profanity/insult/harassment detector for a BOOK chatbot. "
        "Return STRICT JSON: {\"block\": true|false}. "
        "BLOCK only if the message clearly contains insult/profanity/slur/harassment/hate speech "
        "(even if obfuscated or inside a longer sentence). If uncertain, set block=false. Output JSON only."
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

def intent_gate(user_text: str) -> dict:
    """
    Intent gate permisiv – IDENTIC cu varianta ta anterioară.
    """
    system = (
        "You are an intent gate for a BOOK recommendation chatbot. "
        "Always respond in English. Output STRICT JSON with keys: action, reply. "
        "Pick exactly one: 'greet', 'clarify', 'offtopic', 'proceed'.\n\n"
        "- 'greet' ONLY for standalone greetings.\n"
        "- 'offtopic' when not about books/literature.\n"
        "- 'proceed' when there is ANY book-related clue: title OR high-level theme/genre/mood/audience "
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
    reply  = (data.get("reply") or "").strip()
    if action not in {"greet", "clarify", "offtopic", "proceed"}:
        action, reply = "proceed", ""
    return {"action": action, "reply": reply}

def clean_reply(text: str) -> str:
    if not text:
        return text
    for lab in ["Extended summary:", "extended summary:", "Summary:", "summary:"]:
        text = text.replace(lab, "")
    return text.strip()
