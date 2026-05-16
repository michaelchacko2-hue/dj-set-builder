"""
DJ Library Analyzer — Phase 1, Week 2
Runs Librosa audio analysis on every track to extract energy, brightness, and percussiveness.
Merges results with your existing library.json from Week 1.

Setup:
    pip3 install librosa numpy soundfile

Run:
    python analyze_library.py

    Or point to a specific library file:
    python analyze_library.py /path/to/library.json

Output:
    Updates library.json in place, adding audio features to each track.
    Caches results in _analysis_cache.json so re-runs skip already-analyzed tracks.
"""

import os
import sys
import json
import time
import numpy as np

try:
    import librosa
except ImportError:
    print("❌ Librosa not installed. Run: pip3 install librosa numpy soundfile")
    sys.exit(1)


def analyze_track(filepath, sr=22050, duration=None):
    """
    Extract audio features from a track using Librosa.

    Returns dict with:
        - energy: RMS energy (0-1 scale, higher = louder/harder)
        - brightness: spectral centroid mean (higher = brighter/more treble)
        - percussiveness: onset strength mean (higher = more rhythmic/punchy)
        - danceability: rough estimate from tempo stability + onset regularity
        - spectral_contrast: difference between peaks and valleys in spectrum
    """
    try:
        # Load audio (mono, resampled to 22050 Hz)
        y, sr = librosa.load(filepath, sr=sr, duration=duration)

        if len(y) == 0:
            return None

        # --- Energy (RMS) ---
        rms = librosa.feature.rms(y=y)[0]
        energy_mean = float(np.mean(rms))
        energy_max = float(np.max(rms))

        # --- Brightness (Spectral Centroid) ---
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        brightness_mean = float(np.mean(centroid))

        # --- Percussiveness (Onset Strength) ---
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        percussiveness_mean = float(np.mean(onset_env))
        percussiveness_max = float(np.max(onset_env))

        # --- Spectral Contrast ---
        contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
        contrast_mean = float(np.mean(contrast))

        # --- Tempo (backup if BPM tag was missing) ---
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        detected_bpm = round(float(np.atleast_1d(tempo)[0]), 1)

        return {
            'energy_mean': round(energy_mean, 4),
            'energy_max': round(energy_max, 4),
            'brightness': round(brightness_mean, 2),
            'percussiveness_mean': round(percussiveness_mean, 4),
            'percussiveness_max': round(percussiveness_max, 4),
            'spectral_contrast': round(contrast_mean, 4),
            'detected_bpm': detected_bpm,
        }

    except Exception as e:
        return {'_error': str(e)}


def normalize_features(tracks):
    """
    Normalize audio features to 0-1 scale and add human-readable labels.
    Makes it easier to compare tracks and build text descriptions later.
    """
    feature_keys = ['energy_mean', 'brightness', 'percussiveness_mean', 'spectral_contrast']

    # Collect min/max for each feature
    mins = {}
    maxs = {}
    for key in feature_keys:
        values = [t['audio_features'][key] for t in tracks
                  if 'audio_features' in t and t['audio_features']
                  and key in t['audio_features'] and '_error' not in t['audio_features']]
        if values:
            mins[key] = min(values)
            maxs[key] = max(values)

    # Normalize and label
    for track in tracks:
        af = track.get('audio_features')
        if not af or '_error' in af:
            continue

        normalized = {}
        for key in feature_keys:
            if key in af and key in mins and maxs[key] > mins[key]:
                val = (af[key] - mins[key]) / (maxs[key] - mins[key])
                normalized[key] = round(val, 3)

        af['normalized'] = normalized

        # Human-readable labels
        e = normalized.get('energy_mean', 0.5)
        b = normalized.get('brightness', 0.5)
        p = normalized.get('percussiveness_mean', 0.5)

        af['energy_label'] = 'low' if e < 0.33 else ('medium' if e < 0.66 else 'high')
        af['brightness_label'] = 'dark' if b < 0.33 else ('balanced' if b < 0.66 else 'bright')
        af['percussiveness_label'] = 'smooth' if p < 0.33 else ('moderate' if p < 0.66 else 'punchy')

    return tracks


