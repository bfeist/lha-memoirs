#!/usr/bin/env python3
"""
Build a timeline of Lindy Achen's life from memoir transcripts.

This script:
1. Extracts all year references from memoir transcripts and interviews
2. Groups related excerpts by year or year range
3. Uses Gemma3:12b via Ollama to generate descriptions for each time period
4. Outputs timeline.json to /public

Usage:
    python 07_build_timeline.py
    python 07_build_timeline.py --dry-run  # Preview without LLM generation
    python 07_build_timeline.py --regenerate  # Regenerate even if timeline.json exists

Requires: pip install ollama tqdm
Or with uv: uv pip install ollama tqdm
"""

import argparse
import json
import re
import sys
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Optional

# Check for required packages
try:
    import ollama
    from tqdm import tqdm
except ImportError as e:
    print(f"\nMissing required package: {e}")
    print("\nInstall with:")
    print("  uv pip install ollama tqdm")
    sys.exit(1)

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
PUBLIC_DIR = PROJECT_ROOT / "public"
RECORDINGS_BASE_DIR = PUBLIC_DIR / "recordings"
OUTPUT_FILE = PUBLIC_DIR / "timeline.json"

# Add scripts directory to path for imports
sys.path.insert(0, str(SCRIPT_DIR))
from transcript_utils import load_transcript, get_transcript_path

# Recording configs - maps recording info including folder path
RECORDINGS = {
    "memoirs_main": {
        "id": "memoirs_main",
        "title": "Memoirs",
        "folder": "memoirs/Norm_red",
        "audioPath": "/static_assets/audio/memoirs/Norm_red/audio_original.mp3",
    },
    "memoirs_second_telling": {
        "id": "memoirs_second_telling", 
        "title": "Memoirs - Second Telling",
        "folder": "memoirs/TDK_D60_edited_through_air",
        "audioPath": "/static_assets/audio/memoirs/TDK_D60_edited_through_air/audio_original.mp3",
    },
    "glynn_interview": {
        "id": "glynn_interview",
        "title": "Glynn Interview",
        "folder": "glynn_interview",
        "audioPath": "/static_assets/audio/glynn_interview/audio_original.mp3",
    },
    "sister_hilary": {
        "id": "lha_sr_hilary",
        "title": "Sister Hilary Recording",
        "folder": "LHA_Sr.Hilary",
        "audioPath": "/static_assets/audio/LHA_Sr.Hilary/audio_original.mp3",
    },
}

# Model configuration
PREFERRED_MODEL = "gemma3:12b"
MODELS_TO_TRY = ["gemma3:12b", "qwen3:14b", "gemma3:27b"]

# Timeline range - Lindy was born 1902, memoirs go to roughly 1965
TIMELINE_START = 1902
TIMELINE_END = 1966

# Year patterns to match in transcripts
# Matches: 1902, '07, '47, 1945, etc.
YEAR_PATTERN = re.compile(
    r"""
    (?:
        (?:19[0-6][0-9])  # Full year 1900-1969
        |
        (?<![0-9])        # Not preceded by digit
        '[0-6][0-9]       # Abbreviated year '00-'69
        (?![0-9])         # Not followed by digit
    )
    """,
    re.VERBOSE
)


@dataclass
class Excerpt:
    """A transcript excerpt mentioning a specific year."""
    recording_id: str
    recording_title: str
    audio_url: str
    text: str
    start_time: float
    end_time: float
    year_mentioned: int


@dataclass
class TimelineEntry:
    """A single entry in the timeline."""
    year_start: int
    year_end: int
    title: str
    description: str
    age_start: int
    age_end: int
    excerpts: list  # List of Excerpt dicts


def normalize_year(year_str: str) -> Optional[int]:
    """Convert year string to full year integer.
    
    Examples:
        "1947" -> 1947
        "'47" -> 1947
        "'07" -> 1907
    """
    year_str = year_str.strip()
    
    if year_str.startswith("'"):
        # Abbreviated year
        short_year = int(year_str[1:])
        # For Lindy's memoirs (1902-1966):
        # '00-'66 -> 1900-1966
        # But realistically, '00-'06 would be rare (before he was conscious)
        if short_year <= 66:
            return 1900 + short_year
        else:
            return None  # Outside our range
    else:
        year = int(year_str)
        if 1900 <= year <= 1969:
            return year
        return None


def extract_year_mentions(segments: list, recording_info: dict) -> list[Excerpt]:
    """Extract all year mentions from transcript segments."""
    excerpts = []
    
    for seg in segments:
        text = seg.get("text", "")
        start = seg.get("start", 0)
        end = seg.get("end", start)
        
        # Find all year mentions in this segment
        matches = YEAR_PATTERN.findall(text)
        
        for match in matches:
            year = normalize_year(match)
            if year and TIMELINE_START <= year <= TIMELINE_END:
                excerpts.append(Excerpt(
                    recording_id=recording_info["id"],
                    recording_title=recording_info["title"],
                    audio_url=recording_info["audioPath"],
                    text=text.strip(),
                    start_time=start,
                    end_time=end,
                    year_mentioned=year,
                ))
    
    return excerpts


