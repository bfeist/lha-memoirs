#!/usr/bin/env python3
"""
Generalized transcript correction for Achen family memoirs.

This applies corrections to ANY memoir recording based on:
- Achen family names (Linden "Lindy" Achen, Zip, Phyllis, Sister Hilary, Sister Aloysia)
- Saskatchewan, Iowa, North Dakota, Montana place names
- Known company names (SaskPower, Finning, etc.)
- Common Whisper transcription errors

Usage:
    python correct_transcript.py <recording_name>
    python correct_transcript.py --all  # Process all recordings
    python correct_transcript.py <recording_name> --dry-run  # Preview only

Recordings:
    - memoirs/*: Linden "Lindy" Achen's memoir recordings
    - glynn_interview: Interview by Arlene Glynn
    - tibbits_cd: Tibbits family CD recordings
    - LHA_Sr.Hilary: Sister Hilary recordings
    - christmas1986: EXCLUDED (manually corrected)
"""

import re
import argparse
import sys
from pathlib import Path
from datetime import datetime

# Add scripts directory to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from transcript_utils import load_transcript, save_transcript, get_transcript_path

BASE_DIR = SCRIPT_DIR.parent
RECORDINGS_DIR = BASE_DIR / "public" / "recordings"
MEMOIRS_DIR = RECORDINGS_DIR / "memoirs"

# Recordings to skip (already manually corrected)
SKIP_RECORDINGS = {"christmas1986"}

# ============================================================================
# ACHEN FAMILY CORRECTIONS
# Lindy is Linden "Lindy" Achen
# ============================================================================
FAMILY_CORRECTIONS = [
    # Achen family name - all variants
    (r'\bAiken\b', 'Achen'),
    (r'\bAitken\b', 'Achen'),
    (r'\bAitkin\b', 'Achen'),
    (r'\bAchen Construction\b', 'Achen Construction'),
    
    # Note: Do NOT correct names of people who happen to be named Aiken
    # that aren't family. The corrections above are broad - review manually
    # if there are non-family Aikens mentioned.
]

# ============================================================================
# PLACE NAME CORRECTIONS - Saskatchewan and surrounding area
# ============================================================================
PLACE_CORRECTIONS = [
    # Saskatchewan cities/towns
    (r'\bYorktown\b', 'Yorkton'),
    (r'\bRose Town\b', 'Rosetown'),
    (r'\bRose town\b', 'Rosetown'),
    (r'\bGravelberg\b', 'Gravelbourg'),
    (r'\bGravellburg\b', 'Gravelbourg'),
    (r'\bHalgen\b', 'Elgin'),
    (r'\bShawtoven\b', 'Shaunavon'),
    (r'\bShoneman\b', 'Shaunavon'),
    (r'\bShawnevant\b', 'Shaunavon'),
    (r'\bSonovan\b', 'Shaunavon'),
    (r'\bShonovan\b', 'Shaunavon'),
    (r'\bEstadan\b', 'Estevan'),
    (r'\bEstaban\b', 'Estevan'),
    (r'\bBencoff\b', 'Bethune'),
    (r'\bOgamah\b', 'Ogema'),
    (r'\bDinsmoor\b', 'Dinsmore'),
    (r'\bSwift Currents\b', 'Swift Current'),
    (r'\bGuttalink\b', 'Gull Lake'),
    (r'\bWalmart\b', 'Wawota'),
    (r'\bAlbright\b', 'Halbrite'),
    (r'\bHalbright\b', 'Halbrite'),  # Another Whisper variant
    (r'\bMacoon\b', 'Macoun'),
    (r'\bKalali\b', 'Kelliher'),
    (r'\bBean Faith\b', 'Bienfait'),
    (r'\bbean faith\b', 'Bienfait'),
    
    # Manitoba
    (r'\bWinnipeg Oasis\b', 'Winnipegosis'),
    
    # Iowa - Lindy's birthplace
    (r'\bRamson\b', 'Remsen'),
    
    # Lloydminster (one word, Alberta/Saskatchewan border)
    (r'\bLloyd [Mm]inister\b', 'Lloydminster'),
    (r'\blloyd [Mm]inister\b', 'Lloydminster'),
    (r'\bLloyd [Mm]ister\b', 'Lloydminster'),
    
    # Peace River capitalization
    (r'\bpeace river\b', 'Peace River'),
    
    # Other known corrections from analysis
    (r'\bFrank Winner\b', 'Frank Wenner'),
    (r'\bfrank winner\b', 'Frank Wenner'),
]

# ============================================================================
# NAME CORRECTIONS - Sister Hilary spelling
# ============================================================================
NAME_CORRECTIONS = [
    # Sister Hilary (one L) - Lindy's sister
    (r'\bSister Hillary\b', 'Sister Hilary'),
    (r'\bsister Hillary\b', 'sister Hilary'),
    # Linden vs Lyndon
    (r'\bLyndon Hillary\b', 'Linden Hilary'),
    (r'\bAchen Lyndon Hillary\b', 'Achen, Linden Hilary'),
    # Brother's name - Lorry not Larry (context: brother at Sioux Falls)
    # Note: Only correct "Larry" when it appears to be referring to Lorry
    # This is tricky because Larry could be a different person
    (r'\bbrother,? Larry\b', 'brother Lorry'),
    (r'\bbrother Larry\b', 'brother Lorry'),
]

