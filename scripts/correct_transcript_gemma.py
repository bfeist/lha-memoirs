#!/usr/bin/env python3
"""
Fuzzy transcript correction using Gemma LLM.

This uses Gemma's knowledge of:
- Real place names in Saskatchewan, Iowa, North Dakota, Montana
- Common Whisper transcription errors
- Context clues from surrounding text

IMPORTANT: This only corrects likely MISHEARINGS, not grammar or meaning.
The transcript will be used as audio captions, so we preserve the speaker's
actual words - we're just fixing what Whisper got wrong.
"""

import json
import re
import subprocess
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

BASE_DIR = Path(__file__).parent.parent
TRANSCRIPTS_DIR = BASE_DIR / "public" / "recordings" / "memoirs"

# Batch size - how many segments to send to Gemma at once
BATCH_SIZE = 10

# Known place names in the region for context
KNOWN_PLACES = """
Saskatchewan: Regina, Estevan, Moose Jaw, Saskatoon, Yorkton, Gravelbourg, Swift Current, 
Weyburn, Lloydminster, Prince Albert, Maple Creek, Kindersley, Humboldt, Melfort, Tisdale,
Bigger, Tompkins, Shaunavon, Assiniboia, Wilkie, Rosetown, Outlook, Cabri

Iowa: Mars (small town), Des Moines, Sioux City, Cedar Rapids, Davenport, Council Bluffs,
Dubuque, Waterloo, Iowa City, Ames, Mason City, Fort Dodge, Burlington, Ottumwa, Muscatine

North Dakota: Elgin, Thunderhawk, Portal, Minot, Bismarck, Fargo, Grand Forks, Williston,
Dickinson, Mandan, Jamestown, Devils Lake, Mohall, Crosby, Bowbells, Mohawk

Montana: Miles City, Billings, Great Falls, Missoula, Helena, Butte, Bozeman, Havre, Glendive
"""


def call_gemma(prompt: str, model: str = "gemma3:12b") -> str:
    """Call Gemma via Ollama and return the response."""
    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
            encoding='utf-8'
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "ERROR: Timeout"
    except Exception as e:
        return f"ERROR: {e}"


def load_transcript(name: str) -> list[dict]:
    """Load transcript segments."""
    path = TRANSCRIPTS_DIR / name / "transcript.json"
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('segments', [])


def format_segments_for_review(segments: list[dict], start_idx: int) -> str:
    """Format a batch of segments for Gemma review."""
    lines = []
    for i, seg in enumerate(segments):
        idx = start_idx + i
        lines.append(f"[{idx}] {seg['text']}")
    return "\n".join(lines)


def create_correction_prompt(segments_text: str) -> str:
    """Create the prompt for Gemma to identify transcription errors."""
    return f"""You are reviewing a transcript of audio recordings made in Saskatchewan, Canada and Iowa/North Dakota, USA in the 1980s. The speaker is discussing his life working for power companies and as an electrical contractor.

The transcript was created by Whisper AI and may contain MISHEARINGS - words that sound similar but are wrong. Your job is to identify likely transcription errors.

IMPORTANT RULES:
1. ONLY fix clear mishearings (words that sound similar to the correct word)
2. DO NOT fix grammar, word choice, or sentence structure
3. DO NOT add or remove words for meaning
4. Focus especially on proper nouns: place names, person names, company names
5. This is a verbatim transcript for audio captions - preserve the speaker's actual words

Known places in this region:
{KNOWN_PLACES}

Common Whisper errors to look for:
- Place names spelled phonetically wrong (e.g., "Yorktown" should be "Yorkton")
- "Lloyd Minister" should be "Lloydminster" (one word, city on Alberta/Saskatchewan border)
- Names that sound similar but are misspelled
- Numbers that might be wrong based on context

TRANSCRIPT TO REVIEW:
{segments_text}

For each segment with a likely error, respond in this exact format:
SEGMENT [number]: "wrong word/phrase" -> "correct word/phrase" | REASON: brief explanation

If a segment has no errors, do not mention it.
If you're not confident (less than 80% sure), do not suggest the correction.

Only list corrections, nothing else. If no corrections needed, respond with: NO CORRECTIONS NEEDED"""


def parse_gemma_response(response: str) -> list[dict]:
    """Parse Gemma's correction suggestions."""
    corrections = []
    
    for line in response.strip().split('\n'):
        line = line.strip()
        if not line or line == "NO CORRECTIONS NEEDED":
            continue
        
        # Parse format: SEGMENT [number]: "wrong" -> "correct" | REASON: explanation
        match = re.match(
            r'SEGMENT\s*\[?(\d+)\]?:\s*["\']?([^"\']+)["\']?\s*->\s*["\']?([^"\'|]+)["\']?\s*\|\s*REASON:\s*(.+)',
            line,
            re.IGNORECASE
        )
        
        if match:
            corrections.append({
                'segment_idx': int(match.group(1)),
                'wrong': match.group(2).strip(),
                'correct': match.group(3).strip(),
                'reason': match.group(4).strip()
            })
        else:
            # Try simpler format: SEGMENT [number]: "wrong" -> "correct"
            match2 = re.match(
                r'SEGMENT\s*\[?(\d+)\]?:\s*["\']?([^"\']+)["\']?\s*->\s*["\']?([^"\']+)["\']?',
                line,
                re.IGNORECASE
            )
            if match2:
                corrections.append({
                    'segment_idx': int(match2.group(1)),
                    'wrong': match2.group(2).strip(),
                    'correct': match2.group(3).strip(),
                    'reason': 'No reason provided'
                })
    
    return corrections


