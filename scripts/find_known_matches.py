#!/usr/bin/env python3
"""Find known story matches to calibrate window sizes."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.resolve()))
from transcript_utils import load_transcript

MEMOIRS_DIR = Path(__file__).parent.parent / 'public' / 'recordings' / 'memoirs'

norm = load_transcript(MEMOIRS_DIR / 'Norm_red').get('segments', [])
tdk = load_transcript(MEMOIRS_DIR / 'TDK_D60_edited_through_air').get('segments', [])

def get_text(segs, start, end):
    return ' '.join([s['text'] for s in segs if s['end'] >= start and s['start'] < end])

def format_time(seconds):
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"

# Known matches based on grep:
# "Daylight in the swamp" - Norm: 3152s (52:32), TDK: 3119s (51:59)
# "all the glass" - Norm: 3244s (54:04), TDK: 3275s (54:35)

print("="*70)
print("KNOWN MATCH 1: 'Daylight in the swamp' story")
print("="*70)

# Get surrounding context (2 min before, 1 min after)
norm_start, norm_center = 3060, 3152
tdk_start, tdk_center = 3030, 3119

print(f"\nNORM_RED around {format_time(norm_center)}:")
print(f"  Context: {format_time(norm_start)} - {format_time(norm_center + 60)}")
print("-"*70)
print(get_text(norm, norm_start, norm_center + 60))

print(f"\nTDK around {format_time(tdk_center)}:")
print(f"  Context: {format_time(tdk_start)} - {format_time(tdk_center + 60)}")
print("-"*70)
print(get_text(tdk, tdk_start, tdk_center + 60))

print("\n" + "="*70)
print("KNOWN MATCH 2: 'all the glass' car accident story")
print("="*70)

# "all the glass" - Norm: 3244s (54:04), TDK: 3275s (54:35)
norm_start, norm_center = 3180, 3244
tdk_start, tdk_center = 3200, 3275

print(f"\nNORM_RED around {format_time(norm_center)}:")
print(f"  Context: {format_time(norm_start)} - {format_time(norm_center + 60)}")
print("-"*70)
print(get_text(norm, norm_start, norm_center + 60))

print(f"\nTDK around {format_time(tdk_center)}:")
print(f"  Context: {format_time(tdk_start)} - {format_time(tdk_center + 60)}")
print("-"*70)
print(get_text(tdk, tdk_start, tdk_center + 60))

print("\n" + "="*70)
print("TIME DIFFERENCES:")
print("="*70)
print(f"'Daylight in swamp': Norm={format_time(3152)}, TDK={format_time(3119)}, diff={3152-3119}s")
print(f"'all the glass': Norm={format_time(3244)}, TDK={format_time(3275)}, diff={3275-3244}s")
print("\nNote: These stories are ~90s apart in Norm but ~150s apart in TDK")
print("The recordings are NOT in sync - stories appear at different times!")
