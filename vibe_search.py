"""
DJ Library Vector Search — Phase 2, Week 3-4
Loads your analyzed library into ChromaDB for vibe-based semantic search.

Setup:
    pip3 install chromadb

Run:
    python vibe_search.py                          # First run: builds the database
    python vibe_search.py "deep melodic house 122" # Search by vibe
    python vibe_search.py --interactive             # Interactive search mode

Output:
    ChromaDB database stored in ./chroma_db/
"""

import os
import sys
import json
import chromadb

LIBRARY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'library.json')
CHROMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'chroma_db')


def build_track_description(track):
    """
    Turn a track's metadata + audio features into a rich text description.
    This is what gets embedded — more detail = better search results.
    """
    parts = []

    # Core metadata
    if track.get('artist'):
        parts.append(f"Artist: {track['artist']}")
    if track.get('title'):
        parts.append(f"Title: {track['title']}")
    if track.get('genre'):
        parts.append(f"Genre: {track['genre']}")
    if track.get('bpm'):
        parts.append(f"BPM: {track['bpm']}")
    if track.get('key'):
        parts.append(f"Key: {track['key']}")

    # Audio features (human-readable labels)
    af = track.get('audio_features', {})
    if af and '_error' not in af:
        energy = af.get('energy_label', '')
        brightness = af.get('brightness_label', '')
        feel = af.get('percussiveness_label', '')

        if energy:
            parts.append(f"Energy: {energy}")
        if brightness:
            parts.append(f"Tone: {brightness}")
        if feel:
            parts.append(f"Feel: {feel}")

        # Add vibe words based on combinations
        vibes = []
        if energy == 'high' and feel == 'punchy':
            vibes.extend(['driving', 'peak-time', 'banger', 'intense'])
        elif energy == 'high' and brightness == 'bright':
            vibes.extend(['euphoric', 'uplifting', 'festival'])
        elif energy == 'low' and brightness == 'dark':
            vibes.extend(['atmospheric', 'ambient', 'moody', 'underground'])
        elif energy == 'low' and brightness == 'balanced':
            vibes.extend(['chill', 'deep', 'smooth', 'warm-up'])
        elif energy == 'medium' and brightness == 'dark':
            vibes.extend(['deep', 'underground', 'hypnotic', 'minimal'])
        elif energy == 'medium' and brightness == 'balanced':
            vibes.extend(['groovy', 'rolling', 'steady'])
        elif energy == 'medium' and feel == 'punchy':
            vibes.extend(['rhythmic', 'percussive', 'tribal'])

        if brightness == 'bright' and feel == 'smooth':
            vibes.extend(['melodic', 'lush', 'airy'])
        if energy == 'low' and feel == 'smooth':
            vibes.extend(['downtempo', 'relaxed', 'opener'])

        if vibes:
            parts.append(f"Vibe: {', '.join(vibes)}")

    # Duration category
    dur = track.get('duration_seconds')
    if dur:
        if dur > 360:
            parts.append("Length: extended mix")
        elif dur < 180:
            parts.append("Length: short/edit")

    return ". ".join(parts)


def build_database():
    """Load library.json into ChromaDB."""
    print(f"\n🔧 Building ChromaDB vector database...")
    print(f"{'='*50}\n")

    # Load library
    if not os.path.exists(LIBRARY_PATH):
        print(f"❌ Can't find library.json at: {LIBRARY_PATH}")
        print("Run scan_library.py and analyze_library.py first.")
        sys.exit(1)

    with open(LIBRARY_PATH, 'r') as f:
        library = json.load(f)

    tracks = library['tracks']
    print(f"Loaded {len(tracks)} tracks from library.json")

    # Initialize ChromaDB
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    # Delete existing collection if rebuilding
    try:
        client.delete_collection("dj_library")
        print("Cleared existing collection")
    except Exception:
        pass

    collection = client.create_collection(
        name="dj_library",
        metadata={"hnsw:space": "cosine"}
    )

    # Prepare documents
    documents = []
    metadatas = []
    ids = []
    skipped = 0

    for i, track in enumerate(tracks):
        # Skip tracks with analysis errors
        af = track.get('audio_features', {})
        if not af or '_error' in af:
            skipped += 1
            continue

        description = build_track_description(track)
        if not description:
            skipped += 1
            continue

        # Metadata for filtering (ChromaDB only supports str/int/float/bool)
        meta = {
            'artist': track.get('artist') or 'Unknown',
            'title': track.get('title') or track.get('filename', 'Unknown'),
            'filename': track.get('filename', ''),
            'filepath': track.get('filepath', ''),
            'format': track.get('format', ''),
        }

        if track.get('bpm'):
            meta['bpm'] = float(track['bpm'])
        if track.get('key'):
            meta['key'] = track['key']
        if track.get('genre'):
            meta['genre'] = track['genre']
        if track.get('duration_seconds'):
            meta['duration'] = float(track['duration_seconds'])

        # Audio feature labels for filtering
        if af.get('energy_label'):
            meta['energy'] = af['energy_label']
        if af.get('brightness_label'):
            meta['brightness'] = af['brightness_label']
        if af.get('percussiveness_label'):
            meta['feel'] = af['percussiveness_label']

        documents.append(description)
        metadatas.append(meta)
        ids.append(f"track_{i}")

    # Add to ChromaDB in batches
    batch_size = 100
    for start in range(0, len(documents), batch_size):
        end = min(start + batch_size, len(documents))
        collection.add(
            documents=documents[start:end],
            metadatas=metadatas[start:end],
            ids=ids[start:end],
        )
        print(f"  Added batch {start//batch_size + 1}: tracks {start+1}-{end}")

    print(f"\n✅ Database built: {len(documents)} tracks indexed, {skipped} skipped")
    print(f"📁 Stored at: {CHROMA_PATH}")

    return collection


