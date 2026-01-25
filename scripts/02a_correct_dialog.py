#!/usr/bin/env python3
"""
Correct dialog punctuation in transcripts using Ollama LLM.

This script identifies dialog segments (e.g., "I said", "he said") and adds
proper punctuation (quotation marks, commas) to the spoken dialog.
Transcripts are in CSV format (transcript.csv).
Usage:
    python 02a_correct_dialog.py <recording_name>
    python 02a_correct_dialog.py --all  # Process all recordings
    python 02a_correct_dialog.py <recording_name> --dry-run  # Preview only

Requires: pip install ollama
Or with uv: uv pip install ollama

Make sure Ollama is running locally with a model like:
  - ollama run gemma3:12b
"""

import re
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add scripts directory to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from transcript_utils import load_transcript, save_transcript, get_transcript_path

# Check for required packages
try:
    import ollama
except ImportError as e:
    print(f"\nMissing required package: {e}")
    print("\nInstall with:")
    print("  uv pip install ollama")
    sys.exit(1)

BASE_DIR = SCRIPT_DIR.parent
RECORDINGS_DIR = BASE_DIR / "public" / "recordings"
MEMOIRS_DIR = RECORDINGS_DIR / "memoirs"

# Recordings to skip (already manually corrected)
SKIP_RECORDINGS = {}

# Model preferences (same as 04_analyze_chapters.py)
PREFERRED_MODEL = "gemma3:12b"
MODELS_TO_TRY = ["gemma3:12b", "qwen3:14b", "gpt-oss:20b", "devstral:24b", "gemma3:27b"]

# Patterns that indicate dialog
DIALOG_PATTERNS = [
    r'\bI said\b',
    r'\bhe said\b',
    r'\bshe said\b',
    r'\bthey said\b',
    r'\bwe said\b',
    r'\bI asked\b',
    r'\bhe asked\b',
    r'\bshe asked\b',
    r'\bthey asked\b',
    r'\bI told\b',
    r'\bhe told\b',
    r'\bshe told\b',
    r'\bI replied\b',
    r'\bhe replied\b',
    r'\bshe replied\b',
    r'\bI answered\b',
    r'\bhe answered\b',
    r'\bshe answered\b',
    r'\bhe yelled\b',
    r'\bshe yelled\b',
    r'\bI yelled\b',
]

# Compile patterns for efficiency
DIALOG_REGEX = re.compile('|'.join(DIALOG_PATTERNS), re.IGNORECASE)


def sanitize_llm_json(response_text: str) -> str:
    """Sanitize common LLM JSON errors before parsing."""
    # Extract from markdown code blocks if present
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]
    
    return response_text.strip()


def check_ollama_connection():
    """Check if Ollama is running and accessible."""
    try:
        models = ollama.list()
        print("[OK] Connected to Ollama")
        model_list = models.get('models', []) if isinstance(models, dict) else models.models if hasattr(models, 'models') else []
        available = [m.get('name', m.model) if isinstance(m, dict) else m.model for m in model_list]
        if available:
            print(f"   Available models: {available[:5]}...")  # Show first 5
        return True
    except Exception as e:
        print(f"\n[ERROR] Cannot connect to Ollama: {e}")
        print("\nMake sure Ollama is running:")
        print("  1. Install Ollama from https://ollama.ai")
        print("  2. Run: ollama serve")
        return False


def get_available_model():
    """Find an available model from our preferred list."""
    try:
        models = ollama.list()
        model_list = models.get('models', []) if isinstance(models, dict) else models.models if hasattr(models, 'models') else []
        available = [m.get('name', m.model) if isinstance(m, dict) else m.model for m in model_list]
        
        for model in MODELS_TO_TRY:
            for avail in available:
                if avail == model or avail.startswith(model + "-") or avail.startswith(model.replace(":", "-")):
                    print(f"   Using model: {avail}")
                    return avail
        
        if available:
            print(f"   Falling back to: {available[0]}")
            return available[0]
        
        return None
    except Exception as e:
        print(f"   Error checking models: {e}")
        return None


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


