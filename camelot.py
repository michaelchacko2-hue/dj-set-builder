"""
DJ Camelot Mixing Logic — Phase 3
Harmonic mixing brain: maps keys to Camelot codes, finds compatible tracks,
and scores transitions based on BPM, key, and energy flow.

Setup:
    No new dependencies — just needs your library.json from Phase 1-2.

Run:
    python camelot.py                           # Interactive mode
    python camelot.py "4A" 126                  # Find tracks compatible with 4A at ~126 BPM
    python camelot.py --track "Artist - Title"  # Find what mixes well after a specific track

Can also be imported as a module for Phase 4:
    from camelot import find_transitions, score_transition, key_to_camelot
"""

import os
import sys
import json
import re

LIBRARY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'library.json')

# ─── Camelot Wheel Mapping ─────────────────────────────────────

# Musical key → Camelot code
KEY_TO_CAMELOT = {
    # Minor keys (A column)
    'Abm': '1A',  'Ab minor': '1A',  'G#m': '1A',  'G# minor': '1A',
    'Ebm': '2A',  'Eb minor': '2A',  'D#m': '2A',  'D# minor': '2A',
    'Bbm': '3A',  'Bb minor': '3A',  'A#m': '3A',  'A# minor': '3A',
    'Fm':  '4A',  'F minor':  '4A',
    'Cm':  '5A',  'C minor':  '5A',
    'Gm':  '6A',  'G minor':  '6A',
    'Dm':  '7A',  'D minor':  '7A',
    'Am':  '8A',  'A minor':  '8A',
    'Em':  '9A',  'E minor':  '9A',
    'Bm':  '10A', 'B minor':  '10A',
    'F#m': '11A', 'F# minor': '11A', 'Gbm': '11A', 'Gb minor': '11A',
    'Dbm': '12A', 'Db minor': '12A', 'C#m': '12A', 'C# minor': '12A',

    # Major keys (B column)
    'B':   '1B',  'B major':  '1B',
    'F#':  '2B',  'F# major': '2B',  'Gb':  '2B',  'Gb major': '2B',
    'Db':  '3B',  'Db major': '3B',  'C#':  '3B',  'C# major': '3B',
    'Ab':  '4B',  'Ab major': '4B',  'G#':  '4B',  'G# major': '4B',
    'Eb':  '5B',  'Eb major': '5B',  'D#':  '5B',  'D# major': '5B',
    'Bb':  '6B',  'Bb major': '6B',  'A#':  '6B',  'A# major': '6B',
    'F':   '7B',  'F major':  '7B',
    'C':   '8B',  'C major':  '8B',
    'G':   '9B',  'G major':  '9B',
    'D':   '10B', 'D major':  '10B',
    'A':   '11B', 'A major':  '11B',
    'E':   '12B', 'E major':  '12B',
}

# Reverse lookup: Camelot code → key name
CAMELOT_TO_KEY = {
    '1A': 'Ab minor',  '1B': 'B major',
    '2A': 'Eb minor',  '2B': 'F# major',
    '3A': 'Bb minor',  '3B': 'Db major',
    '4A': 'F minor',   '4B': 'Ab major',
    '5A': 'C minor',   '5B': 'Eb major',
    '6A': 'G minor',   '6B': 'Bb major',
    '7A': 'D minor',   '7B': 'F major',
    '8A': 'A minor',   '8B': 'C major',
    '9A': 'E minor',   '9B': 'G major',
    '10A': 'B minor',  '10B': 'D major',
    '11A': 'F# minor', '11B': 'A major',
    '12A': 'C# minor', '12B': 'E major',
}


