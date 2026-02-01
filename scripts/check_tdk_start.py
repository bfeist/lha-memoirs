#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.resolve()))
from transcript_utils import load_transcript

MEMOIRS_DIR = Path(__file__).parent.parent / 'public' / 'recordings' / 'memoirs'

tdk = load_transcript(MEMOIRS_DIR / 'TDK_D60_edited_through_air').get('segments', [])

def get_text(segs, start, end):
    return ' '.join([s['text'] for s in segs if s['end'] >= start and s['start'] < end])

# Check first 5 minutes of TDK to find where real story starts
for minute in range(0, 6):
    start = minute * 60
    end = (minute + 1) * 60
    text = get_text(tdk, start, end)
    print(f"\n=== TDK {minute}:00-{minute+1}:00 ===")
    print(text[:300] + "..." if len(text) > 300 else text)
