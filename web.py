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
    is_offensive,
    insult_gate_llm,
    intent_gate,
    clean_reply,
)
from routes_media import media_bp


# -------- logging --------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("smartlibrarian")

# -------- app & blueprints --------
app = Flask(__name__, template_folder="templates", static_folder="static")
app.register_blueprint(media_bp)

# -------- error handlers --------
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


# -------- startup: load DB + vector store (with fallbacks) --------
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

# -------- routes --------
@app.get("/")
def index():
    return render_template("index.html")


@app.post("/chat")
def chat():
    try:
        # ---- input ----
        try:
            data = request.get_json(force=True) or {}
        except Exception:
            logger.warning("Invalid JSON payload for /chat")
            data = {}
        user_text = (data.get("message") or "").strip()

        if not user_text:
            return jsonify({"reply": "Please type a message related to books."})

        # ---- moderation gates ----
        try:
            if user_text and is_offensive(user_text):
                return jsonify({"reply": "Please rephrase respectfully."})
            if not insult_gate_llm(user_text):
                return jsonify({"reply": "Please rephrase respectfully."})
        except Exception:
            logger.exception("Gates failed; continuing")

        # ---- intent gate ----
        try:
            gate = intent_gate(user_text)
            if gate.get("action") in {"greet", "clarify", "offtopic"}:
                return jsonify({"reply": gate.get("reply", "")})
        except Exception:
            logger.exception("Intent gate failed; proceeding as 'proceed'")

        # ---- retrieval ----
        expanded_terms = llm_expand_query(user_text, max_terms=10)
        retrieval_query = (
            user_text if not expanded_terms
            else f"{user_text}\nKeywords: {', '.join(expanded_terms)}"
        )
        try:
            if collection is None:
                candidates = books_small[:7]
            else:
                candidates = retrieve_candidates(collection, retrieval_query, k=7)
        except Exception:
            logger.exception("Retrieval failed; falling back to first items")
            candidates = books_small[:7]

        messages, tools = build_messages_and_tools(user_text, candidates)

        try:
            first = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.2,
            )
        except Exception:
            logger.exception("First completion failed")
            return jsonify({
                "reply": "I'm having trouble reaching the model right now. Please try again."
            })

        try:
            ai_msg = first.choices[0].message
        except Exception:
            logger.exception("No choices from model in first completion")
            return jsonify({"reply": "Sorry, I couldn't compose an answer. Please try again."})

        tool_calls = getattr(ai_msg, "tool_calls", None) or []
        if tool_calls:
            messages.append({
                "role": "assistant",
                "content": ai_msg.content or "",
                "tool_calls": [
                    {
                        "id": getattr(tc, "id", None),
                        "type": "function",
                        "function": {
                            "name": getattr(getattr(tc, "function", None), "name", ""),
                            "arguments": getattr(getattr(tc, "function", None), "arguments", "{}"),
                        },
                    }
                    for tc in tool_calls
                    if getattr(tc, "type", None) == "function"
                ],
            })

            for tc in tool_calls:
                if getattr(tc, "type", None) != "function" or not getattr(tc, "function", None):
                    continue

                fn_name = getattr(tc.function, "name", "")
                args_raw = getattr(tc.function, "arguments", "{}")
                try:
                    args = json.loads(args_raw or "{}")
                except Exception:
                    logger.warning("Tool arguments JSON parse failed; raw=%r", args_raw)
                    args = {}

                if fn_name == "get_summaries_by_titles":
                    titles = args.get("titles") or []
                    if isinstance(titles, str):
                        titles = [titles]
                    result = {t: get_summary_by_title_local(t) for t in titles}
                    messages.append({
                        "role": "tool",
                        "tool_call_id": getattr(tc, "id", None),
                        "name": "get_summaries_by_titles",
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                elif fn_name == "get_summary_by_title":
                    title = args.get("title") or ""
                    summary_text = get_summary_by_title_local(title)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": getattr(tc, "id", None),
                        "name": "get_summary_by_title",
                        "content": summary_text,
                    })
                else:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": getattr(tc, "id", None),
                        "name": fn_name or "UNKNOWN",
                        "content": "NOT_IMPLEMENTED",
                    })

            try:
                final = client.chat.completions.create(
                    model=CHAT_MODEL,
                    messages=messages,
                    temperature=0.2,
                )
                reply = clean_reply((final.choices[0].message.content or "").strip())
            except Exception:
                logger.exception("Final completion failed")
                reply = "Something went wrong while composing the answer. Please try again."
            return jsonify({"reply": reply})

        reply = clean_reply((ai_msg.content or "").strip())
        return jsonify({"reply": reply})

    except Exception:
        logger.exception("/chat route failed unexpectedly")
        return jsonify({"reply": "Unexpected error. Please try again."})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
