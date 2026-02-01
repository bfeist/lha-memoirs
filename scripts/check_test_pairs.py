#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.resolve()))
from transcript_utils import load_transcript

MEMOIRS_DIR = Path(__file__).parent.parent / 'public' / 'recordings' / 'memoirs'

norm = load_transcript(MEMOIRS_DIR / 'Norm_red').get('segments', [])
tdk = load_transcript(MEMOIRS_DIR / 'TDK_D60_edited_through_air').get('segments', [])

def get_text(segs, start, end):
    return ' '.join([s['text'] for s in segs if s['end'] >= start and s['start'] < end])

print('='*60)
print('TEST PAIR: Dads death and funeral')
print('='*60)
print('NORM 34:00-35:00:')
print(get_text(norm, 2040, 2100))
print()
print('TDK 28:30-30:00:')
print(get_text(tdk, 1710, 1800))
print()
print('='*60)
print('TEST PAIR: Martin Twight separator')
print('='*60)
print('NORM 58:30-59:30:')
print(get_text(norm, 3510, 3570))
print()
print('TDK 50:30-51:30:')
print(get_text(tdk, 3030, 3090))
