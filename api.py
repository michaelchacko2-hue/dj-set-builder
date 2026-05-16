"""
DJ Set Builder API — Phase 5
FastAPI web service that wraps the DJ agent into HTTP endpoints.

Setup:
    pip3 install fastapi uvicorn

    Make sure your ANTHROPIC_API_KEY is set:
    export ANTHROPIC_API_KEY="sk-ant-..."

Run:
    uvicorn api:app --reload

    Then open: http://localhost:8000/docs

Endpoints:
    POST /chat          — Talk to the DJ agent (free-form)
    POST /build-set     — Build a setlist (structured)
    POST /transitions   — Find transitions from a track
    POST /search        — Search library by vibe
    GET  /stats         — Library statistics
    GET  /health        — Health check
"""

import os
import sys
import json
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException, Depends, Header
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    from pydantic import BaseModel
except ImportError:
    print("❌ Missing dependencies. Run: pip3 install fastapi uvicorn")
    sys.exit(1)

import anthropic

# ── Import your existing modules ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

from vibe_search import search as vibe_search, CHROMA_PATH
from camelot import (
    find_transitions as camelot_find_transitions,
    score_transition,
    key_to_camelot,
    find_track_by_name,
    load_library,
    CAMELOT_TO_KEY,
)

import chromadb

# ── Load everything once at startup ──
LIBRARY_TRACKS = load_library()
CHROMA_CLIENT = chromadb.PersistentClient(path=CHROMA_PATH)
COLLECTION = CHROMA_CLIENT.get_collection("dj_library")


# ═══════════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════════

app = FastAPI(
    title="DJ Set Builder API",
    description="AI-powered DJ assistant that searches your library by vibe, "
                "finds harmonic transitions, and builds setlists.",
    version="1.0.0",
)

# Allow frontend to connect from any origin (we'll lock this down in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Auth: protect endpoints that cost money ──
# Set this env var to require a password: export DJ_API_KEY="your-secret-password"
DJ_API_KEY = os.environ.get("DJ_API_KEY")

def verify_api_key(x_api_key: str = Header(default="")):
    """Check API key on endpoints that call Claude (costs money)."""
    if DJ_API_KEY and x_api_key != DJ_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True

# ── Serve frontend ──
STATIC_DIR = os.path.join(SCRIPT_DIR, "static")