def group_excerpts_by_period(excerpts: list[Excerpt]) -> dict[tuple[int, int], list[Excerpt]]:
    """Group excerpts into year periods.
    
    Combines sparse years into ranges where there's little content.
    Returns dict mapping (start_year, end_year) -> excerpts
    """
    # First, count excerpts per year
    year_counts = defaultdict(list)
    for exc in excerpts:
        year_counts[exc.year_mentioned].append(exc)
    
    # Define periods - some fixed historical periods, others dynamic
    # Key life periods for Lindy:
    periods = []
    
    # Check what years have content
    years_with_content = sorted(year_counts.keys())
    
    if not years_with_content:
        return {}
    
    # Build periods dynamically based on content density
    current_start = years_with_content[0]
    current_excerpts = []
    
    # Minimum excerpts to warrant its own year entry
    MIN_EXCERPTS_FOR_SOLO_YEAR = 7
    # Maximum gap before starting a new period
    MAX_GAP = 2
    # Maximum excerpts to accumulate before forcing a break
    MAX_EXCERPTS_PER_PERIOD = 15
    
    i = 0
    while i < len(years_with_content):
        year = years_with_content[i]
        year_excerpts = year_counts[year]
        
        # Check if this year has enough content for its own entry
        if len(year_excerpts) >= MIN_EXCERPTS_FOR_SOLO_YEAR:
            # Flush any accumulated range
            if current_excerpts:
                periods.append((current_start, years_with_content[i-1] if i > 0 else current_start, current_excerpts))
                current_excerpts = []
            
            # This year gets its own entry
            periods.append((year, year, year_excerpts))
            current_start = year + 1
        else:
            # Accumulate into a range
            if not current_excerpts:
                current_start = year
            current_excerpts.extend(year_excerpts)
            
            # Check if next year is too far away
            if i < len(years_with_content) - 1:
                next_year = years_with_content[i + 1]
                if next_year - year > MAX_GAP or len(current_excerpts) >= MAX_EXCERPTS_PER_PERIOD:
                    # End this period
                    periods.append((current_start, year, current_excerpts))
                    current_excerpts = []
                    current_start = next_year
        
        i += 1
    
    # Flush remaining
    if current_excerpts:
        periods.append((current_start, years_with_content[-1], current_excerpts))
    
    # Convert to dict
    return {(start, end): excs for start, end, excs in periods}


def check_ollama_connection():
    """Check if Ollama is running and accessible."""
    try:
        models = ollama.list()
        print("[OK] Connected to Ollama")
        model_list = models.get('models', []) if isinstance(models, dict) else models.models if hasattr(models, 'models') else []
        available = [m.get('name', m.model) if isinstance(m, dict) else m.model for m in model_list]
        if available:
            print(f"   Available models: {available}")
        return True
    except Exception as e:
        print(f"\n[X] Cannot connect to Ollama: {e}")
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


def generate_period_description(
    period_start: int,
    period_end: int,
    excerpts: list[Excerpt],
    model_name: str
) -> tuple[str, str]:
    """Generate a title and description for a time period using the LLM.
    
    Returns (title, description) tuple.
    """
    # Build context from excerpts
    excerpts_text = "\n".join([
        f"- \"{exc.text}\" (from {exc.recording_title})"
        for exc in excerpts[:15]  # Limit to avoid context overflow
    ])
    
    age_start = period_start - 1902
    age_end = period_end - 1902 if period_end != period_start else age_start
    
    year_label = str(period_start) if period_start == period_end else f"{period_start}-{period_end}"
    age_label = str(age_start) if age_start == age_end else f"{age_start}-{age_end}"
    
    prompt = f"""/no_think
You are helping create a timeline for the memoirs of Linden "Lindy" Achen (1902-1994).

These are excerpts from his voice memoirs that mention the year(s) {year_label}:

{excerpts_text}

Lindy was born in 1902, so during this period he was {age_label} years old.

Based on these excerpts, provide:
1. A short, evocative title (3-6 words) for this period of his life
2. A brief description (2-3 sentences) summarizing what was happening in his life during this time

IMPORTANT CONTEXT:
- Lindy was born in Remsen, Iowa in 1902
- His family moved to Saskatchewan, Canada in 1907
- He grew up farming on the Canadian prairies
- He left the farm in 1926/1927 after disputes with brothers
- He became an electrician and eventually started Achen Construction
- He built rural power lines across Saskatchewan from 1945-1965

Respond with ONLY valid JSON:
{{"title": "Short evocative title", "description": "2-3 sentence description of this period"}}"""

    try:
        response_text = ""
        for chunk in ollama.generate(
            model=model_name,
            prompt=prompt,
            stream=True,
            options={"temperature": 0.3, "num_ctx": 4096},
            keep_alive="10m"
        ):
            text = chunk.get("response", "")
            if text:
                response_text += text
        
        # Parse JSON
        # Extract from markdown if present
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]
        
        result = json.loads(response_text.strip())
        return result.get("title", f"Year {year_label}"), result.get("description", "")
        
    except Exception as e:
        print(f"   [!] Error generating description: {e}")
        return f"Year {year_label}", ""