def normalize_key(raw_key):
    """
    Normalize various key formats to a standard form.
    Handles: 'Am', 'A minor', 'Amin', '8A', 'A', 'Abm', 'Ab minor', etc.
    """
    if not raw_key:
        return None

    raw = raw_key.strip()

    # Already a Camelot code?
    if re.match(r'^\d{1,2}[AB]$', raw):
        return raw

    # Try direct lookup first (covers Fm, Am, Abm, Ab, C, etc.)
    if raw in KEY_TO_CAMELOT:
        return raw

    # Case-insensitive direct lookup
    for key in KEY_TO_CAMELOT:
        if key.lower() == raw.lower():
            return key

    # Handle "X minor" / "X major" formats
    minor_match = re.match(r'^([A-G][b#]?)\s*(minor|min)$', raw, re.IGNORECASE)
    if minor_match:
        note = minor_match.group(1)
        candidate = note + 'm'
        if candidate in KEY_TO_CAMELOT:
            return candidate

    major_match = re.match(r'^([A-G][b#]?)\s*(major|maj)$', raw, re.IGNORECASE)
    if major_match:
        note = major_match.group(1)
        if note in KEY_TO_CAMELOT:
            return note

    # Try with 'm' suffix for minor
    if raw + 'm' in KEY_TO_CAMELOT:
        return raw + 'm'

    return raw  # Return as-is if we can't normalize


def key_to_camelot(key):
    """Convert a musical key to its Camelot code."""
    if not key:
        return None

    normalized = normalize_key(key)

    # Already Camelot?
    if normalized in CAMELOT_TO_KEY:
        return normalized

    return KEY_TO_CAMELOT.get(normalized)


def get_compatible_codes(camelot_code):
    """
    Return all Camelot codes compatible with the given code.

    Compatible moves:
    1. Same code (perfect match)
    2. +1 on the wheel (energy up)
    3. -1 on the wheel (energy down)
    4. A↔B switch (major/minor shift — same number, different letter)
    """
    if not camelot_code or camelot_code not in CAMELOT_TO_KEY:
        return []

    number = int(camelot_code[:-1])
    letter = camelot_code[-1]

    compatible = []

    # Same code (perfect)
    compatible.append((camelot_code, 'perfect', 'Same key'))

    # +1 (wraps 12→1)
    up = ((number % 12) + 1)
    compatible.append((f"{up}{letter}", 'good', '+1 on wheel (energy up)'))

    # -1 (wraps 1→12)
    down = ((number - 2) % 12) + 1
    compatible.append((f"{down}{letter}", 'good', '-1 on wheel (energy down)'))

    # A↔B switch (relative major/minor)
    switch = 'B' if letter == 'A' else 'A'
    compatible.append((f"{number}{switch}", 'good', 'Major/minor switch'))

    # +2 on wheel (more adventurous but still usable)
    up2 = ((number % 12) + 2) % 12
    if up2 == 0:
        up2 = 12
    compatible.append((f"{up2}{letter}", 'adventurous', '+2 on wheel'))

    # -2 on wheel
    down2 = ((number - 3) % 12) + 1
    compatible.append((f"{down2}{letter}", 'adventurous', '-2 on wheel'))

    # Diagonal: +1 and switch (creative move)
    up_switch = ((number % 12) + 1)
    compatible.append((f"{up_switch}{switch}", 'creative', '+1 and switch'))

    return compatible


def get_base_title(title):
    """
    Strip remix/edit/version suffixes to get the base song title.
    'Feel My Needs (PDM Remix)' → 'feel my needs'
    'Wipe Me Down (Intro Dirty)' → 'wipe me down'
    """
    if not title:
        return ''
    import re
    # Remove parenthetical suffixes (remix, edit, mix, version, etc.)
    base = re.sub(r'\s*[\(\[].*?[\)\]]', '', title)
    # Remove common suffixes not in parens
    base = re.sub(r'\s*[-–]\s*(remix|edit|mix|version|dub|instrumental|radio|extended|original|clean|dirty|intro|outro|bootleg|rework|vip).*$', '', base, flags=re.IGNORECASE)
    return base.strip().lower()


def is_same_song(track_a, track_b):
    """Check if two tracks are versions of the same song."""
    title_a = get_base_title(track_a.get('title') or track_a.get('filename', ''))
    title_b = get_base_title(track_b.get('title') or track_b.get('filename', ''))
    if not title_a or not title_b:
        return False
    return title_a == title_b


