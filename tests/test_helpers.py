import helpers

def test_parse_json_loose_plain():
    assert helpers.parse_json_loose('{"a":1}') == {"a": 1}

def test_parse_json_loose_wrapped():
    text = "noise\n\n{ \"ok\": true }\nend"
    assert helpers.parse_json_loose(text) == {"ok": True}

def test_normalize_for_moderation():
    s = "Fuuuu!!! băăă\t  "
    out = helpers.normalize_for_moderation(s)
    assert out == "fuu baa"

def test_clean_reply_removes_labels():
    t = "Summary: hello\nExtended summary: more"
    assert helpers.clean_reply(t) == "hello\nmore"

def test_get_summary_by_title_local_factory():
    ext = [{"title": "A", "summary": "EXT A"}]
    fn = helpers.get_summary_by_title_local_factory(ext, [])
    assert fn("A") == "EXT A"
    assert fn("a") == "EXT A"
    assert fn("missing") == "NOT_FOUND"

def test_safety_check_balanced(monkeypatch):
    monkeypatch.setattr(helpers, "is_offensive", lambda t: True)
    monkeypatch.setattr(helpers, "insult_gate_llm", lambda t, context_hint="": True)
    allow, reason = helpers.safety_check("query", context_hint="informational")
    assert allow is True