def apply_correction(text: str, wrong: str, correct: str) -> tuple[str, bool]:
    """Apply a single correction to text, return (new_text, was_applied)."""
    # Case-insensitive search
    pattern = re.compile(re.escape(wrong), re.IGNORECASE)
    
    if pattern.search(text):
        new_text = pattern.sub(correct, text)
        return new_text, True
    
    return text, False


def review_transcript_with_gemma(
    segments: list[dict],
    recording_name: str,
    dry_run: bool = False,
    batch_size: int = 10
) -> tuple[list[dict], list[dict]]:
    """
    Review entire transcript with Gemma in batches.
    Returns (corrected_segments, all_corrections_made)
    """
    all_corrections = []
    corrected_segments = [dict(s) for s in segments]  # Deep copy
    
    total_batches = (len(segments) + batch_size - 1) // batch_size
    
    print(f"\nProcessing {len(segments)} segments in {total_batches} batches...")
    print("=" * 60)
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(segments))
        batch = segments[start_idx:end_idx]
        
        print(f"\nBatch {batch_num + 1}/{total_batches} (segments {start_idx}-{end_idx-1})...")
        
        # Format segments for review
        segments_text = format_segments_for_review(batch, start_idx)
        prompt = create_correction_prompt(segments_text)
        
        # Call Gemma
        response = call_gemma(prompt)
        
        # Show Gemma's raw response
        print(f"\n  --- GEMMA RESPONSE ---")
        print(f"  {response}")
        print(f"  --- END RESPONSE ---\n")
        
        if response.startswith("ERROR"):
            print(f"  {response}")
            continue
        
        # Parse corrections
        corrections = parse_gemma_response(response)
        
        if not corrections:
            print("  No corrections suggested")
            continue
        
        print(f"  Found {len(corrections)} potential corrections:")
        
        for corr in corrections:
            idx = corr['segment_idx']
            
            if idx < 0 or idx >= len(corrected_segments):
                print(f"    [SKIP] Invalid segment index: {idx}")
                continue
            
            original_text = corrected_segments[idx]['text']
            new_text, applied = apply_correction(original_text, corr['wrong'], corr['correct'])
            
            if applied:
                print(f"    [{idx}] '{corr['wrong']}' -> '{corr['correct']}'")
                print(f"         Reason: {corr['reason']}")
                
                if not dry_run:
                    corrected_segments[idx]['text'] = new_text
                
                all_corrections.append({
                    'segment_idx': idx,
                    'time': segments[idx]['start'],
                    'original': original_text,
                    'corrected': new_text,
                    'wrong': corr['wrong'],
                    'correct': corr['correct'],
                    'reason': corr['reason']
                })
            else:
                print(f"    [SKIP] Could not find '{corr['wrong']}' in segment {idx}")
    
    return corrected_segments, all_corrections


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Fuzzy transcript correction using Gemma')
    parser.add_argument('recording', nargs='?', default='Norm_red',
                        help='Recording name (default: Norm_red)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show corrections without applying them')
    parser.add_argument('--batch-size', type=int, default=10,
                        help='Segments per batch (default: 10)')
    args = parser.parse_args()
    
    batch_size = args.batch_size
    
    print("=" * 70)
    print("FUZZY TRANSCRIPT CORRECTION WITH GEMMA")
    print("=" * 70)
    print(f"\nRecording: {args.recording}")
    print(f"Batch size: {batch_size}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'APPLYING CORRECTIONS'}")
    
    # Load transcript
    print("\nLoading transcript...")
    segments = load_transcript(args.recording)
    print(f"  Loaded {len(segments)} segments")
    
    # Process with Gemma
    corrected_segments, all_corrections = review_transcript_with_gemma(
        segments, 
        args.recording,
        dry_run=args.dry_run,
        batch_size=batch_size
    )
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"\nTotal corrections: {len(all_corrections)}")
    
    if all_corrections:
        print("\nAll corrections:")
        for corr in all_corrections:
            print(f"\n  [{corr['time']:.1f}s] '{corr['wrong']}' -> '{corr['correct']}'")
            print(f"    Reason: {corr['reason']}")
    
    if not args.dry_run and all_corrections:
        # Save corrected transcript
        output_path = TRANSCRIPTS_DIR / args.recording / "transcript_gemma_corrected.json"
        
        with open(TRANSCRIPTS_DIR / args.recording / "transcript.json", 'r', encoding='utf-8') as f:
            original_data = json.load(f)
        
        corrected_data = {
            **original_data,
            'segments': corrected_segments,
            '_gemma_corrections': {
                'total_corrections': len(all_corrections),
                'corrections': all_corrections
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(corrected_data, f, indent=2, ensure_ascii=False)
        
        print(f"\nCorrected transcript saved to: {output_path}")
        
        # Save correction report
        report_path = BASE_DIR / "scripts" / f"{args.recording}_gemma_corrections.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump({
                'recording': args.recording,
                'total_corrections': len(all_corrections),
                'corrections': all_corrections
            }, f, indent=2, ensure_ascii=False)
        
        print(f"Correction report saved to: {report_path}")
    
    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    main()