# ============================================================================
# COMPANY/ORGANIZATION CORRECTIONS
# ============================================================================
COMPANY_CORRECTIONS = [
    # SaskPower - Saskatchewan's provincial power company
    (r'\bland power\b', 'SaskPower'),
    (r'\bLand [Pp]ower\b', 'SaskPower'),
    
    # Finning - heavy equipment company
    # Only correct when in equipment context (tricky, so be conservative)
]

# ============================================================================
# COMMON WHISPER MISHEARINGS
# ============================================================================
PHONETIC_CORRECTIONS = [
    # Idioms and common phrases
    (r'\btake an ocean\b', 'take a notion'),
    (r'\bbeck in the wire\b', 'break in the wire'),
    
    # Common sound-alike errors
    (r'\bfanning\b(?=.*farm)', 'farming'),  # farming context
]

# ============================================================================
# HALLUCINATION PATTERNS (Whisper repetition bugs)
# ============================================================================
HALLUCINATION_PATTERNS = [
    # Repeated phrases (Whisper sometimes loops)
    r'(\b\w+\b)(\s+\1){3,}',  # Same word repeated 4+ times
    r'(,\s*\w+\s+\w+)(,\1){2,}',  # Same phrase repeated with commas
]


def compile_corrections() -> list[tuple[re.Pattern, str, str]]:
    """Compile all correction patterns into regex."""
    compiled = []
    
    all_corrections = [
        ("Family", FAMILY_CORRECTIONS),
        ("Place", PLACE_CORRECTIONS),
        ("Name", NAME_CORRECTIONS),
        ("Company", COMPANY_CORRECTIONS),
        ("Phonetic", PHONETIC_CORRECTIONS),
    ]
    
    for category, corrections in all_corrections:
        for pattern, replacement in corrections:
            try:
                compiled.append((
                    re.compile(pattern, re.IGNORECASE),
                    replacement,
                    category
                ))
            except re.error as e:
                print(f"  Warning: Invalid regex '{pattern}': {e}")
    
    return compiled


def fix_hallucinations(text: str) -> tuple[str, list[str]]:
    """Remove Whisper hallucination patterns (repeated text)."""
    changes = []
    new_text = text
    
    # Pattern: same word repeated 4+ times in a row
    pattern = re.compile(r'\b(\w+)(\s+\1){3,}\b', re.IGNORECASE)
    match = pattern.search(new_text)
    if match:
        word = match.group(1)
        changes.append(f"Removed repeated '{word}' (hallucination)")
        new_text = pattern.sub(word, new_text)
    
    # Pattern: "one of them, one of them, one of them..."
    pattern2 = re.compile(r'(\b[\w\s]+\b)(,\s*\1){2,}', re.IGNORECASE)
    match2 = pattern2.search(new_text)
    if match2:
        phrase = match2.group(1).strip()
        changes.append(f"Removed repeated '{phrase}' (hallucination)")
        new_text = pattern2.sub(phrase, new_text)
    
    return new_text, changes


def apply_corrections(text: str, patterns: list) -> tuple[str, list[str]]:
    """Apply all correction patterns to text."""
    changes = []
    new_text = text
    
    for pattern, replacement, category in patterns:
        matches = pattern.findall(new_text)
        for match in matches:
            if isinstance(match, tuple):
                match = match[0]
            # Only log if actually changing (not same case)
            if match != replacement:
                changes.append(f"[{category}] '{match}' -> '{replacement}'")
        new_text = pattern.sub(replacement, new_text)
    
    return new_text, changes


def find_recording_dir(recording_name: str) -> Path | None:
    """Find the directory for a recording (in memoirs or top-level)."""
    # Check memoirs subdirectory first
    memoirs_path = MEMOIRS_DIR / recording_name
    if memoirs_path.exists() and get_transcript_path(memoirs_path) is not None:
        return memoirs_path
    
    # Check top-level recordings directory
    top_level_path = RECORDINGS_DIR / recording_name
    if top_level_path.exists() and get_transcript_path(top_level_path) is not None:
        return top_level_path
    
    return None