def get_all_recordings() -> list[str]:
    """Get list of all recordings with transcripts (excluding skipped ones)."""
    recordings = []
    
    # Get memoir recordings
    if MEMOIRS_DIR.exists():
        for d in MEMOIRS_DIR.iterdir():
            if d.is_dir() and get_transcript_path(d) is not None:
                if d.name not in SKIP_RECORDINGS:
                    recordings.append(d.name)
    
    # Get top-level recordings
    for d in RECORDINGS_DIR.iterdir():
        if d.is_dir() and d.name != "memoirs" and get_transcript_path(d) is not None:
            if d.name not in SKIP_RECORDINGS:
                recordings.append(d.name)
    
    return sorted(recordings)


def segment_has_dialog(segment: dict) -> bool:
    """Check if a segment contains dialog indicators."""
    return bool(DIALOG_REGEX.search(segment.get('text', '')))


def segment_already_quoted(segment: dict) -> bool:
    """Check if a segment already has quotation marks (already processed)."""
    return '"' in segment.get('text', '')


def segment_is_dialog_continuation(segment: dict, prev_segment: dict | None) -> bool:
    """Check if this segment is a continuation of dialog from the previous segment.
    
    E.g., if prev_segment ends with "he said," and this segment has the spoken words.
    """
    if prev_segment is None:
        return False
    
    prev_text = prev_segment.get('text', '').strip()
    
    # Check if previous segment ends with a dialog marker followed by comma
    # e.g., "and he said," or "she asked,"
    ends_with_said = bool(re.search(r'\b(said|asked|told|replied|answered|yelled),?\s*$', prev_text, re.IGNORECASE))
    
    return ends_with_said


def find_dialog_segments(
    segments: list[dict],
    start_time: float | None = None,
    end_time: float | None = None
) -> list[int]:
    """
    Find indices of segments that contain dialog patterns or are dialog continuations.
    Skips segments that already have quotation marks.
    
    Args:
        segments: List of transcript segments
        start_time: Only process segments starting at or after this time (seconds)
        end_time: Only process segments starting before this time (seconds)
    
    Returns list of segment indices that need dialog processing.
    """
    dialog_indices = []
    
    for i, seg in enumerate(segments):
        seg_start = seg.get('start', 0)
        
        # Filter by time range if specified
        if start_time is not None and seg_start < start_time:
            continue
        if end_time is not None and seg_start >= end_time:
            continue
        
        # Skip segments that already have quotes
        if segment_already_quoted(seg):
            continue
        
        # Check if this segment has dialog indicators
        if segment_has_dialog(seg):
            dialog_indices.append(i)
        # Also check if this is a continuation (spoken words after "he said,")
        elif i > 0 and segment_is_dialog_continuation(seg, segments[i-1]):
            dialog_indices.append(i)
    
    return dialog_indices


def build_dialog_context(
    segments: list[dict],
    dialog_idx: int,
    context_before: int = 1,
    context_after: int = 2
) -> list[tuple[int, dict]]:
    """
    Build context around a dialog segment for LLM processing.
    
    Returns list of (index, segment) tuples for the dialog segment and its context.
    """
    start = max(0, dialog_idx - context_before)
    end = min(len(segments), dialog_idx + context_after + 1)
    
    return [(i, segments[i]) for i in range(start, end)]


