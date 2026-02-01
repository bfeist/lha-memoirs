#!/usr/bin/env python3
"""
Quick test to verify the 05b script can detect the known matching stories.
Tests the specific time ranges where we know matches exist.
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from transcript_utils import load_transcript

# Import from main script
from importlib.machinery import SourceFileLoader
main_script = SourceFileLoader("main", str(SCRIPT_DIR / "05b_find_story_overlaps_v2.py")).load_module()

MEMOIRS_DIR = SCRIPT_DIR.parent / "public" / "recordings" / "memoirs"

def format_time(seconds):
    return f"{int(seconds//60)}:{int(seconds%60):02d}"

def test_known_matches():
    print("Loading transcripts...")
    norm_data = load_transcript(MEMOIRS_DIR / "Norm_red")
    tdk_data = load_transcript(MEMOIRS_DIR / "TDK_D60_edited_through_air")
    
    norm_transcript = norm_data.get('segments', [])
    tdk_transcript = tdk_data.get('segments', [])
    
    # Known matching stories (with 90s window margin):
    # 1. "Daylight in swamp": Norm ~3000-3250, TDK ~2980-3230
    # 2. "Car accident": Norm ~3150-3350, TDK ~3150-3400
    
    # Create windows just for test range using the main script's function
    print("\nCreating test windows for known match range (3000-3400s)...")
    
    # Build windows around known match area
    norm_windows = main_script.create_windows(
        norm_transcript, 
        window_duration=main_script.WINDOW_DURATION,
        overlap=main_script.WINDOW_OVERLAP,
        min_time=3000,  # Focus on match area
    )
    norm_windows = [w for w in norm_windows if w.start_time < 3400]
    
    tdk_windows = main_script.create_windows(
        tdk_transcript,
        window_duration=main_script.WINDOW_DURATION,
        overlap=main_script.WINDOW_OVERLAP,
        min_time=2950,  # Slightly earlier for TDK
    )
    tdk_windows = [w for w in tdk_windows if w.start_time < 3400]
    
    print(f"  Norm windows: {len(norm_windows)} (from {format_time(norm_windows[0].start_time)} to {format_time(norm_windows[-1].end_time)})")
    print(f"  TDK windows: {len(tdk_windows)} (from {format_time(tdk_windows[0].start_time)} to {format_time(tdk_windows[-1].end_time)})")
    
    # Extract topics for each window using batch method
    print("\nExtracting topics from Norm windows...")
    norm_windows = main_script.extract_topics_batch(norm_windows, "Norm_red", main_script.MODEL)
    for i, w in enumerate(norm_windows):
        print(f"  [{i}] {format_time(w.start_time)}-{format_time(w.end_time)}: {', '.join(w.topics[:3]) if w.topics else '(none)'}")
    
    print("\nExtracting topics from TDK windows...")
    tdk_windows = main_script.extract_topics_batch(tdk_windows, "TDK", main_script.MODEL)
    for i, w in enumerate(tdk_windows):
        print(f"  [{i}] {format_time(w.start_time)}-{format_time(w.end_time)}: {', '.join(w.topics[:3]) if w.topics else '(none)'}")
    
    # Find matches
    print("\nComparing windows for matches...")
    matches = main_script.find_story_matches(norm_windows, tdk_windows, main_script.MODEL, verbose=False)
    
    print(f"\n{'='*60}")
    print(f"RESULTS: Found {len(matches)} matches")
    print(f"{'='*60}")
    
    for m in matches:
        print(f"\n  Norm {format_time(m.norm_start)}-{format_time(m.norm_end)} <-> TDK {format_time(m.tdk_start)}-{format_time(m.tdk_end)}")
        print(f"  Score: {m.score}, Topic: {m.topic}")
        
    # Check if we found the known matches
    found_daylight = any(
        m.norm_start <= 3152 <= m.norm_end and m.tdk_start <= 3119 <= m.tdk_end 
        for m in matches
    )
    found_accident = any(
        m.norm_start <= 3244 <= m.norm_end and m.tdk_start <= 3275 <= m.tdk_end 
        for m in matches
    )
    
    print(f"\n{'='*60}")
    print(f"KNOWN MATCH DETECTION:")
    print(f"  'Daylight in swamp' (Norm ~3152s, TDK ~3119s): {'✓ FOUND' if found_daylight else '✗ MISSED'}")
    print(f"  'Car accident' (Norm ~3244s, TDK ~3275s): {'✓ FOUND' if found_accident else '✗ MISSED'}")
    print(f"{'='*60}")
    
    return matches

if __name__ == "__main__":
    test_known_matches()
