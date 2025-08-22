"""Edge-case flow tests: ALL results, insult+request blocking, empty RAG, large STT file."""

import importlib
import io

def test_all_love_returns_all_candidates(client, monkeypatch):
    rag = importlib.import_module("rag")
    config = importlib.import_module("config")

    cands = [
        {"title": "A", "summary": "aaa", "score": 0.01},
        {"title": "B", "summary": "bbb", "score": 0.02},
        {"title": "C", "summary": "ccc", "score": 0.03},
    ]
    monkeypatch.setattr(rag, "retrieve_candidates", lambda coll, q, k=10: cands)

    class Msg:
        def __init__(self, content, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls
    class Choice:
        def __init__(self, message): self.message = message
    class Resp:
        def __init__(self, content): self.choices = [Choice(Msg(content))]

    def fake_chat_create(**kwargs):
        return Resp("**A**\n\nWhy this book?\n- because\nSummary:\nEXT A\n\n"
                    "**B**\n\nWhy this book?\n- because\nSummary:\nEXT B\n\n"
                    "**C**\n\nWhy this book?\n- because\nSummary:\nEXT C\n")
    import builtins
    monkeypatch.setattr(config.client.chat.completions, "create", staticmethod(fake_chat_create))

    r = client.post("/chat", json={"message": "dă-mi toate cărțile despre dragoste"})
    assert r.status_code == 200
    txt = r.get_json()["reply"]
    assert "**A**" in txt and "**B**" in txt and "**C**" in txt

def test_block_insult_plus_request(client, monkeypatch):
    web = importlib.import_module("web")
    monkeypatch.setattr(web, "safety_check", lambda text, context_hint="": (False, "blocked"))
    r = client.post("/chat", json={"message": "ești prost, dar recomandă-mi o carte de dragoste"})
    assert r.status_code == 200
    assert r.get_json()["reply"].lower().startswith("please rephrase")

def test_proceed_but_no_candidates_offtopic(client, monkeypatch):
    web = importlib.import_module("web")
    monkeypatch.setattr(web, "intent_gate", lambda t: {"action": "proceed", "reply": ""})
    monkeypatch.setattr(web, "retrieve_candidates", lambda coll, q, k=10: [])
    r = client.post("/chat", json={"message": "temă rară pe care nu o avem"})
    assert r.status_code == 200
    assert r.get_json()["reply"] == web.OFFTOPIC_MSG

def test_stt_large_file_transcribed(client):
    payload = b"\x00" * 8000
    data = {"audio": (io.BytesIO(payload), "voice.webm")}
    r = client.post("/api/stt", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert r.get_json()["text"] == "hello world"
