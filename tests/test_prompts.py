import prompts

def test_build_messages_and_tools_shape():
    cand = [{"title": "A", "summary": "aaa"}]
    messages, tools = prompts.build_messages_and_tools("dragoste", cand)
    assert isinstance(messages, list) and len(messages) >= 2
    assert isinstance(tools, list) and tools[0]["function"]["name"] == "get_summaries_by_titles"
    assert "Candidates" in messages[1]["content"]
