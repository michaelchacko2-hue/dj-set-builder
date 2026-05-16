"""
DJ Library Scanner — Phase 1, Week 1
Scans your music folder, reads ID3/metadata tags, and builds a JSON database.

Setup:
    pip3 install mutagen

Run:
    python scan_library.py /path/to/your/music/folder

Output:
    library.json in the same folder as this script
"""

import os
import sys
import json
from datetime import datetime
from mutagen import File as MutagenFile
from mutagen.id3 import ID3
from mutagen.mp3 import MP3
from mutagen.flac import FLAC
from mutagen.aiff import AIFF

AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.aiff', '.aif', '.m4a', '.ogg'}

def extract_id3_tags(filepath):
    """Extract BPM, key, title, artist, genre, duration from an audio file."""
    track = {
        'filepath': filepath,
        'filename': os.path.basename(filepath),
        'title': None,
        'artist': None,
        'album': None,
        'genre': None,
        'bpm': None,
        'key': None,
        'duration_seconds': None,
        'format': os.path.splitext(filepath)[1].lower().lstrip('.'),
    }

    try:
        audio = MutagenFile(filepath)
        if audio is None:
            return track

        # Duration
        if hasattr(audio, 'info') and hasattr(audio.info, 'length'):
            track['duration_seconds'] = round(audio.info.length, 2)

        # Try ID3 tags (MP3, AIFF, WAV)
        if hasattr(audio, 'tags') and audio.tags is not None:
            tags = audio.tags

            # ID3 tag mapping
            id3_map = {
                'TIT2': 'title',
                'TPE1': 'artist',
                'TALB': 'album',
                'TCON': 'genre',
                'TBPM': 'bpm',
                'TKEY': 'key',
            }

            for tag_id, field in id3_map.items():
                if tag_id in tags:
                    val = str(tags[tag_id])
                    if val:
                        track[field] = val

            # Serato-specific: sometimes BPM/key are in TXXX frames
            for frame in tags.getall('TXXX'):
                desc = frame.desc.lower()
                if 'bpm' in desc and not track['bpm']:
                    track['bpm'] = str(frame.text[0]) if frame.text else None
                elif 'key' in desc and not track['key']:
                    track['key'] = str(frame.text[0]) if frame.text else None
                elif 'initial key' in desc and not track['key']:
                    track['key'] = str(frame.text[0]) if frame.text else None

            # Also check for Vorbis/FLAC style tags
            if hasattr(tags, 'items'):
                for tag_key, tag_val in tags.items() if callable(getattr(tags, 'items', None)) else []:
                    pass

        # FLAC / Vorbis comment style
        if isinstance(audio, FLAC) or hasattr(audio, 'tags'):
            vorbis_map = {
                'title': 'title',
                'artist': 'artist',
                'album': 'album',
                'genre': 'genre',
                'bpm': 'bpm',
                'key': 'key',
                'initialkey': 'key',
            }
            if hasattr(audio, 'tags') and hasattr(audio.tags, '__getitem__'):
                for vorbis_key, field in vorbis_map.items():
                    try:
                        val = audio.tags.get(vorbis_key)
                        if val and not track[field]:
                            track[field] = str(val[0]) if isinstance(val, list) else str(val)
                    except (KeyError, TypeError, IndexError):
                        pass

        # Clean up BPM to a number
        if track['bpm']:
            try:
                bpm_val = float(track['bpm'])
                track['bpm'] = round(bpm_val, 1)
            except ValueError:
                track['bpm'] = None

    except Exception as e:
        track['_error'] = str(e)

    return track

def scan_library(root_folder):
    """Walk the folder tree and scan all audio files."""
    print(f"\n🎵 DJ Library Scanner")
    print(f"{'='*50}")
    print(f"Scanning: {root_folder}\n")

    # Find all audio files
    audio_files = []
    for dirpath, _, filenames in os.walk(root_folder):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in AUDIO_EXTENSIONS:
                audio_files.append(os.path.join(dirpath, fname))

    total = len(audio_files)
    print(f"Found {total} audio files. Reading tags...\n")

    tracks = []
    errors = 0

    for i, fp in enumerate(audio_files, 1):
        if i % 25 == 0 or i == total:
            print(f"  Progress: {i}/{total} ({100*i//total}%)", end='\r')

        track = extract_id3_tags(fp)
        if '_error' in track:
            errors += 1
        tracks.append(track)

    print(f"\n\n{'='*50}")
    print(f"✅ Scanned {total} tracks ({errors} had read errors)")

    # Stats
    with_bpm = sum(1 for t in tracks if t['bpm'])
    with_key = sum(1 for t in tracks if t['key'])
    with_genre = sum(1 for t in tracks if t['genre'])

    print(f"\n📊 Tag coverage:")
    print(f"   BPM:   {with_bpm}/{total} ({100*with_bpm//max(total,1)}%)")
    print(f"   Key:   {with_key}/{total} ({100*with_key//max(total,1)}%)")
    print(f"   Genre: {with_genre}/{total} ({100*with_genre//max(total,1)}%)")

    if with_bpm < total * 0.5:
        print(f"\n💡 Tip: Only {100*with_bpm//max(total,1)}% of tracks have BPM tags.")
        print(f"   Analyze your library in Serato first, or we'll catch this in Week 2 with Librosa.")

    return tracks

def main():
    if len(sys.argv) < 2:
        print("Usage: python scan_library.py /path/to/music/folder")
        print("\nExample: python scan_library.py ~/Music/DJ")
        sys.exit(1)

    root = sys.argv[1]
    if not os.path.isdir(root):
        print(f"Error: '{root}' is not a valid directory")
        sys.exit(1)

    tracks = scan_library(root)

    # Save to JSON
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'library.json')
    output_data = {
        'scanned_at': datetime.now().isoformat(),
        'source_folder': root,
        'total_tracks': len(tracks),
        'tracks': tracks,
    }

    with open(output_path, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n💾 Saved to: {output_path}")

    # Print a sample
    print(f"\n🎶 Sample tracks:")
    print(f"{'─'*60}")
    for track in tracks[:10]:
        title = track['title'] or track['filename']
        artist = track['artist'] or 'Unknown'
        bpm = track['bpm'] or '?'
        key = track['key'] or '?'
        print(f"  {artist} — {title}")
        print(f"    BPM: {bpm} | Key: {key} | Format: {track['format']}")
    
    if len(tracks) > 10:
        print(f"  ... and {len(tracks) - 10} more")

if __name__ == '__main__':
    main()
