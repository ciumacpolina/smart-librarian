# web.py
# Flask UI + RAG + OpenAI tools (English UI)

from flask import Flask, render_template, request, jsonify, Response
import json, re, os, tempfile
from pathlib import Path
import base64, uuid
from pathlib import Path


from config import CHAT_MODEL, client, BOOKS_PATH, BOOKS_EXT_PATH
from rag import (
    load_books, load_books_ext, build_vector_store,
    llm_expand_query, retrieve_candidates, normalize_text
)
from prompts import build_messages_and_tools

app = Flask(__name__, template_folder="templates", static_folder="static")
IMG_DIR = Path(app.static_folder) / "gen"
IMG_DIR.mkdir(parents=True, exist_ok=True)


# ----------------------- Helpers -----------------------

def _to_text(v):
    if isinstance(v, list):
        return "\n\n".join(str(x) for x in v)
    return str(v) if v is not None else ""

def parse_json_loose(text: str) -> dict:
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

def clean_reply(text: str) -> str:
    if not text:
        return text
    for lab in ["Extended summary:", "extended summary:", "Summary:", "summary:"]:
        text = text.replace(lab, "")
    return text.strip()

# ----------------------- Moderation & gates -----------------------

def is_offensive(text: str) -> bool:
    """OpenAI Moderation (multilingual) – blocare dacă e clar ofensator."""
    try:
        resp = client.moderations.create(model="omni-moderation-latest", input=text)
        r = resp.results[0]
        if getattr(r, "flagged", False):
            return True
        cats = getattr(r, "categories", {}) or {}
        keys = ["harassment", "harassment/threats", "hate", "hate/threatening"]
        return any(bool(cats.get(k, False)) for k in keys)
    except Exception:
        return False