def build_timeline(dry_run: bool = False) -> list[TimelineEntry]:
    """Build the complete timeline from transcript analysis."""
    print("=" * 60)
    print("TIMELINE BUILDER")
    print("=" * 60)
    
    all_excerpts = []
    
    # Load and analyze each recording
    for recording_key, recording_info in RECORDINGS.items():
        recording_path = RECORDINGS_BASE_DIR / recording_info["folder"]
        print(f"\n[Folder] Processing {recording_info['title']}...")
        
        transcript_path = get_transcript_path(recording_path)
        if not transcript_path:
            print(f"   [!] No transcript found in {recording_path}")
            continue
        
        transcript_data = load_transcript(recording_path)
        if not transcript_data or not transcript_data.get("segments"):
            print(f"   [!] Empty transcript: {transcript_path}")
            continue
        
        segments = transcript_data["segments"]
        print(f"   Loaded {len(segments)} segments")
        
        excerpts = extract_year_mentions(segments, recording_info)
        print(f"   Found {len(excerpts)} year mentions")
        
        all_excerpts.extend(excerpts)
    
    print(f"\n[Stats] Total year mentions across all recordings: {len(all_excerpts)}")
    
    # Group into periods
    periods = group_excerpts_by_period(all_excerpts)
    print(f"   Grouped into {len(periods)} time periods")
    
    # Show period summary
    print("\n[Periods] Time periods:")
    for (start, end), excs in sorted(periods.items()):
        year_label = str(start) if start == end else f"{start}-{end}"
        print(f"   {year_label}: {len(excs)} excerpts")
    
    if dry_run:
        print("\n[DryRun] Dry run mode - skipping LLM generation")
        return []
    
    # Check Ollama
    if not check_ollama_connection():
        return []
    
    model_name = get_available_model()
    if not model_name:
        print("[X] No suitable model available")
        return []
    
    # Generate descriptions for each period
    print(f"\n[LLM] Generating descriptions with {model_name}...")
    timeline_entries = []
    
    for (period_start, period_end), excerpts in tqdm(sorted(periods.items()), desc="Generating"):
        title, description = generate_period_description(
            period_start, period_end, excerpts, model_name
        )
        
        # Convert excerpts to dicts, limiting to best examples
        # First deduplicate by (recording_id, start_time) to avoid same segment appearing multiple times
        seen_keys = set()
        unique_excerpts = []
        for exc in excerpts:
            key = (exc.recording_id, exc.start_time)
            if key not in seen_keys:
                seen_keys.add(key)
                unique_excerpts.append(exc)
        
        # Sort by text length (prefer more substantive quotes)
        sorted_excerpts = sorted(unique_excerpts, key=lambda e: len(e.text), reverse=True)
        excerpt_dicts = [
            {
                "recordingId": exc.recording_id,
                "recordingTitle": exc.recording_title,
                "audioUrl": exc.audio_url,
                "text": exc.text,
                "startTime": exc.start_time,
                "endTime": exc.end_time,
            }
            for exc in sorted_excerpts[:5]  # Keep top 5 excerpts per period
        ]
        
        entry = TimelineEntry(
            year_start=period_start,
            year_end=period_end,
            title=title,
            description=description,
            age_start=period_start - 1902,
            age_end=period_end - 1902,
            excerpts=excerpt_dicts,
        )
        timeline_entries.append(entry)
    
    return timeline_entries


def save_timeline(entries: list[TimelineEntry]):
    """Save timeline to JSON file."""
    output = {
        "generatedAt": __import__("datetime").datetime.now().isoformat(),
        "timelineStart": TIMELINE_START,
        "timelineEnd": TIMELINE_END,
        "entries": [asdict(e) for e in entries],
    }
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n[OK] Timeline saved to {OUTPUT_FILE}")
    print(f"   {len(entries)} time periods generated")


def main():
    parser = argparse.ArgumentParser(description="Build timeline from memoir transcripts")
    parser.add_argument("--dry-run", action="store_true", help="Preview without LLM generation")
    parser.add_argument("--regenerate", action="store_true", help="Regenerate even if file exists")
    args = parser.parse_args()
    
    # Check if output already exists
    if OUTPUT_FILE.exists() and not args.regenerate and not args.dry_run:
        print(f"[!] {OUTPUT_FILE} already exists. Use --regenerate to overwrite.")
        return
    
    entries = build_timeline(dry_run=args.dry_run)
    
    if entries:
        save_timeline(entries)
    elif args.dry_run:
        print("\n📝 Dry run complete. Run without --dry-run to generate timeline.")


if __name__ == "__main__":
    main()
