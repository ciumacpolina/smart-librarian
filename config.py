from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Load environment 
load_dotenv()

# --- Paths ---
BASE: Path = Path(__file__).parent
DATA_DIR: Path = BASE / "data"
STATIC_DIR: Path = BASE / "static"

BOOKS_PATH: Path = DATA_DIR / "books.json"         
BOOKS_EXT_PATH: Path = DATA_DIR / "books_ext.json" 
PERSIST_DIR: Path = BASE / "chroma_db"             
COLLECTION_NAME: str = "books"

# Static output folders used by media routes
GENERATED_IMAGES_DIR: Path = STATIC_DIR / "gen"
GENERATED_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

STATIC_AUDIO_DIR: Path = STATIC_DIR / "audio"
STATIC_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# --- Model & tuning defaults ---
EMB_MODEL: str  = os.getenv("EMB_MODEL", "text-embedding-3-small")
CHAT_MODEL: str = os.getenv("CHAT_MODEL", "gpt-4o-mini")
GATE_MODEL: str = os.getenv("GATE_MODEL", "gpt-4o")  # intent/insult gates

TOP_K: int = int(os.getenv("TOP_K", "7"))

# TTS
TTS_MODEL: str          = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
TTS_DEFAULT_VOICE: str  = os.getenv("TTS_DEFAULT_VOICE", "alloy")
TTS_DEFAULT_FORMAT: str = os.getenv("TTS_DEFAULT_FORMAT", "mp3")

# Image generation
IMG_MODEL: str           = os.getenv("IMG_MODEL", "gpt-image-1")
IMG_DEFAULT_SIZE: str    = os.getenv("IMG_DEFAULT_SIZE", "1024x1024")  
IMG_DEFAULT_QUALITY: str = os.getenv("IMG_DEFAULT_QUALITY", "low")     

# --- OpenAI client ---
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("OPENAI_API_KEY is missing. Set it in your environment or in a .env file.")

client = OpenAI(api_key=api_key)
