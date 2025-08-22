from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Dict, List

import chromadb
from chromadb.utils import embedding_functions

from config import (
    BOOKS_PATH,
    BOOKS_EXT_PATH,
    PERSIST_DIR,
    COLLECTION_NAME,
    EMB_MODEL,
    CHAT_MODEL,
    TOP_K,
    client,
)


# --------------------------- small utilities ---------------------------

def parse_json_safe(text: str):
    """
    Best-effort JSON parse.
    Tries full parse first; if it fails, extracts the first {...} block.
    Returns dict/list on success, or None on failure.
    """
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text or "")
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def strip_diacritics(s: str) -> str:
    """Remove diacritics for robust, language-agnostic matching."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


def normalize_text(s: str) -> str:
    """Lowercase, remove diacritics and non-alphanumerics, collapse whitespace."""
    s = strip_diacritics(s).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# --------------------------- LLM augmentation ---------------------------

def llm_expand_theme_vocab(unique_themes: List[str], per_theme_max: int = 3) -> Dict[str, List[str]]:
    """
    Ask the model for up to `per_theme_max` near-synonyms per theme.
    Returns a mapping for all input themes. On failure, returns empty lists.
    """
    if not unique_themes:
        return {}

    system = (
        "Expand each short theme tag into up to "
        f"{per_theme_max} near-synonyms or closely related terms, English only. "
        "Return STRICT JSON mapping the exact input theme to a list of short terms."
    )
    user = {"themes": unique_themes}

    try:
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.0,
        )
        data = parse_json_safe((resp.choices[0].message.content or "").strip()) or {}
    except Exception:
        data = {}

    out: Dict[str, List[str]] = {}
    for t in unique_themes:
        vals = data.get(t, [])
        out[t] = [
            str(v).strip()
            for v in (vals if isinstance(vals, list) else [])
            if isinstance(v, (str, int, float)) and str(v).strip()
        ][:per_theme_max]
    return out


def llm_expand_query(query: str, max_terms: int = 10) -> List[str]:
    """
    Ask the model to rewrite the query into up to `max_terms` short English retrieval terms.
    Returns a list; on failure, returns [].
    """
    system = (
        "Rewrite the user's query into English retrieval terms ONLY. "
        f"Return STRICT JSON: {{\"english_keywords\": [up to {max_terms} short terms]}}. "
        "Use single words or very short phrases. No outside facts."
    )
    user = {"query": query}

    try:
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            temperature=0.0,
        )
        data = parse_json_safe((resp.choices[0].message.content or "").strip()) or {}
        terms = data.get("english_keywords", [])
    except Exception:
        terms = []

    if not isinstance(terms, list):
        return []

    out: List[str] = []
    for t in terms:
        s = str(t).strip()
        if s and len(s) <= 40:
            out.append(s)
    return out[:max_terms]


# --------------------------- loading & vector store ---------------------------

def load_books(path: str | os.PathLike = BOOKS_PATH) -> List[Dict]:
    """
    Load the small DB: list of {title, summary, themes}.
    Validates required keys; raises on missing file or malformed entries.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Can't find {path}. Create a 'books.json' file.")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("books.json should contain a list of objects.")

    for i, b in enumerate(data):
        for key in ("title", "summary", "themes"):
            if key not in b:
                raise ValueError(f"Book #{i} is missing required key: {key}")
    return data


def load_books_ext(path: str | os.PathLike = BOOKS_EXT_PATH) -> List[Dict]:
    """
    Load the extended DB: list of {title, summary(long)}.
    Optional file: returns [] if missing. Validates required keys if present.
    """
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("books_ext.json should contain a list of objects.")

    for i, b in enumerate(data):
        for key in ("title", "summary"):
            if key not in b:
                raise ValueError(f"[EXT] Book #{i} is missing required key: {key}")
    return data


def build_vector_store(books: List[Dict]):
    """
    Build a persistent Chroma collection and populate it with book documents.
    Recreates the collection each run.
    """
    os.makedirs(PERSIST_DIR, exist_ok=True)
    client_chroma = chromadb.PersistentClient(path=str(PERSIST_DIR))

    try:
        client_chroma.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass

    try:
        embedder = embedding_functions.OpenAIEmbeddingFunction(
            api_key=client.api_key,
            model_name=EMB_MODEL,
        )
    except Exception as e:
        raise RuntimeError(f"Failed to create OpenAI embedding function: {e!r}")

    collection = client_chroma.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedder,
        metadata={"hnsw:space": "cosine"},
    )

    unique_themes = sorted({t for b in books for t in b.get("themes", [])})
    theme_syn_map = llm_expand_theme_vocab(unique_themes, per_theme_max=3)

    documents: List[str] = []
    metadatas: List[Dict] = []
    ids: List[str] = []

    for idx, b in enumerate(books):
        title = b["title"]
        themes = [str(t) for t in b.get("themes", [])]

        syns: List[str] = []
        for t in themes:
            syns.extend(theme_syn_map.get(t, []))
        syns = [s for s in syns if s]

        doc_text = (
            f"Title: {title}\n"
            f"Themes: {', '.join(themes)}\n"
            f"ThemeSynonyms: {', '.join(syns)}\n"
            f"ThemesBoost: {', '.join(themes)} {', '.join(syns)}\n"
            f"Summary: {b['summary']}"
        )

        documents.append(doc_text)
        metadatas.append({"title": title})
        ids.append(f"book-{idx}")

    collection.add(documents=documents, metadatas=metadatas, ids=ids)
    return collection


# --------------------------- retrieval helpers ---------------------------

def _extract_summary_from_doc(doc_text: str) -> str:
    """
    Robustly extract the text after 'Summary:' (case-insensitive), allowing a newline
    right after the label, e.g. 'Summary:\\nS1'. If no label found, return the whole doc.
    """
    if not doc_text:
        return ""
    parts = re.split(r'(?is)\bsummary\s*:\s*', doc_text, maxsplit=1)
    if len(parts) == 2:
        return parts[1].strip()
    return doc_text.strip()

def extract_summary(doc_text: str) -> str:
    return _extract_summary_from_doc(doc_text)


def retrieve_candidates(collection, query: str, k: int = TOP_K) -> List[Dict]:
    """
    Query the vector store and return a list of {title, summary, score}.
    Returns [] if nothing is found.
    """
    res = collection.query(
        query_texts=[query],
        n_results=k,
        include=["documents", "metadatas", "distances"],
    )

    if not res or not res.get("documents"):
        return []

    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]

    out: List[Dict] = []
    for i in range(min(len(docs), len(metas), len(dists))):
        meta = metas[i] or {}
        out.append(
            {
                "title": meta.get("title", ""),
                "summary": extract_summary(docs[i] or ""),
                "score": float(dists[i]),
            }
        )
    return out
