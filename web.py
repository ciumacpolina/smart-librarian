from flask import Flask, render_template, request, jsonify
import json
import logging

from config import CHAT_MODEL, BOOKS_PATH, BOOKS_EXT_PATH, client
from rag import (
    load_books,
    load_books_ext,
    build_vector_store,
    llm_expand_query,
    retrieve_candidates,
)
from prompts import build_messages_and_tools
from helpers import (
    get_summary_by_title_local_factory,
    intent_gate,
    clean_reply,
    parse_json_loose,
    safety_check,   
)
from routes_media import media_bp

# ---------- logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smartlibrarian")

# ---------- app & blueprints ----------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.register_blueprint(media_bp, url_prefix="/api")

# ---------- error handlers ----------
@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": "bad_request"}), 400

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "not_found"}), 404

@app.errorhandler(500)
def server_error(e):
    logger.exception("Unhandled server error")
    return jsonify({"error": "server_error"}), 500

# ---------- startup: DB + vector store ----------
print("Loading databases…")
books_small = load_books(BOOKS_PATH)
books_ext = load_books_ext(BOOKS_EXT_PATH)

print("Building Chroma vector store…")
try:
    collection = build_vector_store(books_small)
except Exception:
    logger.exception("Chroma vector store build failed")
    collection = None  

get_summary_by_title_local = get_summary_by_title_local_factory(books_ext, books_small)

# ---------- routes ----------
@app.get("/")
def index():
    return render_template("index.html")

OFFTOPIC_MSG = "I can only help with books from this small library. Please mention a title or themes."

@app.post("/chat")
def chat():
    data = request.get_json(force=True) or {}
    user_text = (data.get("message") or data.get("text") or "").strip()
    if not user_text:
        return jsonify({"reply": "Please ask about books — a theme, mood, or a specific title from our small library."})

    # 1) Intent as hint 
    gate_hint = intent_gate(user_text)
    context_hint = "informational" if gate_hint.get("action") == "proceed" else ""

    # 2) Balanced/strict safety
    allow, _reason = safety_check(user_text, context_hint=context_hint)
    if not allow:
        return jsonify({"reply": "Please rephrase respectfully."})

    # 3) Short-circuit for greet/clarify/offtopic
    if gate_hint["action"] in {"greet", "clarify", "offtopic"}:
        return jsonify({"reply": gate_hint["reply"]})

    # 4) Retrieval (bring many so 'all/more' can return everything relevant)
    expanded_terms = llm_expand_query(user_text, max_terms=10)
    retrieval_query = user_text if not expanded_terms else f"{user_text}\nKeywords: {', '.join(expanded_terms)}"
    candidates = retrieve_candidates(
        collection, retrieval_query,
        k=(len(books_small) if collection else 0)
    )

    if not candidates:
        return jsonify({"reply": OFFTOPIC_MSG})

    # 5) Prompt + tools
    messages, tools = build_messages_and_tools(user_text, candidates)

    # 6) First call 
    first = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.2,
    )
    ai_msg = first.choices[0].message

    # 7) Tool execution loop
    if getattr(ai_msg, "tool_calls", None):
        messages.append({
            "role": "assistant",
            "content": ai_msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                }
                for tc in ai_msg.tool_calls if tc.type == "function"
            ],
        })

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
                title = (args.get("title") or "").strip()
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

    # 8) No tools → direct reply
    reply = clean_reply((ai_msg.content or "").strip())
    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True, threaded=True)
