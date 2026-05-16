"""
DJ Library Duplicate Finder
Finds duplicate audio files by content hash (catches dupes even with different filenames).
Run: python find_duplicates.py /path/to/your/music/folder
"""

import os
import sys
import hashlib
from collections import defaultdict

AUDIO_EXTENSIONS = {'.mp3', '.wav', '.flac', '.aiff', '.aif', '.m4a', '.ogg'}

def hash_file(filepath, chunk_size=8192):
    """Hash file contents with SHA-256."""
    sha256 = hashlib.sha256()
    try:
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest()
    except (IOError, PermissionError) as e:
        print(f"  ⚠ Could not read: {filepath} ({e})")
        return None

def find_audio_files(root_folder):
    """Walk folder tree and return all audio file paths."""
    audio_files = []
    for dirpath, _, filenames in os.walk(root_folder):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in AUDIO_EXTENSIONS:
                audio_files.append(os.path.join(dirpath, fname))
    return audio_files

def find_duplicates(root_folder):
    """Group files by hash to find exact duplicates."""
    print(f"\n🔍 Scanning: {root_folder}\n")
    
    audio_files = find_audio_files(root_folder)
    print(f"Found {len(audio_files)} audio files. Hashing...\n")
    
    # Group by file size first (quick pre-filter — files with unique sizes can't be dupes)
    size_groups = defaultdict(list)
    for fp in audio_files:
        try:
            size = os.path.getsize(fp)
            size_groups[size].append(fp)
        except OSError:
            pass
    
    # Only hash files that share a size with at least one other file
    candidates = []
    for size, files in size_groups.items():
        if len(files) > 1:
            candidates.extend(files)
    
    print(f"{len(candidates)} files share a size with another file — hashing those...\n")
    
    hash_groups = defaultdict(list)
    for i, fp in enumerate(candidates, 1):
        if i % 50 == 0 or i == len(candidates):
            print(f"  Hashed {i}/{len(candidates)}", end='\r')
        file_hash = hash_file(fp)
        if file_hash:
            hash_groups[file_hash].append(fp)
    
    print()
    
    # Filter to only groups with duplicates
    duplicates = {h: files for h, files in hash_groups.items() if len(files) > 1}
    return duplicates

def format_size(size_bytes):
    """Human-readable file size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"

def main():
    if len(sys.argv) < 2:
        print("Usage: python find_duplicates.py /path/to/music/folder")
        sys.exit(1)
    
    root = sys.argv[1]
    if not os.path.isdir(root):
        print(f"Error: '{root}' is not a valid directory")
        sys.exit(1)
    
    duplicates = find_duplicates(root)
    
    if not duplicates:
        print("\n✅ No duplicates found! Your library is clean.")
        return
    
    # Calculate wasted space
    total_wasted = 0
    total_dupes = 0
    
    print(f"\n{'='*60}")
    print(f"Found {len(duplicates)} sets of duplicates:\n")
    
    for i, (file_hash, files) in enumerate(duplicates.items(), 1):
        size = os.path.getsize(files[0])
        wasted = size * (len(files) - 1)
        total_wasted += wasted
        total_dupes += len(files) - 1
        
        print(f"── Set {i} ({format_size(size)} each, {len(files)} copies) ──")
        # Mark the first one as KEEP and the rest as dupes
        for j, fp in enumerate(files):
            marker = "KEEP " if j == 0 else "DUPE "
            print(f"  {marker} {fp}")
        print()
    
    print(f"{'='*60}")
    print(f"📊 Summary: {total_dupes} duplicate files wasting {format_size(total_wasted)}")
    print()
    
    # Ask to delete
    response = input("Delete all duplicates? (keeps the first copy of each) [y/N]: ").strip().lower()
    if response == 'y':
        deleted = 0
        for file_hash, files in duplicates.items():
            for fp in files[1:]:  # Skip first (keep it)
                try:
                    os.remove(fp)
                    print(f"  🗑  Deleted: {fp}")
                    deleted += 1
                except OSError as e:
                    print(f"  ⚠  Failed: {fp} ({e})")
        print(f"\n✅ Deleted {deleted} duplicate files.")
    else:
        # Save report instead
        report_path = os.path.join(root, "_duplicates_report.txt")
        with open(report_path, 'w') as f:
            for file_hash, files in duplicates.items():
                f.write(f"--- Duplicate set (hash: {file_hash[:12]}...) ---\n")
                for j, fp in enumerate(files):
                    marker = "KEEP" if j == 0 else "DELETE"
                    f.write(f"  [{marker}] {fp}\n")
                f.write("\n")
        print(f"\n📄 Report saved to: {report_path}")
        print("Review it, then re-run with 'y' to delete, or remove files manually.")

if __name__ == '__main__':
    main()
