"""
DJ Set Builder Agent — Phase 4
An AI agent powered by Claude using native tool calling to build setlists,
find transitions, and search your library by vibe.

Setup:
    pip3 install anthropic

    Set your API key:
    export ANTHROPIC_API_KEY="sk-ant-..."

Run:
    python dj_agent.py

Then just talk to it:
    "Build me a 30-minute deep house set starting at 122 BPM"
    "What should I play after Daft Punk - Veridis Quo?"
    "Find me dark minimal tracks around 126 BPM"
"""

import os
import sys
import json

try:
    import anthropic
except ImportError:
    print("❌ Missing dependency. Run: pip3 install anthropic")
    sys.exit(1)

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

# ── Load library and ChromaDB once ──
LIBRARY_TRACKS = load_library()
CHROMA_CLIENT = chromadb.PersistentClient(path=CHROMA_PATH)
COLLECTION = CHROMA_CLIENT.get_collection("dj_library")


# ═══════════════════════════════════════════════════════════════
# TOOL DEFINITIONS — what Claude sees and can call
# ═══════════════════════════════════════════════════════════════

TOOLS = [
    {
        "name": "search_library",
        "description": "Search the DJ library by vibe description. Use natural language like 'dark driving techno around 126 BPM' or 'smooth deep house for warming up'. Returns matching tracks with BPM, key, and energy info.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language vibe description"},
                "n_results": {"type": "integer", "description": "Number of results (default 10)", "default": 10},
            },
            "required": ["query"],
        },
    },
    {
        "name": "find_compatible_transitions",
        "description": "Given a track name (artist and/or title), find the best tracks to play next based on Camelot key compatibility, BPM matching, and energy flow. Use when the user asks 'what should I play after X'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "track_name": {"type": "string", "description": "Artist and/or title to search for"},
                "top_n": {"type": "integer", "description": "Number of results (default 8)", "default": 8},
            },
            "required": ["track_name"],
        },
    },
    {
        "name": "find_transitions_by_key_bpm",
        "description": "Find tracks compatible with a specific Camelot key code and BPM. Use when building a setlist and you need the next track at a specific key/tempo. Camelot codes: 1A-12A (minor), 1B-12B (major).",
        "input_schema": {
            "type": "object",
            "properties": {
                "camelot_code": {"type": "string", "description": "Camelot code like 4A, 8B, etc."},
                "bpm": {"type": "number", "description": "Target BPM"},
                "top_n": {"type": "integer", "description": "Number of results (default 8)", "default": 8},
            },
            "required": ["camelot_code", "bpm"],
        },
    },
    {
        "name": "get_track_info",
        "description": "Look up detailed info about a specific track in the library. Returns BPM, key, Camelot code, energy, brightness, and percussiveness.",
        "input_schema": {
            "type": "object",
            "properties": {
                "track_name": {"type": "string", "description": "Artist and/or title to search for"},
            },
            "required": ["track_name"],
        },
    },
    {
        "name": "build_setlist",
        "description": "Build an ordered setlist from the library. Finds tracks matching the vibe, then orders them for smooth BPM and key flow. Use when the user asks to build a set or playlist.",
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "Vibe/genre description (e.g., 'deep house warm-up set')"},
                "num_tracks": {"type": "integer", "description": "How many tracks (default 8)", "default": 8},
                "starting_bpm": {"type": "number", "description": "Optional starting BPM to anchor the set"},
            },
            "required": ["description"],
        },
    },
    {
        "name": "preview_track",
        "description": "Generate a YouTube search URL to preview a track.",
        "input_schema": {
            "type": "object",
            "properties": {
                "artist": {"type": "string", "description": "Artist name"},
                "title": {"type": "string", "description": "Track title"},
            },
            "required": ["artist", "title"],
        },
    },
    {
        "name": "library_stats",
        "description": "Show overall statistics about the DJ library — total tracks, BPM range, top genres, energy breakdown, top keys.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
]