def score_transition(track_a, track_b, recent_artists=None):
    """
    Score the transition quality between two tracks (0-100).

    Factors:
    - Key compatibility (Camelot match): 0-40 points
    - BPM closeness: 0-30 points
    - Energy flow (smooth or building): 0-30 points
    - Same artist penalty: -20 points
    - Same song/remix penalty: -40 points
    
    Args:
        recent_artists: List of recently played artist names to penalize repeats
    """
    score = 0
    details = []

    # ── Same song / remix check ──
    if is_same_song(track_a, track_b):
        score -= 40
        details.append("Same song/remix — skip")

    # ── Artist repetition penalty ──
    artist_a = (track_a.get('artist') or '').lower().strip()
    artist_b = (track_b.get('artist') or '').lower().strip()
    
    if artist_a and artist_b and artist_a == artist_b:
        score -= 20
        details.append("Same artist — back-to-back")
    
    # Also check against recent artist history (for setlist building)
    if recent_artists and artist_b:
        recent_lower = [a.lower().strip() for a in recent_artists]
        if artist_b in recent_lower:
            score -= 10
            details.append("Artist played recently")

    # ── Key compatibility (40 points) ──
    key_a = key_to_camelot(track_a.get('key'))
    key_b = key_to_camelot(track_b.get('key'))

    if key_a and key_b:
        compatible = get_compatible_codes(key_a)
        match = next((c for c in compatible if c[0] == key_b), None)

        if match:
            _, quality, desc = match
            if quality == 'perfect':
                score += 40
                details.append(f"Key: perfect match ({key_a})")
            elif quality == 'good':
                score += 35
                details.append(f"Key: compatible ({key_a}→{key_b}, {desc})")
            elif quality == 'adventurous':
                score += 20
                details.append(f"Key: adventurous ({key_a}→{key_b}, {desc})")
            elif quality == 'creative':
                score += 25
                details.append(f"Key: creative ({key_a}→{key_b}, {desc})")
        else:
            score += 0
            details.append(f"Key: clash ({key_a}→{key_b})")
    else:
        score += 15  # Unknown keys get a neutral score
        details.append("Key: unknown (one or both tracks missing key)")

    # ── BPM closeness (30 points) ──
    bpm_a = track_a.get('bpm')
    bpm_b = track_b.get('bpm')

    if bpm_a and bpm_b:
        bpm_a = float(bpm_a)
        bpm_b = float(bpm_b)
        diff = abs(bpm_a - bpm_b)

        # Check half/double time compatibility
        half_diff = abs(bpm_a - bpm_b * 2)
        double_diff = abs(bpm_a * 2 - bpm_b)

        # Determine which relationship is closest
        if half_diff < diff and half_diff < double_diff:
            effective_diff = half_diff
            bpm_label = f"half-time {bpm_a}→{bpm_b}"
        elif double_diff < diff and double_diff < half_diff:
            effective_diff = double_diff
            bpm_label = f"double-time {bpm_a}→{bpm_b}"
        else:
            effective_diff = diff
            bpm_label = f"{bpm_a}→{bpm_b}"

        if effective_diff <= 1:
            score += 30
            details.append(f"BPM: locked ({bpm_label})")
        elif effective_diff <= 3:
            score += 27
            details.append(f"BPM: close ({bpm_label}, Δ{effective_diff:.1f})")
        elif effective_diff <= 6:
            score += 20
            details.append(f"BPM: workable ({bpm_label}, Δ{effective_diff:.1f})")
        elif effective_diff <= 10:
            score += 10
            details.append(f"BPM: stretch ({bpm_label}, Δ{effective_diff:.1f})")
        else:
            # Penalize big jumps so they can't rank high on key alone
            score -= 15
            details.append(f"BPM: too far ({bpm_label}, Δ{effective_diff:.1f})")
    else:
        score += 10
        details.append("BPM: unknown")

    # ── Energy flow (30 points) ──
    af_a = track_a.get('audio_features', {})
    af_b = track_b.get('audio_features', {})

    if af_a and af_b and '_error' not in af_a and '_error' not in af_b:
        norm_a = af_a.get('normalized', {})
        norm_b = af_b.get('normalized', {})

        e_a = norm_a.get('energy_mean', 0.5)
        e_b = norm_b.get('energy_mean', 0.5)
        energy_diff = e_b - e_a  # Positive = building up

        if abs(energy_diff) < 0.1:
            score += 30
            details.append("Energy: steady flow")
        elif 0 < energy_diff <= 0.25:
            score += 28
            details.append("Energy: building up nicely")
        elif -0.25 <= energy_diff < 0:
            score += 25
            details.append("Energy: cooling down smoothly")
        elif energy_diff > 0.25:
            score += 15
            details.append("Energy: big jump up")
        else:
            score += 12
            details.append("Energy: big drop")
    else:
        score += 15
        details.append("Energy: no data")

    return {
        'score': score,
        'grade': 'A' if score >= 85 else 'B' if score >= 70 else 'C' if score >= 50 else 'D',
        'details': details,
    }


