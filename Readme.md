# 📚 Smart Librarian

> **A modern AI-powered book recommendation chatbot with summaries, TTS/STT, and animated bookshelf UI.**

![Python](https://img.shields.io/badge/python-3.9%2B-blue?logo=python)
![Flask](https://img.shields.io/badge/flask-%20web%20app-lightgrey?logo=flask)
![OpenAI](https://img.shields.io/badge/openai-embeddings%20%7C%20chat-green?logo=openai)
![ChromaDB](https://img.shields.io/badge/chromadb-vector%20store-orange?logo=databricks)

---

## ✨ Features

- **Semantic Book Search:** Finds relevant books by theme, genre, or keywords using OpenAI embeddings.
- **Conversational Chatbot:** Natural language chat, intent detection, and moderation.
- **Text-to-Speech & Speech-to-Text:** Listen to answers or dictate questions.
- **Image Generation:** Create book cover illustrations for recommendations.
- **Animated Bookshelf UI:** Modern, responsive, and visually appealing interface.
- **Automatic Moderation:** Filters offensive or irrelevant messages.

---

## 🚀 Quickstart

```bash
git clone https://github.com/username/book_chatbot.git
cd book_chatbot

# Add your OpenAI key in a .env file
echo "OPENAI_API_KEY=sk-..." > .env

pip install -r requirements.txt
python web.py
```

Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser.

---

## 🗂️ Project Structure

```
book_chatbot/
│
├── config.py           # Configuration, API keys, model names
├── web.py              # Flask server, main routes
├── rag.py              # Book loading, embeddings, vector search
├── prompts.py          # LLM prompts, selection/formatting rules
├── helpers.py          # Utilities, moderation, reply cleaning
├── routes_media.py     # TTS, STT, image generation endpoints
│
├── data/
│   ├── books.json      # Main book database (title, summary, themes)
│   └── books_ext.json  # Extended summaries
│
├── static/
│   ├── css/style.css
│   └── js/
│       ├── app.js
│       └── bookshelf-bg.js
│
├── templates/
│   └── index.html      # Main web UI
│
├── requirements.txt
└── .env                # Your OpenAI API key (not in git)
```

---

## 🧠 How Embedding is Used

- Each book in `data/books.json` is embedded into a semantic vector using OpenAI.
- User queries are also embedded.
- ChromaDB performs vector similarity search to find the most relevant books, even for fuzzy or thematic queries.
- This enables smart, context-aware recommendations beyond keyword matching.

---

## 💡 Example Usage

- **User:** `Recommend a fantasy book about friendship`
- **Bot:** Suggests 1–3 relevant titles, each with a full extended summary and reasons for recommendation.
- **Extras:** Click 🖼️ to generate a cover, 🔊 to listen, or use 🎙️ to dictate your query.

---

## ⚙️ Requirements

- Python 3.9+
- OpenAI API key (`OPENAI_API_KEY`)
- (Optional) ChromaDB for local vector store

---

## 📖 Add More Books

- Edit `data/books.json` to add new books (title, summary, themes).
- Optionally, add extended summaries in `data/books_ext.json`.

---

## 📝 License

MIT License

---

> Made with ❤️ for book lovers and AI enthusiasts.