GATE_MODEL = "gpt-4o"

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
    Intent gate permisiv:
    - greet doar pt. saluturi pure;
    - offtopic dacă nu e despre cărți;
    - proceed dacă există orice indiciu (temă/ gen / mood / public țintă sau titlu);
    - clarify dacă nu există niciun indiciu.
    """
    system = (
        "You are an intent gate for a BOOK recommendation chatbot. "
        "Always respond in English. Output STRICT JSON with keys: action, reply. "
        "Pick exactly one: 'greet', 'clarify', 'offtopic', 'proceed'.\n\n"
        "- 'greet' ONLY for standalone greetings (hi/hello/salut/buna).\n"
        "- 'offtopic' when not about books/literature.\n"
        "- 'proceed' when there is ANY book-related clue: title OR high-level theme/genre/mood/audience "
        "(e.g., love/romance, friendship, war, mystery/detective/crime, fantasy, sci-fi, historical, "
        "adventure, horror, coming-of-age, classics, magic/wizard, dystopia, family, grief, courage, "
        "for teenagers/young adult/adolescents, for children/kids, funny, sad, inspiring; "
        "Romanian cues like 'dragoste', 'prietenie', 'război', 'adolescenți', 'mister', 'aventură', 'istoric', 'magie' also count).\n"
        "- 'clarify' only when the message is too vague.\n\n"
        "Replies (use exactly):\n"
        "- greet → 'Hi! What kind of books are you interested in?'\n"
        "- clarify → 'Please ask about books — a theme, mood, or a specific title from our small library.'\n"
        "- offtopic → 'I can only help with books from this small library. Please mention a title or themes.'\n"
        "- proceed → ''"
    )
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
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

# ----------------------- Startup -----------------------

print("📚 Loading databases…")
books_small = load_books(BOOKS_PATH)
books_ext   = load_books_ext(BOOKS_EXT_PATH)

print("🔎 Building Chroma vector store…")
collection = build_vector_store(books_small)

get_summary_by_title_local = get_summary_by_title_local_factory(books_ext, books_small)

# ----------------------- Routes -----------------------

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/chat")
def chat():
    data = request.get_json(force=True) or {}
    user_text = (data.get("message") or "").strip()

    # A) Moderation / insult gate
    if user_text and is_offensive(user_text):
        return jsonify({"reply": "Please rephrase respectfully."})
    if not insult_gate_llm(user_text):
        return jsonify({"reply": "Please rephrase respectfully."})

    # B) Intent gate
    gate = intent_gate(user_text)
    if gate["action"] in {"greet", "clarify", "offtopic"}:
        return jsonify({"reply": gate["reply"]})

    # C) Retrieval
    expanded_terms = llm_expand_query(user_text, max_terms=10)
    retrieval_query = user_text if not expanded_terms else f"{user_text}\nKeywords: {', '.join(expanded_terms)}"
    candidates = retrieve_candidates(collection, retrieval_query, k=7)

    # D) Prompt & tools
    messages, tools = build_messages_and_tools(user_text, candidates)

    # E) First call (model poate cere tool)
    first = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.2,
    )
    ai_msg = first.choices[0].message

    # F) Execuție tool(s) și al doilea call
    if getattr(ai_msg, "tool_calls", None):
        # assistant with tool_calls
        messages.append({
            "role": "assistant",
            "content": ai_msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                } for tc in ai_msg.tool_calls
            ],
        })

        # un răspuns 'tool' pentru fiecare tool_call_id
        for tc in ai_msg.tool_calls:
            if tc.type != "function":
                continue

            fn = tc.function.name
            args = parse_json_loose(tc.function.arguments or "{}")

            if fn == "get_summaries_by_titles":
                titles = args.get("titles") or []
                if isinstance(titles, str):
                    titles = [titles]
                result_map = {t: get_summary_by_title_local(t) for t in titles}
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": "get_summaries_by_titles",
                    "content": json.dumps(result_map, ensure_ascii=False),
                })
            elif fn == "get_summary_by_title":
                title = args.get("title") or ""
                summary_text = get_summary_by_title_local(title)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": "get_summary_by_title",
                    "content": summary_text,
                })
            else:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": fn,
                    "content": "NOT_IMPLEMENTED",
                })

        final = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=messages,
            temperature=0.2,
        )
        reply = clean_reply((final.choices[0].message.content or "").strip())
        return jsonify({"reply": reply})

    # Fallback: fără tool
    reply = clean_reply((ai_msg.content or "").strip())
    return jsonify({"reply": reply})

# ----------------------- TTS (single fixed voice) -----------------------

@app.post("/tts")
def tts():
    """
    Text-to-speech: primește {text} și întoarce MP3 (voice='alloy').
    Fără salvare pe disc (folosim fișier temporar).
    """
    try:
        data = request.get_json(force=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return Response(b"", mimetype="audio/mpeg")

        # Streaming API -> temp file -> bytes
        with client.audio.speech.with_streaming_response.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text,
        ) as resp:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                tmp_path = tmp.name
            try:
                resp.stream_to_file(tmp_path)
                with open(tmp_path, "rb") as f:
                    mp3 = f.read()
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        return Response(mp3, mimetype="audio/mpeg")

    except Exception:
        # Fallback non-streaming (în funcție de SDK)
        try:
            audio = client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice="alloy",
                input=text,
            )
            mp3 = getattr(audio, "content", None)
            if mp3 is None and hasattr(audio, "read"):
                mp3 = audio.read()
            if mp3 is None:
                mp3 = b""
            return Response(mp3, mimetype="audio/mpeg")
        except Exception:
            return Response("TTS error", status=500)

# -----------------------
@app.post("/stt")
def stt():
    """
    Speech-to-Text:
      - primește multipart/form-data cu un fișier 'audio' (webm)
      - apelează OpenAI Transcribe (gpt-4o-transcribe; fallback whisper-1)
      - răspunde JSON: {"text": "..."} sau {"text": ""} la nevoie
    """
    try:
        f = request.files.get("audio")
        if not f:
            return jsonify({"text": ""}), 400

        # scriem temporar fișierul, deoarece SDK-ul cere un file-like real
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            temp_path = tmp.name
            f.save(temp_path)

        try:
            with open(temp_path, "rb") as audio_file:
                try:
                    # model recomandat în docs
                    resp = client.audio.transcriptions.create(
                        model="gpt-4o-transcribe",
                        file=audio_file
                    )
                except Exception:
                    # fallback clasic
                    audio_file.seek(0)
                    resp = client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file
                    )

            text = getattr(resp, "text", "") or ""
            return jsonify({"text": text})

        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    except Exception as e:
        print("STT error:", repr(e))
        return jsonify({"text": ""}), 500

## IMAGE GENERATION (optional, gpt-image-1) -----------------------  
@app.post("/image")
def generate_image():
    """
    Generează o imagine cu gpt-image-1 și o salvează în /static/gen/{uuid}.png.
    Returnează JSON: {"url": "/static/gen/<file>.png"}
    """
    try:
        data = request.get_json(force=True) or {}
        prompt  = (data.get("prompt")  or "").strip()
        size    = (data.get("size")    or "1024x1024").strip()   # permise: 1024x1024, 1024x1536, 1536x1024, auto
        quality = (data.get("quality") or "low").strip()         # permise: low, medium, high, auto

        if not prompt:
            return jsonify({"error": "empty_prompt"}), 400

        allowed_sizes = {"1024x1024", "1024x1536", "1536x1024", "auto"}
        if size not in allowed_sizes:
            size = "1024x1024"

        allowed_quality = {"low", "medium", "high", "auto"}
        if quality not in allowed_quality:
            quality = "low"

        # ATENȚIE: NU trimitem response_format – nu este suportat.
        result = client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
            quality=quality,
            # background="transparent",  # opțional: decomentează dacă vrei PNG cu fundal transparent
        )

        b64 = result.data[0].b64_json
        img_bytes = base64.b64decode(b64)

        filename = f"{uuid.uuid4().hex}.png"
        out_path = IMG_DIR / filename
        out_path.write_bytes(img_bytes)

        return jsonify({"url": f"/static/gen/{filename}"})
    except Exception as e:
        print("IMAGE error:", repr(e))
        return jsonify({"error": "image_gen_failed"}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