# ═══════════════════════════════════════════════════════════════
# TOOL IMPLEMENTATIONS
# ═══════════════════════════════════════════════════════════════

def run_search_library(query, n_results=10):
    results = vibe_search(query, collection=COLLECTION, n_results=n_results)

    if not results['ids'][0]:
        return "No matching tracks found. Try a broader description."

    output = []
    for meta, distance in zip(results['metadatas'][0], results['distances'][0]):
        relevance = round((1 - distance) * 100, 1)
        camelot = key_to_camelot(meta.get('key', '')) or '?'
        output.append(
            f"• {meta.get('artist', 'Unknown')} — {meta.get('title', 'Unknown')} "
            f"[BPM: {meta.get('bpm', '?')}, Key: {meta.get('key', '?')} ({camelot}), "
            f"Energy: {meta.get('energy', '?')}, Tone: {meta.get('brightness', '?')}, "
            f"Feel: {meta.get('feel', '?')}, Match: {relevance}%]"
        )

    return f"Found {len(output)} tracks:\n" + "\n".join(output)


def run_find_compatible_transitions(track_name, top_n=8):
    matches = find_track_by_name(LIBRARY_TRACKS, track_name)

    if not matches:
        return f"Could not find '{track_name}' in the library."

    source = matches[0]
    artist = source.get('artist') or 'Unknown'
    title = source.get('title') or source.get('filename', '?')
    bpm = source.get('bpm') or '?'
    key = source.get('key') or '?'
    camelot = key_to_camelot(key) or '?'

    transitions = camelot_find_transitions(source, LIBRARY_TRACKS, top_n=top_n)

    output = [f"Transitions from: {artist} — {title} [BPM: {bpm}, Key: {key} ({camelot})]\n"]
    for t in transitions:
        track = t['track']
        t_camelot = key_to_camelot(track.get('key', '')) or '?'
        details = "; ".join(t['details'])
        output.append(
            f"• [{t['grade']}] {track.get('artist', 'Unknown')} — {track.get('title', '?')} "
            f"[BPM: {track.get('bpm', '?')}, Key: {track.get('key', '?')} ({t_camelot}), "
            f"Score: {t['score']}/100] ({details})"
        )

    return "\n".join(output)


def run_find_transitions_by_key_bpm(camelot_code, bpm, top_n=8):
    code = camelot_code.upper().strip()
    if code not in CAMELOT_TO_KEY:
        return f"Invalid Camelot code: {code}. Use 1A-12A for minor, 1B-12B for major."

    virtual_track = {
        'key': CAMELOT_TO_KEY[code],
        'bpm': bpm,
        'audio_features': {'normalized': {'energy_mean': 0.5}},
    }

    transitions = camelot_find_transitions(virtual_track, LIBRARY_TRACKS, top_n=top_n)

    output = [f"Tracks compatible with {code} ({CAMELOT_TO_KEY[code]}) at {bpm} BPM:\n"]
    for t in transitions:
        track = t['track']
        t_camelot = key_to_camelot(track.get('key', '')) or '?'
        details = "; ".join(t['details'])
        output.append(
            f"• [{t['grade']}] {track.get('artist', 'Unknown')} — {track.get('title', '?')} "
            f"[BPM: {track.get('bpm', '?')}, Key: {track.get('key', '?')} ({t_camelot}), "
            f"Score: {t['score']}/100] ({details})"
        )

    return "\n".join(output)


def run_get_track_info(track_name):
    matches = find_track_by_name(LIBRARY_TRACKS, track_name)

    if not matches:
        return f"Could not find '{track_name}' in the library."

    output = []
    for track in matches[:5]:
        camelot = key_to_camelot(track.get('key', '')) or '?'
        dur = track.get('duration_seconds')
        dur_str = f"{int(dur)//60}:{int(dur)%60:02d}" if dur else '?'
        af = track.get('audio_features', {})

        output.append(
            f"• {track.get('artist', 'Unknown')} — {track.get('title', '?')}\n"
            f"  BPM: {track.get('bpm', '?')} | Key: {track.get('key', '?')} ({camelot}) | "
            f"Genre: {track.get('genre', '?')}\n"
            f"  Duration: {dur_str} | Energy: {af.get('energy_label', '?')} | "
            f"Tone: {af.get('brightness_label', '?')} | Feel: {af.get('percussiveness_label', '?')}"
        )

    return "\n".join(output)


