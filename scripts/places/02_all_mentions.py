#!/usr/bin/env python3
"""
Find all mentions of known places across all transcript files.

This script takes the existing places.json file and searches all transcript
files for every mention of each place name, updating the mentions array
with any new occurrences found.

Run with: uv run 02_all_mentions.py

The script will:
1. Load the existing places.json file
2. Iterate through all transcript.csv files
3. Search for each place name in the transcript text
4. Upsert mentions by (transcript, startSecs) to avoid duplicates
5. Save the updated places.json file

Options:
  --dry-run: Show what would be found without saving
  --verbose: Print each mention as it's found

Requires: tqdm (for progress bar)
"""

import json
import re
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Set
from datetime import datetime

try:
    from tqdm import tqdm
except ImportError:
    print("Missing required package: tqdm")
    print("Install with: uv pip install tqdm")
    sys.exit(1)

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
RECORDINGS_DIR = PROJECT_ROOT / "public" / "recordings"
PLACES_FILE = PROJECT_ROOT / "public" / "places.json"

# Add scripts directory to path for imports
sys.path.insert(0, str(SCRIPT_DIR.parent))
from transcript_utils import read_transcript_csv


def find_all_transcripts() -> List[Path]:
    """Find all transcript.csv files in the recordings directory."""
    transcripts = []
    for transcript_path in RECORDINGS_DIR.rglob("transcript.csv"):
        transcripts.append(transcript_path)
    return sorted(transcripts)


def get_transcript_id(transcript_path: Path) -> str:
    """Get the transcript ID (relative path from recordings dir) for a transcript file.
    
    Example: memoirs/Norm_red
    """
    rel_path = transcript_path.parent.relative_to(RECORDINGS_DIR)
    return str(rel_path).replace("\\", "/")


def build_place_patterns(places: List[Dict]) -> Dict[str, re.Pattern]:
    """Build regex patterns for each place name.
    
    Returns a dict mapping place name to compiled regex pattern.
    The patterns look for the place name as a whole word (case-insensitive).
    """
    patterns = {}
    for place in places:
        name = place["name"]
        # Create pattern that matches the place name as a whole word
        # Use word boundaries, but handle special cases like hyphenated names
        escaped_name = re.escape(name)
        # Allow for slight variations (e.g., "Saint" vs "St.")
        if name.startswith("Saint "):
            alt_name = "St\\.? " + re.escape(name[6:])
            pattern = rf'\b({escaped_name}|{alt_name})\b'
        elif name.startswith("St. "):
            alt_name = "Saint " + re.escape(name[4:])
            pattern = rf'\b({escaped_name}|{alt_name})\b'
        else:
            pattern = rf'\b{escaped_name}\b'
        
        patterns[name] = re.compile(pattern, re.IGNORECASE)
    
    return patterns


