import os
from dotenv import load_dotenv
load_dotenv()

# === Paths & models ===
BOOKS_PATH = "books.json"            # small DB: title, summary(short), themes
BOOKS_EXT_PATH = "books_ext.json"    # extended DB: title, summary(long)
PERSIST_DIR = "chroma_db"
COLLECTION_NAME = "books"

EMB_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o-mini"
TOP_K = 7  # give the LLM a few strong options

# === OpenAI client (SDK v1) ===
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("OPENAI_API_KEY is missing. Put it in .env or environment.")

# --- TTS defaults (add these lines somewhere after you create `client`) ---
# Modelul TTS (poți schimba din .env dacă vrei)
TTS_MODEL = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")

# Vocea implicită (poți schimba din .env)
TTS_DEFAULT_VOICE = os.getenv("TTS_DEFAULT_VOICE", "alloy")

# Formatul audio returnat
TTS_DEFAULT_FORMAT = os.getenv("TTS_DEFAULT_FORMAT", "mp3")