def run_build_setlist(description, num_tracks=8, starting_bpm=None):
    results = vibe_search(description, collection=COLLECTION, n_results=min(num_tracks * 3, 30))

    if not results['ids'][0]:
        return "No matching tracks found for that description."

    candidates = []
    seen = set()
    for meta in results['metadatas'][0]:
        matches = find_track_by_name(LIBRARY_TRACKS, f"{meta.get('artist','')} {meta.get('title','')}")
        if matches:
            fp = matches[0].get('filepath', '')
            if fp not in seen:
                candidates.append(matches[0])
                seen.add(fp)

    if not candidates:
        return "Found tracks but couldn't match them to library."

    if starting_bpm:
        candidates.sort(key=lambda t: abs(float(t.get('bpm') or 999) - starting_bpm))

    setlist = [candidates.pop(0)]

    while len(setlist) < num_tracks and candidates:
        current = setlist[-1]
        best_score = -999
        best_idx = 0

        # Track last 3 artists for diversity
        recent_artists = [t.get('artist', '') for t in setlist[-3:]]

        for i, candidate in enumerate(candidates):
            result = score_transition(current, candidate, recent_artists=recent_artists)
            if result['score'] > best_score:
                best_score = result['score']
                best_idx = i

        setlist.append(candidates.pop(best_idx))

    output = [f"🎧 Setlist: {description} ({len(setlist)} tracks)\n{'─' * 60}"]
    total_duration = 0

    for i, track in enumerate(setlist, 1):
        dur = track.get('duration_seconds') or 0
        total_duration += dur
        dur_str = f"{int(dur)//60}:{int(dur)%60:02d}" if dur else '?'
        camelot = key_to_camelot(track.get('key', '')) or '?'
        af = track.get('audio_features', {})

        output.append(
            f"{i:2d}. {track.get('artist', 'Unknown')} — {track.get('title', '?')}\n"
            f"    BPM: {track.get('bpm', '?')} | Key: {track.get('key', '?')} ({camelot}) | "
            f"Energy: {af.get('energy_label', '?')} | Duration: {dur_str}"
        )

        if i < len(setlist):
            transition = score_transition(track, setlist[i])
            icons = {'A': '🟢', 'B': '🟡', 'C': '🟠', 'D': '🔴'}
            output.append(f"    {icons.get(transition['grade'], '⚪')} → {transition['grade']} transition ({transition['score']}/100)")

    output.append(f"\n{'─' * 60}\nTotal duration: ~{int(total_duration // 60)} minutes")
    return "\n".join(output)


def run_preview_track(artist, title):
    import urllib.parse
    query = urllib.parse.quote(f"{artist} {title}")
    return f"Preview on YouTube: https://www.youtube.com/results?search_query={query}"


