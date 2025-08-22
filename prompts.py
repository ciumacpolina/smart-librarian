from typing import List, Dict, Tuple
import json as pyjson

def build_messages_and_tools(query: str, candidates: List[Dict]) -> Tuple[list, list]:
    """
    Build system/user messages and the single tool schema for the chat call.
    Planner + executor in one round with an enforced single tool call.
    """
    system_msg = (
        "You are Smart Librarian — a focused book-recommendation assistant. "
        "Use ONLY the provided candidates (title + short summary). Do not invent facts.\n\n"
        "Language:\n"
        "- Always reply in English.\n"
        "- Keep book titles exactly as written.\n\n"
        "Civility:\n"
        "- If the user's message contains insults/harassment/profanity/hate speech, "
        "reply exactly: 'Please rephrase respectfully.' and stop.\n\n"
        "Selection rules (very important):\n"
        "1) If the user explicitly asks for ONE book, return exactly one title.\n"
        "2) If the user gives a number N, return exactly N titles.\n"
        "3) If the user explicitly requests an UNBOUNDED quantity (e.g., 'more', 'all', 'as many as possible'), "
        "return EVERY relevant candidate — do NOT cap the count.\n"
        "4) If quantity is unspecified (no number and no unbounded request), return a short list of 1–3 strong matches.\n"
        "5) Never return more titles than requested, except when rule #3 applies (unbounded request).\n\n"
        "Mandatory tool call:\n"
        "- After deciding the final list of titles, call the tool 'get_summaries_by_titles' EXACTLY ONCE with that list "
        "(even if it contains many titles). Wait for the tool result before producing the final answer.\n"
        "- The tool returns a JSON map {title: full_extended_summary}. For each recommended title, paste the value "
        "verbatim under 'Summary:'. Do not paraphrase or translate tool content. Do not add extra labels.\n\n"
        "Output format (repeat the block for each recommended title; if many, repeat for all):\n"
        "**<Title>**\n"
        "Why this book?\n"
        "- <2–3 short reasons based only on the candidate summary>\n"
        "Summary:\n"
        "<paste here the exact extended summary from the tool>\n"
        "If a title has no extended summary (NOT_FOUND or missing), omit the 'Summary:' section for that title.\n\n"
        "Special case — about a single title:\n"
        "- If the user only asks what a specific candidate title is about, output ONLY:\n"
        "  **<Title>**\n"
        "  Summary:\n"
        "  <verbatim extended summary from the tool>\n"
        "  (Do NOT include 'Why this book?' in this case.)"
    )

    user_prompt = (
        "Task:\n"
        "Choose book recommendations strictly from these candidates, then call the tool ONCE to fetch full summaries "
        "for ALL selected titles. Finally, format the answer exactly as requested.\n\n"
        "Candidates (JSON with 'title' and 'summary'):\n"
        f"{pyjson.dumps(candidates, ensure_ascii=False, indent=2)}\n\n"
        "User message:\n"
        f"{query}\n\n"
        "Remember:\n"
        "- If the user asked for ONE book, return EXACTLY ONE.\n"
        "- If the user asked for a number N, return EXACTLY N.\n"
        "- If the user asked for an UNBOUNDED quantity (e.g., 'more', 'all', 'as many as possible'), return EVERY relevant candidate.\n"
        "- If quantity is unspecified, return 1–3 strong matches."
    )

    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_summaries_by_titles",
                "description": "Return a JSON map {title: full_extended_summary} for all requested titles.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "titles": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Exact book titles as they appear in candidates (case-sensitive).",
                        }
                    },
                    "required": ["titles"],
                },
            },
        }
    ]

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_prompt},
    ]
    return messages, tools