def correct_dialog_with_llm(
    segments: list[dict],
    dialog_idx: int,
    model_name: str
) -> list[dict] | None:
    """
    Use LLM to correct dialog punctuation for a specific dialog segment and its context.
    
    Returns corrections or None if no changes needed.
    """
    # Get the dialog segment and surrounding context
    context = build_dialog_context(segments, dialog_idx, context_before=2, context_after=2)
    
    # Build the text for the LLM with segment indices
    segment_texts = []
    for idx, seg in context:
        marker = ">>>" if idx == dialog_idx else "   "
        segment_texts.append(f"{marker}[{idx}] {seg['text']}")
    
    combined_text = "\n".join(segment_texts)
    dialog_text = segments[dialog_idx]['text']
    
    # Check if this segment follows a "said," pattern
    prev_ends_with_said = False
    if dialog_idx > 0:
        prev_text = segments[dialog_idx - 1].get('text', '').strip()
        prev_ends_with_said = prev_text.endswith('said,') or prev_text.endswith('asked,') or prev_text.endswith('told,')
    
    if prev_ends_with_said:
        # This segment contains the spoken words
        prompt = f"""/no_think
The previous segment ended with "said," so this segment contains the SPOKEN WORDS.
Add quotation marks around the entire text.

CONTEXT:
{combined_text}

TARGET [{dialog_idx}]: {dialog_text}

The previous segment ended with a speaking verb, so segment {dialog_idx} is what was said.
Add quotes: "{dialog_text}" -> add " at start and end

JSON response with quotes added:
{{"index": {dialog_idx}, "original": "{dialog_text}", "corrected": "\\"{dialog_text}\\""}}"""
    else:
        prompt = f"""/no_think
Check if this segment needs quotation marks around spoken words.

CONTEXT:
{combined_text}

TARGET [{dialog_idx}]: {dialog_text}

ADD QUOTES when segment contains SPOKEN WORDS after "said":
- "He said, I'm leaving." -> He said, "I'm leaving."

DO NOT ADD QUOTES:
- "he said," alone (spoken words in next segment) -> {{}}
- "as I said" (reference, not new dialog) -> {{}}
- Indirect: "He said that..." -> {{}}

JSON:
- Quotes needed: {{"index": {dialog_idx}, "original": "text", "corrected": "text with quotes"}}
- No quotes: {{}}"""

    try:
        # Stream response to console for monitoring
        response_text = ""
        seg_time = segments[dialog_idx].get('start', 0)
        time_fmt = f"{int(seg_time//60)}:{int(seg_time%60):02d}"
        print(f"      [{dialog_idx}] @{time_fmt}: ", end="", flush=True)
        
        for chunk in ollama.generate(
            model=model_name,
            prompt=prompt,
            stream=True,
            options={
                "temperature": 0.1,  # Very low for consistent punctuation
                "num_ctx": 2048,
            },
            keep_alive="10m"
        ):
            text = chunk.get("response", "")
            if text:
                response_text += text
                sys.stdout.write(text)
                sys.stdout.flush()
        
        print()  # Newline after stream
        
        # Parse JSON
        response_text = sanitize_llm_json(response_text)
        result = json.loads(response_text)
        
        # Handle variant response format: {"Quotes needed": {...}} 
        if isinstance(result, dict):
            # Check for nested format
            for key in ['Quotes needed', 'quotes needed', 'correction', 'Correction']:
                if key in result and isinstance(result[key], dict):
                    result = result[key]
                    break
        
        # Check if it's an empty result or a valid correction
        if not result or 'index' not in result:
            return None
        
        return [result]  # Return as a list for compatibility
        
    except json.JSONDecodeError as e:
        print(f" [WARN] JSON parse error: {e}")
        return None
    except Exception as e:
        print(f" [ERROR] LLM error: {e}")
        return None


def extract_words(text: str) -> list[str]:
    """
    Extract just the words from text, stripping ALL punctuation.
    Used to verify that only punctuation was changed, not content.
    """
    # Remove all punctuation and special characters, keep only letters/numbers/spaces
    cleaned = re.sub(r'[^\w\s]', ' ', text.lower())
    # Split and filter empty strings
    return [w for w in cleaned.split() if w]


def words_match(original: str, corrected: str) -> tuple[bool, str]:
    """
    Verify that the corrected text has the exact same words as original.
    Only punctuation should differ.
    
    Returns (match: bool, reason: str)
    """
    orig_words = extract_words(original)
    corr_words = extract_words(corrected)
    
    if orig_words == corr_words:
        return True, ""
    
    # Find what changed
    if len(orig_words) != len(corr_words):
        return False, f"word count changed: {len(orig_words)} -> {len(corr_words)}"
    
    # Find mismatched words
    mismatches = []
    for i, (o, c) in enumerate(zip(orig_words, corr_words)):
        if o != c:
            mismatches.append(f"'{o}' -> '{c}'")
    
    if mismatches:
        return False, f"words changed: {', '.join(mismatches[:3])}"
    
    return True, ""


