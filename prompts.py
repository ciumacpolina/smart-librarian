# prompts.py
from typing import List, Dict, Tuple
import json as pyjson

def build_messages_and_tools(query: str, candidates: List[Dict]) -> Tuple[list, list]:
    """
    Planner + executor într-o singură rundă:
    - Modelul selectează titlurile exclusiv din candidați.
    - Dacă utilizatorul cere 1 carte (ex. 'o singura carte', 'doar una', 'one book', 'single', 'exactly one'),
      trebuie să returneze STRICT UN singur titlu.
    - Altfel, returnează o listă scurtă de 1–3 titluri (fără umplutură).
    - Apelează EXACT O DATĂ tool-ul get_summaries_by_titles cu lista finală de titluri selectate.
    - La final, inserează VERBATIM (fără parafrazare) rezumatul extins primit de la tool.
    """

    system_msg = (
        "You are Smart Librarian — a focused book-recommendation assistant. "
        "Use ONLY the provided CANDIDATES (title + short summary). Do not invent facts.\n\n"

        "LANGUAGE: Always reply in English. Keep book titles exactly as written.\n\n"

        "CIVILITY: If the user's message contains insults/harassment/profanity/hate speech, "
        "answer exactly: 'Please rephrase respectfully.' and stop.\n\n"

        "SELECTION RULES (VERY IMPORTANT):\n"
        "1) If the user EXPLICITLY asks for ONE book , "
        "you MUST return EXACTLY ONE title — never more than one.\n"
        "2) If the user gives a number, return exactly that many "
        "titles (respect the number), but never exceed 3 unless they explicitly ask for a higher number.\n"
        "3) If the quantity is unspecified, return a SHORT list of 1–3 strong matches (avoid padding with weak choices).\n"
        "4) NEVER list more titles than the user asked for. If in doubt, prefer ONE.\n\n"

        "MANDATORY TOOL CALL:\n"
        "- After you decide the final list of title(s), you MUST call the tool 'get_summaries_by_titles' "
        "EXACTLY ONCE with that list (even if it has only one title).\n"
        "- Wait for the tool result and ONLY THEN produce your final answer.\n"
        "- The tool returns a JSON map {title: full_extended_summary}. For each recommended title, "
        "paste the value for that title VERBATIM under 'Summary:'.\n"
        "- Do NOT paraphrase or translate tool content. Do NOT add 'Extended summary' labels.\n\n"

        "OUTPUT FORMAT (repeat the block for each recommended title, but NEVER exceed the requested count):\n"
        "**<Title>**\n"
        "Why this book?\n"
        "- <2–3 short reasons based only on the candidate summary>\n"
        "Summary:\n"
        "<paste here the exact extended summary from the tool for this title>\n"
        "If a title has no extended summary (NOT_FOUND or missing), omit the 'Summary:' section for that title."

        "SPECIAL CASE — ABOUT A TITLE:\n"
        "- If the user only asks what a specific candidate title is about, "
        "output ONLY:\n"
        "  **<Title>**\n"
        "  Summary:\n"
        "  <verbatim extended summary from the tool>\n"
        "  (Do NOT include 'Why this book?' in this case.)"
    )

    # Transmitem explicit candidații + query; modelul va infere intenția de cantitate
    user_prompt = (
        "TASK\n"
        "Choose book recommendations strictly from these candidates, then call the tool ONCE to fetch full summaries "
        "for ALL selected titles. Finally, format the answer exactly as requested.\n\n"
        "CANDIDATES (JSON with 'title' and 'summary'):\n"
        f"{pyjson.dumps(candidates, ensure_ascii=False, indent=2)}\n\n"
        "USER MESSAGE:\n"
        f"{query}\n\n"
        "REMEMBER:\n"
        "- If the user asked for ONE book , "
        "return EXACTLY ONE title.\n"
        "- Never output more titles than requested."
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
                            "description": "Exact book titles, exactly as in candidates (case-sensitive)."
                        }
                    },
                    "required": ["titles"]
                }
            }
        }
    ]

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user",   "content": user_prompt},
    ]
    return messages, tools
