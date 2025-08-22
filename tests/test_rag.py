import rag

def test_parse_json_safe_extract():
    s = "xx {\"a\": 2} yy"
    assert rag.parse_json_safe(s) == {"a": 2}

def test_strip_and_normalize():
    raw = "ĂâÎî  --  Dragoste!"
    assert rag.strip_diacritics(raw) != raw
    assert rag.normalize_text(raw) == "aaii dragoste"

class DummyCollection:
    def query(self, query_texts, n_results, include=None, where_document=None):
        return {
            "documents": [[
                "Intro\nSummary:\nS1",
                "X\nSummary:\nS2",
            ]],
            "metadatas": [[{"title": "T1"}, {"title": "T2"}]],
            "distances": [[0.05, 0.12]],
        }

def test_retrieve_candidates_mapping():
    coll = DummyCollection()
    out = rag.retrieve_candidates(coll, "q", k=2)
    assert len(out) == 2
    assert out[0]["title"] == "T1"
    assert out[0]["summary"] == "S1"
    assert isinstance(out[0]["score"], float)
