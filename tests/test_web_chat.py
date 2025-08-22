import importlib

def test_chat_proceed_ok(client):
    r = client.post("/chat", json={"message": "carti despre dragoste"})
    assert r.status_code == 200
    j = r.get_json()
    assert "A" in j["reply"]

def test_chat_offtopic_short_circuit(client, monkeypatch):
    web = importlib.import_module("web")
    monkeypatch.setattr(web, "intent_gate",
        lambda t: {"action": "offtopic", "reply": "OFFTOPIC"})
    r = client.post("/chat", json={"message": "care e vremea maine"})
    assert r.status_code == 200
    assert r.get_json()["reply"] == "OFFTOPIC"

def test_chat_blocked_by_safety(client, monkeypatch):
    web = importlib.import_module("web")
    monkeypatch.setattr(web, "safety_check", lambda text, context_hint="": (False, "blocked"))
    r = client.post("/chat", json={"message": "injurii"})
    assert r.status_code == 200
    assert r.get_json()["reply"].lower().startswith("please rephrase")