def search(query, collection=None, n_results=10, bpm_range=None, energy=None, genre=None):
    """
    Search your library by vibe.

    Args:
        query: Natural language description ("dark minimal techno 126 bpm")
        n_results: How many results to return
        bpm_range: Tuple of (min_bpm, max_bpm) to filter
        energy: Filter by energy level ("low", "medium", "high")
        genre: Filter by genre string
    """
    if collection is None:
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        collection = client.get_collection("dj_library")

    # Build filters
    where_filters = []
    if bpm_range:
        where_filters.append({"bpm": {"$gte": float(bpm_range[0])}})
        where_filters.append({"bpm": {"$lte": float(bpm_range[1])}})
    if energy:
        where_filters.append({"energy": energy})
    if genre:
        where_filters.append({"genre": {"$contains": genre}})

    where = None
    if len(where_filters) == 1:
        where = where_filters[0]
    elif len(where_filters) > 1:
        where = {"$and": where_filters}

    # Query
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        where=where,
        include=["documents", "metadatas", "distances"],
    )

    return results


def print_results(results):
    """Pretty-print search results."""
    if not results['ids'][0]:
        print("  No matches found. Try broadening your search.")
        return

    for i, (meta, distance) in enumerate(zip(results['metadatas'][0], results['distances'][0]), 1):
        artist = meta.get('artist', 'Unknown')
        title = meta.get('title', 'Unknown')
        bpm = meta.get('bpm', '?')
        key = meta.get('key', '?')
        energy = meta.get('energy', '?')
        brightness = meta.get('brightness', '?')
        feel = meta.get('feel', '?')
        relevance = round((1 - distance) * 100, 1)

        print(f"\n  {i}. {artist} — {title}")
        print(f"     BPM: {bpm} | Key: {key} | Match: {relevance}%")
        print(f"     Energy: {energy} | Tone: {brightness} | Feel: {feel}")


def interactive_mode():
    """Interactive search REPL."""
    print(f"\n🎧 DJ Library Vibe Search")
    print(f"{'='*50}")
    print(f"Type a vibe description to search your library.")
    print(f"Examples:")
    print(f'  "dark driving techno around 130 bpm"')
    print(f'  "smooth deep house for warming up"')
    print(f'  "high energy disco banger"')
    print(f'  "chill melodic stuff"')
    print(f"\nFilters: add bpm:120-128 or energy:high to narrow results")
    print(f"Type 'quit' to exit.\n")

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection("dj_library")

    while True:
        try:
            raw = input("🔍 Search: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Later!")
            break

        if not raw or raw.lower() in ('quit', 'exit', 'q'):
            print("👋 Later!")
            break

        # Parse inline filters
        query = raw
        bpm_range = None
        energy = None

        # Extract bpm:120-130
        import re
        bpm_match = re.search(r'bpm:(\d+)-(\d+)', raw, re.IGNORECASE)
        if bpm_match:
            bpm_range = (int(bpm_match.group(1)), int(bpm_match.group(2)))
            query = raw[:bpm_match.start()] + raw[bpm_match.end():]

        # Extract energy:high
        energy_match = re.search(r'energy:(low|medium|high)', raw, re.IGNORECASE)
        if energy_match:
            energy = energy_match.group(1).lower()
            query = query[:energy_match.start()] + query[energy_match.end():]

        query = query.strip()
        if not query:
            query = "music"

        results = search(query, collection=collection, bpm_range=bpm_range, energy=energy)
        print_results(results)
        print()


def main():
    # Check if database exists
    db_exists = os.path.exists(CHROMA_PATH) and os.listdir(CHROMA_PATH)

    if '--rebuild' in sys.argv:
        build_database()
        return

    if not db_exists:
        print("First run — building the vector database...")
        build_database()
        print()

    # Interactive mode or single query
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    
    if not args or '--interactive' in sys.argv:
        interactive_mode()
    else:
        query = ' '.join(args)
        print(f"\n🔍 Searching for: {query}\n")
        results = search(query)
        print_results(results)
        print()


if __name__ == '__main__':
    main()