def find_mentions_in_segment(
    text: str,
    start_secs: float,
    end_secs: float,
    transcript_id: str,
    patterns: Dict[str, re.Pattern],
    context_window: int = 200
) -> List[Dict]:
    """Find all place mentions in a transcript segment.
    
    Args:
        text: The segment text
        start_secs: The segment start time in seconds
        end_secs: The segment end time in seconds
        transcript_id: The transcript identifier
        patterns: Dict of place name -> regex pattern
        context_window: How many characters of context to include around the match
    
    Returns:
        List of mention dicts: {place_name, transcript, context, startSecs, endSecs}
    """
    mentions = []
    
    for place_name, pattern in patterns.items():
        for match in pattern.finditer(text):
            # Extract context around the match
            start = max(0, match.start() - context_window // 2)
            end = min(len(text), match.end() + context_window // 2)
            context = text[start:end].strip()
            
            # Add ellipsis if we truncated
            if start > 0:
                context = "..." + context
            if end < len(text):
                context = context + "..."
            
            mentions.append({
                "place_name": place_name,
                "transcript": transcript_id,
                "context": context,
                "startSecs": start_secs,
                "endSecs": end_secs
            })
    
    return mentions


def upsert_mention(place: Dict, mention: Dict) -> bool:
    """Add a mention to a place if it doesn't already exist.
    
    Uses (transcript, startSecs) as the unique key.
    
    Returns True if the mention was added, False if it already existed.
    """
    if "mentions" not in place:
        place["mentions"] = []
    
    # Check if this exact mention already exists
    for existing in place["mentions"]:
        if (existing.get("transcript") == mention["transcript"] and 
            existing.get("startSecs") == mention["startSecs"]):
            return False
    
    # Add the new mention
    place["mentions"].append({
        "transcript": mention["transcript"],
        "context": mention["context"],
        "startSecs": mention["startSecs"],
        "endSecs": mention["endSecs"]
    })
    return True


def sort_mentions(place: Dict) -> None:
    """Sort mentions by transcript, then by startSecs."""
    if "mentions" in place:
        place["mentions"].sort(key=lambda m: (m.get("transcript", ""), m.get("startSecs", 0)))


def main():
    parser = argparse.ArgumentParser(description="Find all mentions of known places in transcripts")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be found without saving")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print each mention as it's found")
    args = parser.parse_args()
    
    # Load existing places
    if not PLACES_FILE.exists():
        print(f"[ERROR] Places file not found: {PLACES_FILE}")
        print("Please run 01_find_placenames.py first.")
        sys.exit(1)
    
    print(f"[LOAD] Loading places from {PLACES_FILE}")
    with open(PLACES_FILE, "r", encoding="utf-8") as f:
        places_data = json.load(f)
    
    places = places_data.get("places", [])
    print(f"       Found {len(places)} places")
    
    # Build regex patterns for each place
    print("[BUILD] Building search patterns...")
    patterns = build_place_patterns(places)
    
    # Create a lookup dict for places by name
    places_by_name = {p["name"]: p for p in places}
    
    # Find all transcripts
    transcripts = find_all_transcripts()
    print(f"[SCAN] Found {len(transcripts)} transcript files")
    
    # Track statistics
    total_new_mentions = 0
    total_existing_mentions = 0
    mentions_by_place = {}
    
    # Process each transcript
    for transcript_path in tqdm(transcripts, desc="Processing transcripts"):
        transcript_id = get_transcript_id(transcript_path)
        
        # Load transcript
        try:
            data = read_transcript_csv(transcript_path)
            segments = data.get("segments", [])
        except Exception as e:
            print(f"\n[WARN] Error reading {transcript_path}: {e}")
            continue
        
        # Search each segment for place mentions
        for segment in segments:
            text = segment.get("text", "")
            start_secs = segment.get("start", 0)
            end_secs = segment.get("end", 0)
            
            # Find all mentions in this segment
            mentions = find_mentions_in_segment(
                text=text,
                start_secs=start_secs,
                end_secs=end_secs,
                transcript_id=transcript_id,
                patterns=patterns
            )
            
            # Upsert each mention
            for mention in mentions:
                place_name = mention["place_name"]
                place = places_by_name.get(place_name)
                
                if place:
                    was_added = upsert_mention(place, mention)
                    
                    if was_added:
                        total_new_mentions += 1
                        mentions_by_place[place_name] = mentions_by_place.get(place_name, 0) + 1
                        
                        if args.verbose:
                            print(f"\n  + {place_name} in {transcript_id} @ {mention['startSecs']:.1f}s")
                            print(f"    \"{mention['context'][:100]}...\"")
                    else:
                        total_existing_mentions += 1
    
    # Sort mentions for each place
    print("\n[SORT] Sorting mentions...")
    for place in places:
        sort_mentions(place)
    
    # Print summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Total new mentions found: {total_new_mentions}")
    print(f"Already existing mentions: {total_existing_mentions}")
    
    if mentions_by_place:
        print(f"\nNew mentions by place (top 20):")
        sorted_places = sorted(mentions_by_place.items(), key=lambda x: -x[1])
        for place_name, count in sorted_places[:20]:
            print(f"  {place_name}: +{count}")
        if len(sorted_places) > 20:
            print(f"  ... and {len(sorted_places) - 20} more places")
    
    # Save updated places
    if args.dry_run:
        print("\n[DRY-RUN] Not saving changes")
    else:
        # Update metadata
        places_data["metadata"]["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"\n[SAVE] Saving to {PLACES_FILE}")
        with open(PLACES_FILE, "w", encoding="utf-8") as f:
            json.dump(places_data, f, indent=2, ensure_ascii=False)
        print("[DONE] Complete!")


if __name__ == "__main__":
    main()
