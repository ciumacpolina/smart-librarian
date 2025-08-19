import os
import re
import json
import unicodedata
from typing import List, Dict

import chromadb
from chromadb.utils import embedding_functions

from config import (
    BOOKS_PATH, BOOKS_EXT_PATH, PERSIST_DIR,
    COLLECTION_NAME, EMB_MODEL, CHAT_MODEL, TOP_K, client
)

# ---------- helpers ----------

def parse_json_safe(text: str):
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None

def strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

def normalize_text(s: str) -> str:
    s = strip_diacritics(s).lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

# ---------- LLM augmentation (no hardcoded synonyms) ----------

def llm_expand_theme_vocab(unique_themes: List[str], per_theme_max: int = 3) -> Dict[str, List[str]]:
    if not unique_themes:
        return {}
    system = (
        "Expand each short theme tag into up to "
        f"{per_theme_max} near-synonyms or closely related terms, English only. "
        "Return STRICT JSON mapping the exact input theme to a list of short terms. "
        "Do not introduce new themes or titles."
    )
    user = {"themes": unique_themes}
    try:
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)}
            ],
            temperature=0.0
        )
        data = parse_json_safe(resp.choices[0].message.content.strip()) or {}
        out = {}
        for t in unique_themes:
            vals = data.get(t, [])
            out[t] = [
                str(v).strip() for v in vals
                if isinstance(v, (str, int, float)) and str(v).strip()
            ]
        return out
    except Exception:
        return {t: [] for t in unique_themes}

def llm_expand_query(query: str, max_terms: int = 10) -> List[str]:
    system = (
        "Rewrite the user's query into English retrieval terms ONLY. "
        f"Return STRICT JSON: {{\"english_keywords\": [up to {max_terms} short terms]}}. "
        "Use single words or very short phrases. No book titles unless explicitly mentioned. No outside facts."
    )
    user = {"query": query}
    try:
        resp = client.chat.completions.create(
            model=CHAT_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)}
            ],
            temperature=0.0
        )
        data = parse_json_safe(resp.choices[0].message.content.strip()) or {}
        terms = data.get("english_keywords", [])
        if not isinstance(terms, list):
            return []
        out = []
        for t in terms:
            s = str(t).strip()
            if s and len(s) <= 40:
                out.append(s)
        return out[:max_terms]
    except Exception:
        return []

# ---------- Data loading & Chroma (small DB) ----------

def load_books(path: str = BOOKS_PATH) -> List[Dict]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Can't find {path}. Create a 'books.json' file.")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for i, b in enumerate(data):
        for key in ("title", "summary", "themes"):
            if key not in b:
                raise ValueError(f"Book #{i} is missing required key: {key}")
    return data

def load_books_ext(path: str = BOOKS_EXT_PATH) -> List[Dict]:
    """Extended DB: list of {title, summary(long)}. Optional file."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for i, b in enumerate(data):
        for key in ("title", "summary"):
            if key not in b:
                raise ValueError(f"[EXT] Book #{i} is missing required key: {key}")
    return data

def build_vector_store(books: List[Dict]):
    os.makedirs(PERSIST_DIR, exist_ok=True)
    client_chroma = chromadb.PersistentClient(path=PERSIST_DIR)
    try:
        client_chroma.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass

    embedder = embedding_functions.OpenAIEmbeddingFunction(
        api_key=client.api_key,
        model_name=EMB_MODEL
    )
    collection = client_chroma.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedder,
        metadata={"hnsw:space": "cosine"}
    )

    unique_themes = sorted({t for b in books for t in b.get("themes", [])})
    theme_syn_map = llm_expand_theme_vocab(unique_themes, per_theme_max=3)

    documents, metadatas, ids = [], [], []
    for idx, b in enumerate(books):
        title = b["title"]
        themes = [str(t) for t in b.get("themes", [])]
        syns = []
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

def extract_summary(doc_text: str) -> str:
    for line in doc_text.splitlines():
        if line.startswith("Summary:"):
            return line.replace("Summary:", "").strip()
    return doc_text

def retrieve_candidates(collection, query: str, k: int = TOP_K) -> List[Dict]:
    res = collection.query(
        query_texts=[query],
        n_results=k,
        include=["documents", "metadatas", "distances"]
    )
    docs = res["documents"][0]
    metas = res["metadatas"][0]
    dists = res["distances"][0]
    out = []
    for i in range(len(docs)):
        out.append({
            "title": metas[i]["title"],
            "summary": extract_summary(docs[i]),
            "score": float(dists[i])
        })
    return out