def main():
    # Find library.json
    if len(sys.argv) > 1:
        library_path = sys.argv[1]
    else:
        library_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'library.json')

    if not os.path.exists(library_path):
        print(f"❌ Can't find library.json at: {library_path}")
        print("Run scan_library.py first, or pass the path: python analyze_library.py /path/to/library.json")
        sys.exit(1)

    # Load library
    with open(library_path, 'r') as f:
        library = json.load(f)

    tracks = library['tracks']
    total = len(tracks)
    print(f"\n🎛  DJ Library Analyzer")
    print(f"{'='*50}")
    print(f"Loaded {total} tracks from library.json\n")

    # Load cache (so we don't re-analyze tracks)
    cache_path = os.path.join(os.path.dirname(library_path), '_analysis_cache.json')
    cache = {}
    if os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            cache = json.load(f)
        print(f"📦 Loaded cache with {len(cache)} previously analyzed tracks\n")

    # Analyze
    analyzed = 0
    skipped = 0
    errors = 0
    start_time = time.time()

    for i, track in enumerate(tracks, 1):
        fp = track['filepath']
        
        # Check cache
        if fp in cache and '_error' not in cache[fp]:
            track['audio_features'] = cache[fp]
            skipped += 1
            continue

        # Check file exists
        if not os.path.exists(fp):
            track['audio_features'] = {'_error': 'file not found'}
            errors += 1
            continue

        # Analyze
        elapsed = time.time() - start_time
        rate = analyzed / elapsed if elapsed > 0 and analyzed > 0 else 0
        remaining = (total - i) / rate if rate > 0 else 0
        eta = f"{int(remaining//60)}m{int(remaining%60)}s" if rate > 0 else "calculating..."

        title = track.get('title') or track.get('filename', '?')
        print(f"  [{i}/{total}] {title[:45]:<45} ETA: {eta}", end='\r')

        features = analyze_track(fp)
        if features and '_error' not in features:
            track['audio_features'] = features
            cache[fp] = features
            analyzed += 1

            # Also backfill BPM if the tag was missing
            if not track.get('bpm') and features.get('detected_bpm'):
                track['bpm'] = features['detected_bpm']
                track['bpm_source'] = 'librosa'
        else:
            track['audio_features'] = features or {'_error': 'analysis returned None'}
            errors += 1

        # Save cache every 25 tracks
        if analyzed % 25 == 0:
            with open(cache_path, 'w') as f:
                json.dump(cache, f)

    # Final cache save
    with open(cache_path, 'w') as f:
        json.dump(cache, f)

    elapsed_total = time.time() - start_time
    print(f"\n\n{'='*50}")
    print(f"✅ Analysis complete in {int(elapsed_total//60)}m {int(elapsed_total%60)}s")
    print(f"   Analyzed: {analyzed} tracks")
    print(f"   Cached:   {skipped} tracks (skipped)")
    print(f"   Errors:   {errors} tracks")

    # Normalize features across the library
    print(f"\n📐 Normalizing features across library...")
    tracks = normalize_features(tracks)

    # Backfill stats
    bpm_backfilled = sum(1 for t in tracks if t.get('bpm_source') == 'librosa')
    if bpm_backfilled:
        print(f"🎯 Backfilled BPM for {bpm_backfilled} tracks that were missing tags")

    # Save updated library
    library['tracks'] = tracks
    library['analysis_date'] = time.strftime('%Y-%m-%dT%H:%M:%S')

    with open(library_path, 'w') as f:
        json.dump(library, f, indent=2)

    print(f"\n💾 Updated: {library_path}")

    # Print some fun stats
    print(f"\n🎶 Library vibe breakdown:")
    print(f"{'─'*40}")

    labels = {'energy_label': 'Energy', 'brightness_label': 'Brightness', 'percussiveness_label': 'Feel'}
    for key, name in labels.items():
        counts = {}
        for t in tracks:
            af = t.get('audio_features', {})
            if af and '_error' not in af:
                label = af.get(key, 'unknown')
                counts[label] = counts.get(label, 0) + 1
        if counts:
            parts = [f"{v}: {count}" for v, count in sorted(counts.items())]
            print(f"  {name:12s} → {', '.join(parts)}")

    # Sample dark vs bright tracks
    print(f"\n🌙 Darkest tracks:")
    dark = sorted(
        [t for t in tracks if t.get('audio_features', {}).get('normalized', {}).get('brightness') is not None],
        key=lambda t: t['audio_features']['normalized']['brightness']
    )[:5]
    for t in dark:
        title = t.get('title') or t.get('filename', '?')
        artist = t.get('artist') or 'Unknown'
        print(f"  {artist} — {title}")

    print(f"\n☀️  Brightest tracks:")
    bright = sorted(
        [t for t in tracks if t.get('audio_features', {}).get('normalized', {}).get('brightness') is not None],
        key=lambda t: t['audio_features']['normalized']['brightness'],
        reverse=True
    )[:5]
    for t in bright:
        title = t.get('title') or t.get('filename', '?')
        artist = t.get('artist') or 'Unknown'
        print(f"  {artist} — {title}")


if __name__ == '__main__':
    main()