def capitalize_after_quote(text: str) -> str:
    """Capitalize the first letter after an opening quote mark."""
    # Find pattern: " followed by lowercase letter
    result = re.sub(r'"([a-z])', lambda m: '"' + m.group(1).upper(), text)
    return result


def apply_corrections_to_segments(
    segments: list[dict],
    corrections: list[dict],
    verbose: bool = True
) -> tuple[list[dict], list[dict]]:
    """
    Apply corrections to segments in place.
    Only applies corrections where words are unchanged (punctuation-only changes).
    
    Returns (modified_segments, change_log)
    """
    change_log = []
    rejected_count = 0
    
    for correction in corrections:
        idx = correction.get("index")
        original = correction.get("original", "")
        corrected = correction.get("corrected", "")
        
        if idx is None or idx >= len(segments):
            continue
        
        # Skip if corrected text is empty or same as original
        if not corrected or corrected.strip() == original.strip():
            continue
        
        # Get actual text from segment
        actual_text = segments[idx].get("text", "").strip()
        
        # Skip if segment already has quotes (already processed)
        if '"' in actual_text:
            continue
        
        # Skip if the corrected text doesn't actually add quotes
        if '"' not in corrected:
            continue
        
        # Capitalize the first letter after opening quotes
        corrected = capitalize_after_quote(corrected)
        
        # CRITICAL: Verify the correction only changes punctuation, not words
        # Compare actual segment text against the corrected version
        words_ok, reason = words_match(actual_text, corrected)
        
        if not words_ok:
            rejected_count += 1
            if verbose and rejected_count <= 3:
                print(f"      [REJECTED] Segment {idx}: {reason}")
            continue
        
        # Apply correction
        old_text = segments[idx]["text"]
        segments[idx]["text"] = corrected
        
        change_log.append({
            "index": idx,
            "start": segments[idx].get("start", 0),
            "original": old_text,
            "corrected": corrected
        })
    
    if rejected_count > 0 and verbose:
        if rejected_count > 3:
            print(f"      [REJECTED] ... and {rejected_count - 3} more")
        print(f"      Total rejected (content changed): {rejected_count}")
    
    return segments, change_log