def find_transitions(track, library_tracks, top_n=10, bpm_tolerance=10):
    """Find the best tracks to play after the given track.
    
    Args:
        track: Source track dict
        library_tracks: List of all tracks
        top_n: Number of results to return
        bpm_tolerance: Max BPM difference allowed (also checks half/double time)
    """
    scored = []
    source_bpm = float(track.get('bpm') or 0)

    for candidate in library_tracks:
        # Don't match against itself
        if candidate.get('filepath') == track.get('filepath'):
            continue

        # Pre-filter by BPM range (including half/double time)
        cand_bpm = float(candidate.get('bpm') or 0)
        if source_bpm and cand_bpm:
            diff = abs(source_bpm - cand_bpm)
            half_diff = abs(source_bpm - cand_bpm * 2)
            double_diff = abs(source_bpm * 2 - cand_bpm)
            closest = min(diff, half_diff, double_diff)
            if closest > bpm_tolerance:
                continue

        result = score_transition(track, candidate)
        result['track'] = candidate
        scored.append(result)

    # Sort by score descending
    scored.sort(key=lambda x: x['score'], reverse=True)

    return scored[:top_n]


def load_library():
    """Load library.json."""
    if not os.path.exists(LIBRARY_PATH):
        print(f"❌ Can't find library.json at: {LIBRARY_PATH}")
        sys.exit(1)

    with open(LIBRARY_PATH, 'r') as f:
        library = json.load(f)

    return library['tracks']


def find_track_by_name(tracks, search_term):
    """Fuzzy find a track by artist/title."""
    search_lower = search_term.lower()
    matches = []

    for t in tracks:
        artist = (t.get('artist') or '').lower()
        title = (t.get('title') or '').lower()
        filename = (t.get('filename') or '').lower()

        # Check if search term appears in artist, title, or filename
        combined = f"{artist} {title} {filename}"
        if search_lower in combined:
            matches.append(t)

    return matches


def print_transition_results(transitions):
    """Pretty-print transition results."""
    for i, t in enumerate(transitions, 1):
        track = t['track']
        artist = track.get('artist') or 'Unknown'
        title = track.get('title') or track.get('filename', '?')
        bpm = track.get('bpm') or '?'
        key = track.get('key') or '?'
        camelot = key_to_camelot(key) or '?'

        grade_colors = {'A': '🟢', 'B': '🟡', 'C': '🟠', 'D': '🔴'}
        grade_icon = grade_colors.get(t['grade'], '⚪')

        print(f"\n  {i}. {grade_icon} [{t['grade']}] {artist} — {title}")
        print(f"     BPM: {bpm} | Key: {key} ({camelot}) | Score: {t['score']}/100")
        for detail in t['details']:
            print(f"     • {detail}")


