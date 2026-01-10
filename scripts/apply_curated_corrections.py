#!/usr/bin/env python3
"""
Apply curated corrections to Norm_red transcript.

This applies ONLY high-confidence corrections identified from Gemma analysis,
filtered to remove grammar/style edits. Focus on:
- Place name mishearings (Saskatchewan/Iowa/ND/Montana places)
- Family name: Achen (not Aiken) - the narrator is Linden "Lindy" Achen
- Known company names (SaskPower, Finning, etc.)
- Clear phonetic mishearings

DOES NOT apply:
- Grammar fixes (keeped→kept, give→gave)
- Style changes (bucks→dollars, boys→guys, fellas→fellows)
- Uncertain year changes
- Province guesses (Manitoba→Saskatchewan)
"""

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
TRANSCRIPTS_DIR = BASE_DIR / "public" / "recordings" / "memoirs"

# ============================================================================
# CURATED CORRECTIONS
# ============================================================================

# Family names - The narrator is Linden "Lindy" Achen
FAMILY_CORRECTIONS = {
    # All variations of Aiken/Aitken should be Achen
    r'\bAiken\b': 'Achen',
    r'\bAitken\b': 'Achen',
    r'\bAitkin\b': 'Achen',
    r'\bAchen Construction\b': 'Achen Construction',  # Company name
}

# Place name corrections - HIGH CONFIDENCE
PLACE_CORRECTIONS = {
    # Saskatchewan places
    r'\bYorktown\b': 'Yorkton',
    r'\bRose Town\b': 'Rosetown',
    r'\bRosetown\b': 'Rosetown',  # Ensure correct capitalization
    r'\bGravelberg\b': 'Gravelbourg',
    r'\bGravellburg\b': 'Gravelbourg',
    r'\bHalgen\b': 'Elgin',
    r'\bLloyd [Mm]inister\b': 'Lloydminster',
    r'\blloyd [Mm]inister\b': 'Lloydminster',
    r'\bShawtoven\b': 'Shaunavon',
    r'\bShoneman\b': 'Shaunavon',
    r'\bEstadan\b': 'Estevan',
    r'\bBencoff\b': 'Bethune',
    
    # Other places
    r'\bFrank Winner\b': 'Frank Wenner',
    r'\bfrank winner\b': 'Frank Wenner',
}

# Company/Organization corrections - HIGH CONFIDENCE
COMPANY_CORRECTIONS = {
    r'\bland power\b': 'SaskPower',
    r'\bLand [Pp]ower\b': 'SaskPower',
    r'\bfinance\b(?=.*equipment)': 'Finning',  # Only when near "equipment"
}

# Clear phonetic mishearings - HIGH CONFIDENCE
PHONETIC_CORRECTIONS = {
    r'\btake an ocean\b': 'take a notion',
    r'\bbeck in the wire\b': 'break in the wire',
    r'\bfanning\b(?=.*farm)': 'farming',  # Only in farming context
}

# Known names from context
NAME_CORRECTIONS = {
    # Will be applied carefully - these are common names in the region
    r'\bOgamah\b': 'Ogema',  # Town in Saskatchewan, not Shaunavon
}


def apply_corrections(text: str, corrections: dict[str, str], case_sensitive: bool = False) -> tuple[str, list[str]]:
    """
    Apply regex corrections to text.
    Returns (new_text, list_of_changes_made)
    """
    changes = []
    new_text = text
    
    flags = 0 if case_sensitive else re.IGNORECASE
    
    for pattern, replacement in corrections.items():
        regex = re.compile(pattern, flags)
        matches = regex.findall(new_text)
        if matches:
            for match in matches:
                if isinstance(match, tuple):
                    match = match[0]
                if match.lower() != replacement.lower():  # Only log if actually changing
                    changes.append(f"'{match}' -> '{replacement}'")
            new_text = regex.sub(replacement, new_text)
    
    return new_text, changes


def process_transcript(input_path: Path, output_path: Path, dry_run: bool = False):
    """Process the transcript and apply curated corrections."""
    
    print(f"\nLoading: {input_path}")
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    segments = data.get('segments', [])
    print(f"  {len(segments)} segments loaded")
    
    all_changes = []
    modified_count = 0
    
    # All correction sets to apply
    correction_sets = [
        ("Family names (Achen)", FAMILY_CORRECTIONS),
        ("Place names", PLACE_CORRECTIONS),
        ("Companies", COMPANY_CORRECTIONS),
        ("Phonetic fixes", PHONETIC_CORRECTIONS),
        ("Names", NAME_CORRECTIONS),
    ]
    
    for i, seg in enumerate(segments):
        original_text = seg['text']
        current_text = original_text
        segment_changes = []
        
        for set_name, corrections in correction_sets:
            current_text, changes = apply_corrections(current_text, corrections)
            segment_changes.extend(changes)
        
        if segment_changes:
            modified_count += 1
            all_changes.append({
                'segment': i,
                'time': seg['start'],
                'original': original_text,
                'corrected': current_text,
                'changes': segment_changes
            })
            
            if not dry_run:
                segments[i]['text'] = current_text
    
    # Summary
    print(f"\n{'=' * 60}")
    print("CORRECTION SUMMARY")
    print(f"{'=' * 60}")
    print(f"\nSegments modified: {modified_count}")
    print(f"Total corrections: {sum(len(c['changes']) for c in all_changes)}")
    
    if all_changes:
        print("\nChanges by segment:")
        for change in all_changes:
            print(f"\n  [{change['segment']}] @ {change['time']:.1f}s")
            for c in change['changes']:
                print(f"      {c}")
    
    if not dry_run and all_changes:
        # Update segments in data
        data['segments'] = segments
        
        # Add correction metadata
        data['_curated_corrections'] = {
            'total_modified': modified_count,
            'changes': all_changes
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\n\nSaved to: {output_path}")
    elif dry_run:
        print("\n\n[DRY RUN - no changes written]")
    
    return all_changes


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Apply curated transcript corrections')
    parser.add_argument('--dry-run', action='store_true', help='Preview without saving')
    parser.add_argument('--input', default='transcript_corrected.json',
                        help='Input transcript file (default: transcript_corrected.json)')
    parser.add_argument('--output', default='transcript_curated.json',
                        help='Output file (default: transcript_curated.json)')
    args = parser.parse_args()
    
    recording = "Norm_red"
    input_path = TRANSCRIPTS_DIR / recording / args.input
    output_path = TRANSCRIPTS_DIR / recording / args.output
    
    print("=" * 60)
    print("CURATED TRANSCRIPT CORRECTIONS")
    print("=" * 60)
    print(f"\nNarrator: Linden 'Lindy' Achen")
    print(f"Family: Brother Zip, Sisters Hilary & Aloysia (nuns)")
    print(f"Wife: Phyllis, Friends: Hugo, Tilley")
    print(f"\nInput:  {input_path}")
    print(f"Output: {output_path}")
    print(f"Mode:   {'DRY RUN' if args.dry_run else 'APPLY'}")
    
    if not input_path.exists():
        # Fall back to original transcript
        input_path = TRANSCRIPTS_DIR / recording / "transcript.json"
        print(f"\n[!] transcript_corrected.json not found, using: {input_path}")
    
    process_transcript(input_path, output_path, dry_run=args.dry_run)
    
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
