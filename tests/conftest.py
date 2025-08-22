"""Common test setup: stubs external services and exposes a Flask test app/client."""

import types, sys, base64, importlib, os
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

fake_chromadb_utils = types.SimpleNamespace(
    embedding_functions=types.SimpleNamespace(OpenAIEmbeddingFunction=lambda **k: None)
)
sys.modules.setdefault("chromadb.utils", fake_chromadb_utils)
sys.modules.setdefault("chromadb", types.SimpleNamespace(PersistentClient=lambda path: None))

@pytest.fixture
def app(monkeypatch, tmp_path):
    import rag

    small = [
        {"title": "A", "summary": "aaa", "themes": ["love"]},
        {"title": "B", "summary": "bbb", "themes": ["war"]},
    ]
    ext = [
        {"title": "A", "summary": "EXT A"},
        {"title": "B", "summary": "EXT B"},
    ]
    monkeypatch.setattr(rag, "load_books", lambda path=None: small)
    monkeypatch.setattr(rag, "load_books_ext", lambda path=None: ext)
    monkeypatch.setattr(rag, "llm_expand_query", lambda q, max_terms=10: [])

    class DummyCollection:
        def query(self, query_texts, n_results, include=None, where_document=None):
            return {
                "documents": [[
                    "note\n\nSummary:\naaa",
                    "note\n\nSummary:\nbbb",
                ]],
                "metadatas": [[{"title": "A"}, {"title": "B"}]],
                "distances": [[0.1, 0.2]],
            }
    monkeypatch.setattr(rag, "build_vector_store", lambda books: DummyCollection())

    import prompts
    def fake_build_messages_and_tools(query, candidates):
        msgs = [{"role": "system", "content": "x"}, {"role": "user", "content": "y"}]
        tools = [{
            "type": "function",
            "function": {"name": "get_summaries_by_titles",
                         "parameters": {"type": "object", "properties": {"titles": {"type": "array"}}}},
        }]
        return msgs, tools
    monkeypatch.setattr(prompts, "build_messages_and_tools", fake_build_messages_and_tools)

    import helpers
    monkeypatch.setattr(helpers, "safety_check", lambda text, context_hint="": (True, "ok"))
    monkeypatch.setattr(helpers, "intent_gate", lambda text: {"action": "proceed", "reply": ""})

    import config

    class Msg:
        def __init__(self, content, tool_calls=None):
            self.content = content
            self.tool_calls = tool_calls
    class Choice:
        def __init__(self, message): self.message = message
    class Resp:
        def __init__(self, content): self.choices = [Choice(Msg(content))]
    def fake_chat_create(**kwargs):
        return Resp("**A**\n\nWhy this book?\n- because\nSummary:\nEXT A\n")
    monkeypatch.setattr(config.client.chat.completions, "create", staticmethod(fake_chat_create))

    class FakeAudioResp: content = b"ID3\x03\x00demo"
    class FakeStreaming:
        def create(self, **k): raise RuntimeError("no stream in tests")
    monkeypatch.setattr(config.client.audio.speech, "with_streaming_response", FakeStreaming())
    monkeypatch.setattr(config.client.audio.speech, "create", staticmethod(lambda **k: FakeAudioResp()))

    class FakeTransc:
        def __init__(self, t): self.text = t
    monkeypatch.setattr(config.client.audio.transcriptions, "create",
                        staticmethod(lambda **k: FakeTransc("hello world")))

    tiny_png = base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\x0f\x00\x01\x01\x01\x00"
        b"\x18\xdd\xdcS\x00\x00\x00\x00IEND\xaeB`\x82"
    ).decode()
    class FakeImgObj:
        def __init__(self, b64): self.data = [types.SimpleNamespace(b64_json=b64)]
    monkeypatch.setattr(config.client.images, "generate", staticmethod(lambda **k: FakeImgObj(tiny_png)))

    web = importlib.import_module("web")
    web.app.config.update(TESTING=True)
    return web.app

@pytest.fixture
def client(app):
    return app.test_client()