def run_library_stats():
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

    top_genres = sorted(genres.items(), key=lambda x: x[1], reverse=True)[:10]
    top_keys = sorted(key_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return (
        f"📊 Library: {total} tracks\n"
        f"BPM range: {min(bpms):.0f}-{max(bpms):.0f} (avg: {sum(bpms)/len(bpms):.0f})\n"
        f"Energy: Low {energy_counts['low']} | Medium {energy_counts['medium']} | High {energy_counts['high']}\n"
        f"Top genres: {', '.join(f'{g} ({c})' for g, c in top_genres)}\n"
        f"Top keys: {', '.join(f'{k} ({c})' for k, c in top_keys)}"
    )


# ── Tool dispatcher ──
TOOL_RUNNERS = {
    "search_library": lambda args: run_search_library(args["query"], args.get("n_results", 10)),
    "find_compatible_transitions": lambda args: run_find_compatible_transitions(args["track_name"], args.get("top_n", 8)),
    "find_transitions_by_key_bpm": lambda args: run_find_transitions_by_key_bpm(args["camelot_code"], args["bpm"], args.get("top_n", 8)),
    "get_track_info": lambda args: run_get_track_info(args["track_name"]),
    "build_setlist": lambda args: run_build_setlist(args["description"], args.get("num_tracks", 8), args.get("starting_bpm")),
    "preview_track": lambda args: run_preview_track(args["artist"], args["title"]),
    "library_stats": lambda args: run_library_stats(),
}


# ═══════════════════════════════════════════════════════════════
# AGENT LOOP
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """You are a professional DJ assistant with deep knowledge of mixing, 
harmonic theory, and electronic music. You have access to the user's personal DJ library 
and can search it, analyze transitions, and build setlists.

Key principles:
- Always use the tools to search the ACTUAL library — never make up track names
- When building setlists, prioritize smooth transitions (Camelot key compatibility + BPM flow)
- Explain your mixing decisions in DJ terms (Camelot moves, energy arcs, BPM progression)
- If the library doesn't have what's needed, say so honestly
- When suggesting transitions, mention the Camelot code and why it works

When building setlists, think about the energy arc — most good sets build gradually, 
have peaks, and maybe a cool-down. Don't just dump tracks randomly."""


def run_agent_turn(client, messages, verbose=False):
    """
    Run one turn of the agent loop.
    Claude may call tools multiple times before giving a final text response.
    """

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            # Claude wants to call tools — add its response and process calls
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input

                    if verbose:
                        print(f"\n  🔧 Calling: {tool_name}({json.dumps(tool_input)})")

                    runner = TOOL_RUNNERS.get(tool_name)
                    if runner:
                        try:
                            result = runner(tool_input)
                        except Exception as e:
                            result = f"Error running {tool_name}: {str(e)}"
                    else:
                        result = f"Unknown tool: {tool_name}"

                    if verbose:
                        preview = result[:300] + "..." if len(result) > 300 else result
                        print(f"  📋 Result: {preview}\n")

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})

        else:
            # Final response — extract text
            text_parts = [block.text for block in response.content if hasattr(block, 'text')]
            final_text = "\n".join(text_parts)
            messages.append({"role": "assistant", "content": final_text})
            return final_text


def main():
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("❌ Set your Anthropic API key:")
        print("   export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print(f"\n🎧 DJ Set Builder Agent")
    print(f"{'='*50}")
    print(f"Loaded {len(LIBRARY_TRACKS)} tracks from your library")
    print(f"\nTalk to me like your DJ assistant. Try:")
    print(f'  "Build me a deep house set starting at 120 BPM"')
    print(f'  "What should I play after Daft Punk Veridis Quo?"')
    print(f'  "Find me dark minimal tracks around 126"')
    print(f'  "Show me my library stats"')
    print(f"\nType 'quit' to exit, 'verbose' to toggle tool visibility\n")

    messages = []
    verbose = False

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Peace out!")
            break

        if not user_input:
            continue
        if user_input.lower() in ('quit', 'exit', 'q'):
            print("👋 Peace out!")
            break
        if user_input.lower() == 'verbose':
            verbose = not verbose
            print(f"  Tool visibility: {'ON' if verbose else 'OFF'}")
            continue

        messages.append({"role": "user", "content": user_input})

        try:
            response = run_agent_turn(client, messages, verbose=verbose)
            print(f"\nDJ Agent: {response}\n")
        except Exception as e:
            print(f"\n⚠ Error: {e}\n")
            messages.pop()

        if len(messages) > 30:
            messages = messages[-30:]


if __name__ == '__main__':
    main()