def process_transcript(
    recording_name: str,
    dry_run: bool = False,
    verbose: bool = True
) -> dict:
    """Process a single transcript and apply corrections."""
    
    recording_dir = find_recording_dir(recording_name)
    if recording_dir is None:
        print(f"  ERROR: Recording '{recording_name}' not found")
        return {"error": "Recording not found"}
    
    input_path = recording_dir / "transcript.csv"
    
    # Load transcript
    data = load_transcript(recording_dir)
    if data is None:
        print(f"  ERROR: Could not load transcript from '{recording_name}'")
        return {"error": "Could not load transcript"}
    
    segments = data.get('segments', [])
    if verbose:
        print(f"  Loaded {len(segments)} segments")
    
    # Compile patterns
    patterns = compile_corrections()
    
    # Process each segment
    all_changes = []
    modified_count = 0
    
    for i, seg in enumerate(segments):
        original_text = seg['text']
        current_text = original_text
        segment_changes = []
        
        # Apply pattern corrections
        current_text, changes = apply_corrections(current_text, patterns)
        segment_changes.extend(changes)
        
        # Fix hallucinations
        current_text, hall_changes = fix_hallucinations(current_text)
        segment_changes.extend(hall_changes)
        
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
    if verbose:
        print(f"  Segments modified: {modified_count}")
        print(f"  Total corrections: {sum(len(c['changes']) for c in all_changes)}")
    
    if all_changes and verbose:
        print("\n  Changes:")
        for change in all_changes[:20]:  # Show first 20
            print(f"    [{change['segment']}] @ {change['time']:.1f}s")
            for c in change['changes']:
                print(f"        {c}")
        if len(all_changes) > 20:
            print(f"    ... and {len(all_changes) - 20} more")
    
    result = {
        'recording': recording_name,
        'segments_total': len(segments),
        'segments_modified': modified_count,
        'corrections': all_changes
    }
    
    if not dry_run and all_changes:
        # Backup original (preserve original file with appropriate extension)
        backup_suffix = input_path.suffix
        backup_path = recording_dir / f"transcript_original{backup_suffix}"
        if not backup_path.exists():
            import shutil
            shutil.copy(input_path, backup_path)
            if verbose:
                print(f"\n  Backup saved: {backup_path.name}")
        
        # Save corrected transcript as CSV
        data['segments'] = segments
        # Note: CSV format doesn't store metadata like _corrections
        # We save as CSV only
        output_path = save_transcript(recording_dir, data)
        
        if verbose:
            print(f"  Saved: {output_path.name}")
    
    return result


def get_all_recordings() -> list[str]:
    """Get list of all recordings with transcripts (excluding skipped ones)."""
    recordings = []
    
    # Get memoir recordings
    if MEMOIRS_DIR.exists():
        for d in MEMOIRS_DIR.iterdir():
            if d.is_dir() and get_transcript_path(d) is not None:
                if d.name not in SKIP_RECORDINGS:
                    recordings.append(d.name)
    
    # Get top-level recordings (glynn_interview, tibbits_cd, LHA_Sr.Hilary, etc.)
    for d in RECORDINGS_DIR.iterdir():
        if d.is_dir() and d.name != "memoirs" and get_transcript_path(d) is not None:
            if d.name not in SKIP_RECORDINGS:
                recordings.append(d.name)
    
    return sorted(recordings)


def main():
    parser = argparse.ArgumentParser(
        description='Apply corrections to memoir transcripts'
    )
    parser.add_argument(
        'recording',
        nargs='?',
        help='Recording name to process (or --all for all)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Process all memoir recordings'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without saving'
    )
    parser.add_argument(
        '--list',
        action='store_true',
        help='List available recordings'
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("ACHEN FAMILY TRANSCRIPT CORRECTIONS")
    print("=" * 60)
    print("\nRecordings include:")
    print("  - Memoir tapes: Narrator Linden 'Lindy' Achen")
    print("  - glynn_interview: Interviewer Arlene Glynn")
    print("  - tibbits_cd, LHA_Sr.Hilary: Family recordings")
    print(f"\nSkipping: {', '.join(SKIP_RECORDINGS)}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'APPLY'}")
    
    recordings = get_all_recordings()
    
    if args.list:
        print("\nAvailable recordings:")
        for r in recordings:
            print(f"  - {r}")
        return
    
    if args.all:
        to_process = recordings
    elif args.recording:
        if args.recording in SKIP_RECORDINGS:
            print(f"\nERROR: Recording '{args.recording}' is in skip list (already corrected)")
            return
        if args.recording not in recordings:
            # Check if it exists but has no transcript
            possible_dir = find_recording_dir(args.recording)
            if possible_dir is None:
                print(f"\nERROR: Recording '{args.recording}' not found")
                print(f"Available: {', '.join(recordings)}")
            else:
                print(f"\nERROR: Recording '{args.recording}' has no transcript.csv")
            return
        to_process = [args.recording]
    else:
        parser.print_help()
        print(f"\nAvailable recordings: {', '.join(recordings)}")
        return
    
    print(f"\nProcessing: {', '.join(to_process)}")
    
    results = []
    for rec in to_process:
        print(f"\n{'=' * 40}")
        print(f"Recording: {rec}")
        print("=" * 40)
        result = process_transcript(rec, dry_run=args.dry_run)
        results.append(result)
    
    # Final summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    total_modified = sum(r.get('segments_modified', 0) for r in results)
    total_corrections = sum(
        sum(len(c['changes']) for c in r.get('corrections', []))
        for r in results
    )
    
    print(f"\nRecordings processed: {len(results)}")
    print(f"Total segments modified: {total_modified}")
    print(f"Total corrections applied: {total_corrections}")
    
    if args.dry_run:
        print("\n[DRY RUN - no changes saved]")
    
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