def interactive_mode():
    """Interactive transition finder."""
    tracks = load_library()

    print(f"\n🎛  DJ Transition Finder")
    print(f"{'='*50}")
    print(f"Loaded {len(tracks)} tracks\n")
    print(f"Commands:")
    print(f'  Search by track:   disco inferno')
    print(f'  Search by Camelot: 4A 126')
    print(f"  Type 'quit' to exit\n")

    while True:
        try:
            raw = input("🎵 Find transitions for: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋")
            break

        if not raw or raw.lower() in ('quit', 'exit', 'q'):
            print("👋")
            break

        # Check if input is Camelot code + BPM
        camelot_match = re.match(r'^(\d{1,2}[AB])\s+(\d+\.?\d*)$', raw, re.IGNORECASE)

        if camelot_match:
            code = camelot_match.group(1).upper()
            bpm = float(camelot_match.group(2))

            if code not in CAMELOT_TO_KEY:
                print(f"  Invalid Camelot code: {code}")
                continue

            # Create a virtual track with the given key/bpm
            virtual_track = {
                'key': CAMELOT_TO_KEY[code],
                'bpm': bpm,
                'audio_features': {'normalized': {'energy_mean': 0.5}},
            }

            print(f"\n  Finding tracks compatible with {code} ({CAMELOT_TO_KEY[code]}) at {bpm} BPM:")
            transitions = find_transitions(virtual_track, tracks)
            print_transition_results(transitions)

        else:
            # Search by track name
            matches = find_track_by_name(tracks, raw)

            if not matches:
                print(f"  No tracks found matching '{raw}'")
                continue

            if len(matches) > 1:
                print(f"\n  Found {len(matches)} matches:")
                for j, m in enumerate(matches[:8], 1):
                    artist = m.get('artist') or 'Unknown'
                    title = m.get('title') or m.get('filename', '?')
                    print(f"    {j}. {artist} — {title}")

                try:
                    pick = input(f"  Pick one (1-{min(len(matches), 8)}): ").strip()
                    idx = int(pick) - 1
                    if 0 <= idx < len(matches):
                        source = matches[idx]
                    else:
                        continue
                except (ValueError, EOFError):
                    continue
            else:
                source = matches[0]

            artist = source.get('artist') or 'Unknown'
            title = source.get('title') or '?'
            bpm = source.get('bpm') or '?'
            key = source.get('key') or '?'
            camelot = key_to_camelot(key) or '?'

            print(f"\n  Now playing: {artist} — {title}")
            print(f"  BPM: {bpm} | Key: {key} ({camelot})")
            print(f"\n  Best transitions:")

            transitions = find_transitions(source, tracks)
            print_transition_results(transitions)

        print()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]

    if len(args) == 2 and re.match(r'^\d{1,2}[AB]$', args[0], re.IGNORECASE):
        # Direct: python camelot.py 4A 126
        tracks = load_library()
        code = args[0].upper()
        bpm = float(args[1])

        virtual = {
            'key': CAMELOT_TO_KEY.get(code, ''),
            'bpm': bpm,
            'audio_features': {'normalized': {'energy_mean': 0.5}},
        }

        print(f"\n🎵 Tracks compatible with {code} ({CAMELOT_TO_KEY.get(code, '?')}) at {bpm} BPM:")
        transitions = find_transitions(virtual, tracks)
        print_transition_results(transitions)

    elif '--track' in sys.argv:
        idx = sys.argv.index('--track')
        if idx + 1 < len(sys.argv):
            tracks = load_library()
            search = sys.argv[idx + 1]
            matches = find_track_by_name(tracks, search)
            if matches:
                source = matches[0]
                print(f"\n🎵 Transitions from: {source.get('artist','')} — {source.get('title','')}")
                transitions = find_transitions(source, tracks)
                print_transition_results(transitions)
            else:
                print(f"No tracks found matching '{search}'")
    else:
        interactive_mode()


if __name__ == '__main__':
    main()