def process_transcript(
    recording_name: str,
    model_name: str,
    dry_run: bool = False,
    verbose: bool = True,
    start_time: float | None = None,
    end_time: float | None = None
) -> dict:
    """Process a single transcript and correct dialog punctuation.
    
    Args:
        recording_name: Name of the recording to process
        model_name: Ollama model to use
        dry_run: If True, don't save changes
        verbose: If True, print detailed output
        start_time: Only process segments starting at or after this time (seconds)
        end_time: Only process segments starting before this time (seconds)
    """
    
    recording_dir = find_recording_dir(recording_name)
    if recording_dir is None:
        print(f"  ERROR: Recording '{recording_name}' not found")
        return {"error": "Recording not found"}
    
    input_path = get_transcript_path(recording_dir)
    if input_path is None:
        print(f"  ERROR: No transcript found for '{recording_name}'")
        return {"error": "No transcript found"}
    
    # Load transcript (supports both CSV and JSON)
    data = load_transcript(recording_dir)
    if data is None:
        print(f"  ERROR: Failed to load transcript for '{recording_name}'")
        return {"error": "Failed to load transcript"}
    
    segments = data.get('segments', [])
    if verbose:
        print(f"  Loaded {len(segments)} segments")
        if start_time is not None or end_time is not None:
            time_range = []
            if start_time is not None:
                time_range.append(f"from {int(start_time//60)}:{int(start_time%60):02d}")
            if end_time is not None:
                time_range.append(f"to {int(end_time//60)}:{int(end_time%60):02d}")
            print(f"  Time filter: {' '.join(time_range)}")
    
    # Find dialog segments (not windows)
    dialog_indices = find_dialog_segments(segments, start_time, end_time)
    
    if not dialog_indices:
        print(f"  No dialog patterns found in time range - skipping")
        return {
            "recording": recording_name,
            "segments_total": len(segments),
            "segments_modified": 0,
            "corrections": []
        }
    
    if verbose:
        print(f"  Found {len(dialog_indices)} segments with dialog indicators")
    
    # Process each dialog segment individually
    all_changes = []
    
    if verbose:
        print(f"\n  Processing {len(dialog_indices)} dialog segments...")
    
    for i, dialog_idx in enumerate(dialog_indices):
        corrections = correct_dialog_with_llm(segments, dialog_idx, model_name)
        
        if corrections:
            segments, changes = apply_corrections_to_segments(segments, corrections, verbose=verbose)
            all_changes.extend(changes)
    
    # Summary
    if verbose:
        print(f"\n  Segments modified: {len(all_changes)}")
    
    if all_changes and verbose:
        print("\n  Sample changes:")
        for change in all_changes[:10]:
            print(f"    [{change['index']}] @ {change['start']:.1f}s")
            print(f"        Before: {change['original']}")
            print(f"        After:  {change['corrected']}")
        if len(all_changes) > 10:
            print(f"    ... and {len(all_changes) - 10} more")
    
    result = {
        'recording': recording_name,
        'segments_total': len(segments),
        'segments_modified': len(all_changes),
        'corrections': all_changes
    }
    
    if not dry_run and all_changes:
        # Backup original (if not already backed up by 02_correct_transcript.py)
        backup_suffix = input_path.suffix
        backup_path = recording_dir / f"transcript_original{backup_suffix}"
        if not backup_path.exists():
            import shutil
            shutil.copy(input_path, backup_path)
            if verbose:
                print(f"\n  Backup saved: {backup_path.name}")
        
        # Save corrected transcript as CSV
        data['segments'] = segments
        # Note: CSV format doesn't store metadata like _dialog_corrections
        output_path = save_transcript(recording_dir, data, format='csv')
        
        if verbose:
            print(f"  Saved: {output_path.name}")
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description='Correct dialog punctuation in transcripts using Ollama'
    )
    parser.add_argument(
        'recording',
        nargs='?',
        help='Recording name to process (or --all for all)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Process all recordings'
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
    parser.add_argument(
        '--start',
        type=int,
        default=None,
        help='Start time in seconds - only process segments at or after this time'
    )
    parser.add_argument(
        '--end',
        type=int,
        default=None,
        help='End time in seconds - only process segments before this time'
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("DIALOG PUNCTUATION CORRECTION")
    print("=" * 60)
    print("\nThis script uses Ollama to add proper quotation marks")
    print("around spoken dialog (e.g., 'I said, \"Hello.\"')")
    print(f"\nSkipping: {', '.join(SKIP_RECORDINGS)}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'APPLY'}")
    
    if args.start is not None or args.end is not None:
        time_info = []
        if args.start is not None:
            time_info.append(f"start={args.start}s")
        if args.end is not None:
            time_info.append(f"end={args.end}s")
        print(f"Time range: {', '.join(time_info)}")
    
    recordings = get_all_recordings()
    
    if args.list:
        print("\nAvailable recordings:")
        for r in recordings:
            print(f"  - {r}")
        return
    
    # Check Ollama connection
    if not check_ollama_connection():
        sys.exit(1)
    
    # Get model
    model_name = get_available_model()
    if not model_name:
        print("\n[ERROR] No suitable model found!")
        print("   Pull a model with: ollama pull gemma3:12b")
        sys.exit(1)
    
    print(f"\n[MODEL] Using: {model_name}")
    
    if args.all:
        to_process = recordings
    elif args.recording:
        if args.recording in SKIP_RECORDINGS:
            print(f"\nERROR: Recording '{args.recording}' is in skip list")
            return
        if args.recording not in recordings:
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
        result = process_transcript(
            rec,
            model_name,
            dry_run=args.dry_run,
            start_time=float(args.start) if args.start is not None else None,
            end_time=float(args.end) if args.end is not None else None
        )
        results.append(result)
    
    # Final summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    total_modified = sum(r.get('segments_modified', 0) for r in results)
    
    print(f"\nRecordings processed: {len(results)}")
    print(f"Total segments modified: {total_modified}")
    
    if args.dry_run:
        print("\n[DRY RUN - no changes saved]")
    
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
