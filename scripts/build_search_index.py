#!/usr/bin/env python3
"""
Build a search index from all transcript CSV files.
Run with: uv run scripts/build_search_index.py

Processes all transcript.csv files in public/recordings/ (including nested folders)
and generates a compressed JSON search index at public/search-index.json.

The search index uses short keys to minimize file size:
  - r = recording path (e.g., "memoirs/Norm_red")
  - t = recording title
  - s = start time
  - e = end time
  - x = original text
  - n = normalized text (lowercase, trimmed)
  - i = segment index
"""

import json
import sys
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from transcript_utils import load_transcript

# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent
RECORDINGS_DIR = PROJECT_ROOT / "public" / "recordings"
OUTPUT_PATH = PROJECT_ROOT / "public" / "search-index.json"


def get_recording_title(recording_path: str) -> str:
    """
    Get a display title for the recording based on its path.
    """
    # Map known paths to titles
    title_map = {
        "christmas1986": "Christmas 1986",
        "glynn_interview": "Glynn Interview",
        "LHA_Sr.Hilary": "Sister Hilary Recording",
        "tibbits_cd": "Tibbits CD",
        "memoirs/Norm_red": "Memoirs",
        "memoirs/TDK_D60_edited_through_air": "Memoirs - Draft Telling",
    }
    
    if recording_path in title_map:
        return title_map[recording_path]
    
    # Fallback: convert path to title
    name = recording_path.split("/")[-1]
    return name.replace("_", " ").title()


def normalize_text(text: str) -> str:
    """Normalize text for case-insensitive searching."""
    return text.lower().strip()


def build_search_index() -> dict:
    """
    Build search index from all transcript CSV files.
    
    Returns:
        dict with 'index' key containing list of indexed segments
    """
    index = []
    transcript_count = 0
    segment_count = 0
    
    # Find all transcript.csv files recursively
    transcript_files = sorted(RECORDINGS_DIR.rglob("transcript.csv"))
    
    print(f"Found {len(transcript_files)} transcript files")
    print()
    
    for transcript_path in transcript_files:
        # Get recording path relative to recordings directory
        recording_dir = transcript_path.parent
        recording_path_rel = recording_dir.relative_to(RECORDINGS_DIR)
        recording_path_str = str(recording_path_rel).replace("\\", "/")
        
        # Load transcript
        transcript_data = load_transcript(recording_dir)
        if not transcript_data:
            print(f"⚠️  Skipping {recording_path_str}: Failed to load")
            continue
        
        segments = transcript_data.get("segments", [])
        if not segments:
            print(f"⚠️  Skipping {recording_path_str}: No segments")
            continue
        
        # Get recording title
        recording_title = get_recording_title(recording_path_str)
        
        # Process each segment
        segments_added = 0
        for i, segment in enumerate(segments):
            text = segment.get("text", "").strip()
            
            # Skip empty segments
            if not text:
                continue
            
            # Add to index with short keys
            index.append({
                "r": recording_path_str,  # recording path
                "t": recording_title,      # recording title
                "s": segment["start"],     # start time
                "e": segment["end"],       # end time
                "x": text,                 # original text
                "n": normalize_text(text), # normalized text
                "i": i,                    # segment index
            })
            
            segments_added += 1
        
        transcript_count += 1
        segment_count += segments_added
        print(f"✓ {recording_path_str}: {segments_added} segments")
    
    return {"index": index}, transcript_count, segment_count


def main():
    """Build and save search index."""
    print("Building search index from transcripts...")
    print(f"Recordings directory: {RECORDINGS_DIR}")
    print()
    
    # Build index
    search_index, transcript_count, segment_count = build_search_index()
    
    # Save to JSON
    print()
    print(f"Writing search index to {OUTPUT_PATH}")
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(search_index, f, separators=(",", ":"), ensure_ascii=False)
    
    # Get file size
    file_size = OUTPUT_PATH.stat().st_size
    file_size_kb = file_size / 1024
    file_size_mb = file_size_kb / 1024
    
    # Print statistics
    print()
    print("=" * 50)
    print("Search Index Statistics:")
    print(f"  Transcripts processed: {transcript_count}")
    print(f"  Total segments indexed: {segment_count}")
    print(f"  Output file size: {file_size_mb:.2f} MB ({file_size_kb:.1f} KB)")
    print("=" * 50)
    print()
    print("✅ Search index built successfully!")


if __name__ == "__main__":
    main()
