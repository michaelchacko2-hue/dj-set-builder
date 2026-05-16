# 🎧 DJ Set Builder Agent

An AI-powered DJ assistant that searches your music library by vibe, finds harmonically compatible transitions using Camelot wheel logic, and builds complete setlists — powered by Claude, ChromaDB, and Librosa audio analysis.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Claude](https://img.shields.io/badge/AI-Claude%20Sonnet%204.6-blueviolet)
![ChromaDB](https://img.shields.io/badge/Vector%20DB-ChromaDB-orange)
![FastAPI](https://img.shields.io/badge/API-FastAPI-green)

## What It Does

- **Vibe Search** — Search your library with natural language: "dark minimal techno around 126 BPM" or "funky disco for warming up"
- **Harmonic Mixing** — Scores transitions between tracks using Camelot wheel compatibility, BPM matching, and energy flow
- **Setlist Builder** — Generates ordered setlists with smooth transitions, energy arcs, and BPM progression
- **AI Agent** — Chat naturally with Claude, which decides which tools to call and chains them together

## Architecture

```
You ──→ Chat UI ──→ FastAPI ──→ Claude (Sonnet 4.6)
                                   │
                          ┌────────┴────────┐
                          ▼                  ▼
                    search_library     find_transitions
                          │                  │
                    ChromaDB             Camelot Module
                    (vector search)      (key + BPM + energy)
                          │                  │
                          └────────┬─────────┘
                                   ▼
                             library.json
                        (ID3 tags + Librosa features)
```

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| AI Agent | Claude Sonnet 4.6 (Anthropic SDK) | Natural language reasoning + tool orchestration |
| Vector Database | ChromaDB | Semantic search over track descriptions |
| Audio Analysis | Librosa | Energy, brightness, percussiveness extraction |
| Metadata | Mutagen | ID3 tag reading (BPM, key, genre) |
| Harmonic Logic | Custom Camelot module | Key compatibility + transition scoring |
| API | FastAPI | RESTful endpoints |
| Frontend | Vanilla HTML/CSS/JS | Chat interface with setlist rendering |
| Containerization | Docker | One-command deployment |

## How It Works

### 1. Library Scanning
`scan_library.py` reads ID3 metadata from every audio file (BPM, key, artist, genre). `analyze_library.py` uses Librosa to extract audio features — energy (RMS), brightness (spectral centroid), and percussiveness (onset strength) — and normalizes them to human-readable labels.

### 2. Vector Embeddings
`vibe_search.py` generates text descriptions for each track combining metadata + audio labels + vibe words, then stores them in ChromaDB. Searches use cosine similarity over embeddings from the all-MiniLM-L6-v2 model.

### 3. Camelot Mixing Logic
`camelot.py` maps musical keys to Camelot codes and scores transitions on three dimensions:
- **Key compatibility** (40 pts): Same key, ±1 on wheel, major/minor switch
- **BPM closeness** (30 pts): Including half/double time detection
- **Energy flow** (30 pts): Smooth, building, or dropping

### 4. AI Agent
`dj_agent.py` exposes the above as tools that Claude can call. Claude reads tool descriptions, decides which to use, chains multiple calls, and synthesizes results into a coherent response.

## Run Locally

```bash
# Clone and install
git clone https://github.com/YOUR_USERNAME/dj-set-builder.git
cd dj-set-builder
pip install -r requirements.txt

# Scan your music library
python scan_library.py /path/to/your/music
python analyze_library.py
python vibe_search.py --rebuild

# Run the terminal agent
export ANTHROPIC_API_KEY="sk-ant-..."
python dj_agent.py

# Or run the web UI
export DJ_API_KEY="your-password"
python api.py
# Open http://localhost:8000
```

## Run with Docker

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export DJ_API_KEY="your-password"
docker compose up --build
```

## API Endpoints

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/health` | No | Health check |
| GET | `/stats` | No | Library statistics |
| POST | `/search` | No | Vibe-based search |
| POST | `/transitions` | No | Find compatible transitions |
| POST | `/build-set` | No | Build ordered setlist |
| POST | `/chat` | Yes | Free-form agent chat |

## Cost

- ChromaDB, Librosa, FastAPI: **Free** (runs locally)
- Claude API: **~$0.01–0.05 per chat message** (Sonnet 4.6)
- Typical monthly usage: **$2–5**

## License

MIT