@app.get("/")
def serve_frontend():
    """Serve the frontend UI."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "DJ Set Builder API. See /docs for endpoints."}


# ═══════════════════════════════════════════════════════════════
# REQUEST / RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    history: Optional[list] = []

class ChatResponse(BaseModel):
    response: str
    tool_calls: Optional[list] = []

class BuildSetRequest(BaseModel):
    description: str
    num_tracks: Optional[int] = 8
    starting_bpm: Optional[float] = None

class SearchRequest(BaseModel):
    query: str
    n_results: Optional[int] = 10

class TransitionRequest(BaseModel):
    track_name: str
    top_n: Optional[int] = 8

class TrackResult(BaseModel):
    artist: str
    title: str
    bpm: Optional[float] = None
    key: Optional[str] = None
    camelot: Optional[str] = None
    energy: Optional[str] = None
    brightness: Optional[str] = None
    feel: Optional[str] = None

class TransitionResult(BaseModel):
    track: TrackResult
    score: int
    grade: str
    details: list[str]

class SetlistResult(BaseModel):
    tracks: list[TrackResult]
    transitions: list[dict]
    total_duration_minutes: int


# ═══════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def track_to_result(track) -> TrackResult:
    """Convert a library track dict to a TrackResult."""
    af = track.get('audio_features', {})
    return TrackResult(
        artist=track.get('artist') or 'Unknown',
        title=track.get('title') or track.get('filename', 'Unknown'),
        bpm=float(track['bpm']) if track.get('bpm') else None,
        key=track.get('key'),
        camelot=key_to_camelot(track.get('key')),
        energy=af.get('energy_label') if af and '_error' not in af else None,
        brightness=af.get('brightness_label') if af and '_error' not in af else None,
        feel=af.get('percussiveness_label') if af and '_error' not in af else None,
    )


# ═══════════════════════════════════════════════════════════════
# AGENT (reused from dj_agent.py)
# ═══════════════════════════════════════════════════════════════

# Import tool definitions and runners from dj_agent
from dj_agent import TOOLS, TOOL_RUNNERS, SYSTEM_PROMPT

def run_agent_turn(client, messages):
    """Run one agent turn with tool calling loop."""
    tool_calls_log = []

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input

                    runner = TOOL_RUNNERS.get(tool_name)
                    if runner:
                        try:
                            result = runner(tool_input)
                        except Exception as e:
                            result = f"Error: {str(e)}"
                    else:
                        result = f"Unknown tool: {tool_name}"

                    tool_calls_log.append({
                        "tool": tool_name,
                        "input": tool_input,
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})
        else:
            text_parts = [block.text for block in response.content if hasattr(block, 'text')]
            final_text = "\n".join(text_parts)
            return final_text, tool_calls_log


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "tracks_loaded": len(LIBRARY_TRACKS),
        "chromadb_connected": True,
    }


@app.get("/stats")
def library_stats():
    """Get library statistics."""
    total = len(LIBRARY_TRACKS)
    bpms = [float(t['bpm']) for t in LIBRARY_TRACKS if t.get('bpm')]
    
    genres = {}
    energy_counts = {'low': 0, 'medium': 0, 'high': 0}
    key_counts = {}

    for t in LIBRARY_TRACKS:
        g = t.get('genre')
        if g:
            genres[g] = genres.get(g, 0) + 1
        af = t.get('audio_features', {})
        if af and '_error' not in af:
            label = af.get('energy_label', '')
            if label in energy_counts:
                energy_counts[label] += 1
        k = key_to_camelot(t.get('key'))
        if k:
            key_counts[k] = key_counts.get(k, 0) + 1

    return {
        "total_tracks": total,
        "bpm_range": {"min": min(bpms), "max": max(bpms), "avg": round(sum(bpms) / len(bpms), 1)} if bpms else None,
        "energy_breakdown": energy_counts,
        "top_genres": dict(sorted(genres.items(), key=lambda x: x[1], reverse=True)[:10]),
        "top_keys": dict(sorted(key_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
    }


@app.post("/search")
def search_library(req: SearchRequest):
    """Search the library by vibe description."""
    results = vibe_search(req.query, collection=COLLECTION, n_results=req.n_results)

    if not results['ids'][0]:
        return {"tracks": [], "message": "No matching tracks found."}

    tracks = []
    for meta, distance in zip(results['metadatas'][0], results['distances'][0]):
        tracks.append({
            "artist": meta.get('artist', 'Unknown'),
            "title": meta.get('title', 'Unknown'),
            "bpm": meta.get('bpm'),
            "key": meta.get('key'),
            "camelot": key_to_camelot(meta.get('key', '')),
            "energy": meta.get('energy'),
            "brightness": meta.get('brightness'),
            "feel": meta.get('feel'),
            "relevance": round((1 - distance) * 100, 1),
        })

    return {"tracks": tracks, "query": req.query}


@app.post("/transitions")
def find_transitions(req: TransitionRequest):
    """Find the best transitions from a specific track."""
    matches = find_track_by_name(LIBRARY_TRACKS, req.track_name)

    if not matches:
        raise HTTPException(status_code=404, detail=f"Track '{req.track_name}' not found in library.")

    source = matches[0]
    transitions = camelot_find_transitions(source, LIBRARY_TRACKS, top_n=req.top_n)

    return {
        "source": track_to_result(source).model_dump(),
        "transitions": [
            {
                "track": track_to_result(t['track']).model_dump(),
                "score": t['score'],
                "grade": t['grade'],
                "details": t['details'],
            }
            for t in transitions
        ],
    }


@app.post("/build-set")
def build_set(req: BuildSetRequest):
    """Build an ordered setlist."""
    results = vibe_search(req.description, collection=COLLECTION, n_results=min(req.num_tracks * 3, 30))

    if not results['ids'][0]:
        raise HTTPException(status_code=404, detail="No matching tracks found for that description.")

    # Build candidates
    candidates = []
    seen = set()
    for meta in results['metadatas'][0]:
        matches = find_track_by_name(LIBRARY_TRACKS, f"{meta.get('artist', '')} {meta.get('title', '')}")
        if matches:
            fp = matches[0].get('filepath', '')
            if fp not in seen:
                candidates.append(matches[0])
                seen.add(fp)

    if not candidates:
        raise HTTPException(status_code=404, detail="Could not match tracks to library.")

    # Sort by starting BPM if provided
    if req.starting_bpm:
        candidates.sort(key=lambda t: abs(float(t.get('bpm') or 999) - req.starting_bpm))

    # Greedy setlist builder
    setlist = [candidates.pop(0)]
    while len(setlist) < req.num_tracks and candidates:
        current = setlist[-1]
        best_score = -999
        best_idx = 0
        recent_artists = [t.get('artist', '') for t in setlist[-3:]]
        for i, candidate in enumerate(candidates):
            result = score_transition(current, candidate, recent_artists=recent_artists)
            if result['score'] > best_score:
                best_score = result['score']
                best_idx = i
        setlist.append(candidates.pop(best_idx))

    # Build response with transition info
    tracks_out = [track_to_result(t).model_dump() for t in setlist]
    transitions_out = []
    total_duration = 0

    for i, track in enumerate(setlist):
        total_duration += track.get('duration_seconds', 0)
        if i < len(setlist) - 1:
            t = score_transition(track, setlist[i + 1])
            transitions_out.append({
                "from_index": i,
                "to_index": i + 1,
                "score": t['score'],
                "grade": t['grade'],
                "details": t['details'],
            })

    return {
        "description": req.description,
        "tracks": tracks_out,
        "transitions": transitions_out,
        "total_duration_minutes": int(total_duration // 60),
    }


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest, _auth: bool = Depends(verify_api_key)):
    """Free-form chat with the DJ agent."""
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set on server.")

    client = anthropic.Anthropic(api_key=api_key)

    # Build messages from history
    messages = []
    for msg in (req.history or []):
        messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    messages.append({"role": "user", "content": req.message})

    try:
        response_text, tool_calls = run_agent_turn(client, messages)
        return ChatResponse(response=response_text, tool_calls=tool_calls)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════
# RUN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    print(f"\n🎧 DJ Set Builder API")
    print(f"{'='*50}")
    print(f"Loaded {len(LIBRARY_TRACKS)} tracks")
    print(f"Docs: http://localhost:8000/docs\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
