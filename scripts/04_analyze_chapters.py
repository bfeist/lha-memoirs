"""
Analyze transcript content and generate chapter structure using Ollama.
Run with: uv run 03_analyze_chapters.py [recording_path]

Processes all recording folders in public/recordings/ (including nested folders),
or a specific one if path is provided (e.g., "memoirs/HF_60").

Skips recordings that already have a chapters.json file.

Requires: pip install ollama tqdm
Or with uv: uv pip install ollama tqdm

Make sure Ollama is running locally with one of these models:
  - ollama run gemma3:12b
  - ollama run qwen2.5:20b (or similar)
"""

import json
import sys
import time
from pathlib import Path

print("=" * 60)
print("CHAPTER ANALYSIS SCRIPT")
print("=" * 60)

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
OUTPUT_BASE_DIR = PROJECT_ROOT / "public" / "recordings"

# Model to use (try these in order - optimized for RTX 4090 24GB with ~17GB available)
PREFERRED_MODEL = "gemma3:12b"
MODELS_TO_TRY = ["gemma3:12b", "qwen3:14b", "gpt-oss:20b", "devstral:24b", "gemma3:27b"]


def find_all_recordings(base_dir: Path) -> list[Path]:
    """Recursively find all folders containing transcript.json."""
    recordings = []
    
    def scan_folder(folder: Path):
        if (folder / "transcript.json").exists():
            recordings.append(folder)
        for item in sorted(folder.iterdir()):
            if item.is_dir():
                scan_folder(item)
    
    if base_dir.exists():
        scan_folder(base_dir)
    return recordings


def get_recording_folders(specific_recording: str | None = None) -> list[Path]:
    """Get all recording folders from public/recordings, or a specific one."""
    if specific_recording:
        folder = OUTPUT_BASE_DIR / specific_recording
        if folder.exists() and folder.is_dir():
            if (folder / "transcript.json").exists():
                return [folder]
            else:
                # Maybe it's a parent folder with nested recordings
                return find_all_recordings(folder)
        else:
            print(f"❌ Recording folder not found: {folder}")
            return []
    
    return find_all_recordings(OUTPUT_BASE_DIR)


def get_relative_recording_path(recording_folder: Path) -> str:
    """Get the path of a recording relative to public/recordings."""
    return str(recording_folder.relative_to(OUTPUT_BASE_DIR)).replace("\\", "/")


def check_ollama_connection():
    """Check if Ollama is running and accessible."""
    try:
        models = ollama.list()
        print("✅ Connected to Ollama")
        # Handle both old and new API response formats
        model_list = models.get('models', []) if isinstance(models, dict) else models.models if hasattr(models, 'models') else []
        available = [m.get('name', m.model) if isinstance(m, dict) else m.model for m in model_list]
        if available:
            print(f"   Available models: {available}")
        else:
            print("   No models currently loaded")
        return True
    except Exception as e:
        print(f"\n❌ Cannot connect to Ollama: {e}")
        print("\nMake sure Ollama is running:")
        print("  1. Install Ollama from https://ollama.ai")
        print("  2. Run: ollama serve")
        return False


def pull_model(model_name: str) -> bool:
    """Pull a model from Ollama registry."""
    print(f"\n🔄 Pulling model {model_name}...")
    print("   This may take a few minutes on first download...")
    try:
        # Stream the pull progress
        for progress in ollama.pull(model_name, stream=True):
            if hasattr(progress, 'status'):
                status = progress.status
                if hasattr(progress, 'completed') and hasattr(progress, 'total') and progress.total:
                    pct = int(progress.completed / progress.total * 100)
                    print(f"   {status}: {pct}%", end="\r")
                else:
                    print(f"   {status}", end="\r")
        print(f"\n   ✅ Model {model_name} pulled successfully!")
        return True
    except Exception as e:
        print(f"\n   ❌ Failed to pull model: {e}")
        return False


def get_available_model():
    """Find an available model from our preferred list, or pull one if needed."""
    try:
        models = ollama.list()
        # Handle both old and new API response formats
        model_list = models.get('models', []) if isinstance(models, dict) else models.models if hasattr(models, 'models') else []
        available = [m.get('name', m.model) if isinstance(m, dict) else m.model for m in model_list]
        
        for model in MODELS_TO_TRY:
            # Check for exact match first (e.g., "qwen3:14b" matches "qwen3:14b" or "qwen3:14b-...")
            for avail in available:
                # Exact match or starts with model name (handles tags like "qwen3:14b-q4_0")
                if avail == model or avail.startswith(model + "-") or avail.startswith(model.replace(":", "-")):
                    print(f"   Using model: {avail}")
                    return avail
        
        # No exact match - try pulling the preferred model
        print(f"\n⚠️  No preferred model found. Will pull {PREFERRED_MODEL}...")
        if pull_model(PREFERRED_MODEL):
            return PREFERRED_MODEL
        
        # If pull failed and we have any model available, use it
        if available:
            print(f"   Falling back to: {available[0]}")
            return available[0]
        
        return None
    except Exception as e:
        print(f"   Error checking models: {e}")
        return None


def unload_model(model_name: str):
    """Unload the model from memory after use."""
    print(f"\n🔄 Unloading model {model_name}...")
    try:
        # Send a request with keep_alive=0 to unload
        ollama.generate(model=model_name, prompt="", keep_alive=0)
        print("   ✅ Model unloaded from memory")
    except Exception as e:
        print(f"   ⚠️ Could not unload model: {e}")


# Minimum chapter duration in seconds - chapters shorter than this will be merged
MIN_CHAPTER_DURATION = 90  # 1.5 minutes minimum


def analyze_content_for_chapters(segments: list, model_name: str, total_duration: float = None) -> dict:
    """Use LLM to analyze transcript and identify logical chapters."""
    
    print(f"\n🤖 Analyzing content with {model_name}...")
    print("   Processing transcript in chunks for better accuracy...")
    
    # Get total duration
    if total_duration is None:
        total_duration = segments[-1]["end"] if segments else 0
    
    # Process in 10-minute windows with 60-second overlap for better context
    WINDOW_SIZE = 600  # 10 minutes
    OVERLAP = 60  # 60 seconds
    
    all_chapters = []
    window_start = 0
    chunk_num = 0
    
    while window_start < total_duration:
        chunk_num += 1
        window_end = min(window_start + WINDOW_SIZE, total_duration)
        
        # Get segments in this window
        window_segments = [
            seg for seg in segments
            if seg["start"] >= window_start and seg["start"] < window_end
        ]
        
        if not window_segments:
            window_start += WINDOW_SIZE - OVERLAP
            continue
        
        # Format for prompt - include seconds directly so LLM doesn't have to calculate
        transcript_lines = []
        for seg in window_segments:
            minutes = int(seg["start"] // 60)
            seconds = int(seg["start"] % 60)
            total_secs = seg["start"]
            transcript_lines.append(f"[{total_secs:.0f}s] {seg['text']}")
        
        chunk_text = "\n".join(transcript_lines)
        
        # Create focused prompt for this chunk
        prompt = f"""/no_think
Analyze this transcript segment and identify 1-2 MAJOR topic changes.

IMPORTANT: Only create a new chapter when there's a SIGNIFICANT topic shift.
- A chapter should cover at least 1-2 minutes of content
- Minor digressions within the same general topic should NOT start a new chapter
- If no major topic change occurs in this segment, return an empty chapters array

Transcript (timestamps are in SECONDS from start of recording):

{chunk_text}

For each MAJOR topic, provide:
- title: 2-4 word descriptive title for the main subject
- startTime: Copy the [XXXs] number where this topic BEGINS (just the number, e.g., 103)
- description: Brief phrase describing what's discussed (no "the speaker" or "he discusses")

Respond with ONLY valid JSON:
{{"chapters": [{{"id": 1, "title": "Topic Title", "startTime": 103, "description": "Brief description"}}]}}"""

        print(f"\n   Chunk {chunk_num} ({int(window_start/60)}:{int(window_start%60):02d}-{int(window_end/60)}:{int(window_end%60):02d}):")
        sys.stdout.flush()
        
        # Stream response
        response_text = ""
        
        try:
            for chunk in ollama.generate(
                model=model_name,
                prompt=prompt,
                stream=True,
                options={
                    "temperature": 0.3,
                    "num_ctx": 4096,
                }
            ):
                text = chunk.get("response", "")
                if text:
                    response_text += text
                    sys.stdout.write(text)
                    sys.stdout.flush()
            
            print()  # Newline after stream
            
            # Parse JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            chunk_result = json.loads(response_text.strip())
            
            # Add chapters from this chunk
            for chapter in chunk_result.get("chapters", []):
                all_chapters.append(chapter)
            
        except json.JSONDecodeError as e:
            print(f"   ⚠️  Could not parse JSON: {e}")
            print(f"   Response: {response_text[:200]}...")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Move to next window
        window_start += WINDOW_SIZE - OVERLAP
    
    # Merge nearby chapters with similar topics
    merged_chapters = merge_similar_chapters(all_chapters)
    
    # Generate overall summary
    print("\n   Generating overall summary...")
    summary = generate_summary(segments, model_name, merged_chapters)
    
    return {
        "chapters": merged_chapters,
        "summary": summary
    }


def merge_similar_chapters(chapters: list) -> list:
    """Merge chapters that are close together or too short."""
    if not chapters:
        return []
    
    # Sort by start time
    chapters = sorted(chapters, key=lambda c: c["startTime"])
    
    merged = [chapters[0]]
    
    for chapter in chapters[1:]:
        last = merged[-1]
        time_diff = chapter["startTime"] - last["startTime"]
        
        # Merge if:
        # 1. Very close together (within 30 seconds) - likely same topic / micro-chapters
        # 2. Within 90 seconds AND have similar titles
        # 3. Previous chapter would be too short (less than MIN_CHAPTER_DURATION)
        should_merge = (
            time_diff < 30 or 
            (time_diff < MIN_CHAPTER_DURATION and chapters_similar(last["title"], chapter["title"])) or
            time_diff < MIN_CHAPTER_DURATION  # Enforce minimum duration
        )
        
        if should_merge:
            # Keep the earlier start time, combine descriptions
            if chapter.get('description') and chapter['description'] not in last.get('description', ''):
                last["description"] = f"{last.get('description', '')}; {chapter['description']}".strip('; ')
            # Use longer/better title if current one is very short
            if len(chapter.get('title', '')) > len(last.get('title', '')):
                last['title'] = chapter['title']
        else:
            merged.append(chapter)
    
    # Second pass: ensure no chapter is shorter than minimum duration
    # by checking duration to next chapter
    final_merged = []
    for i, chapter in enumerate(merged):
        if i == 0:
            final_merged.append(chapter)
            continue
        
        # Calculate duration of previous chapter
        prev = final_merged[-1]
        prev_duration = chapter["startTime"] - prev["startTime"]
        
        if prev_duration < MIN_CHAPTER_DURATION:
            # Previous chapter too short, merge current into it
            if chapter.get('description') and chapter['description'] not in prev.get('description', ''):
                prev["description"] = f"{prev.get('description', '')}; {chapter['description']}".strip('; ')
            print(f"   ⚡ Merged short chapter: '{chapter['title']}' into '{prev['title']}' (was {prev_duration:.0f}s)")
        else:
            final_merged.append(chapter)
    
    return final_merged


def chapters_similar(title1: str, title2: str) -> bool:
    """Check if two chapter titles are similar."""
    words1 = set(title1.lower().split())
    words2 = set(title2.lower().split())
    
    # If they share 50% of words, consider them similar
    if not words1 or not words2:
        return False
    
    overlap = len(words1 & words2)
    min_words = min(len(words1), len(words2))
    
    return overlap / min_words >= 0.5


def validate_chapter_timing(chapters: list, segments: list, model_name: str) -> list:
    """
    Second pass: validate and correct chapter start times by finding where
    each topic actually begins in the transcript.
    """
    print("\n🔍 SECOND PASS: Validating chapter timing...")
    
    # Build a searchable transcript with timestamps
    transcript_lines = []
    for seg in segments:
        transcript_lines.append({
            "start": seg["start"],
            "text": seg["text"].strip().lower()
        })
    
    corrected_chapters = []
    
    for i, chapter in enumerate(chapters):
        # Define search window: from previous chapter (or 0) to current start + 2 minutes
        search_start = corrected_chapters[-1]["startTime"] if corrected_chapters else 0
        search_end = chapter["startTime"] + 120  # Look up to 2 min after claimed start
        
        # Get segments in search window
        window_segments = [
            seg for seg in segments
            if seg["start"] >= search_start and seg["start"] <= search_end
        ]
        
        if not window_segments:
            corrected_chapters.append(chapter)
            continue
        
        # Format window for LLM - use seconds directly
        window_text = "\n".join([
            f"[{seg['start']:.0f}s] {seg['text']}"
            for seg in window_segments
        ])
        
        prompt = f"""/no_think
Find where this topic FIRST begins.

Topic: "{chapter['title']}" - {chapter.get('description', '')}
Current time: {chapter['startTime']:.0f}s

Transcript (numbers are seconds):
{window_text}

Return the [XXXs] number where this topic FIRST starts.
Respond with ONLY: {{"correctedStartTime": <number>, "reason": "brief"}}"""

        try:
            # Stream the response so user can watch progress
            response_text = ""
            sys.stdout.write(f"      ")
            for chunk in ollama.generate(
                model=model_name,
                prompt=prompt,
                stream=True,
                options={"temperature": 0.1, "num_ctx": 4096}
            ):
                text = chunk.get("response", "")
                if text:
                    response_text += text
                    sys.stdout.write(text)
                    sys.stdout.flush()
            print()  # Newline after stream
            
            # Parse JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            result = json.loads(response_text.strip())
            corrected_time = float(result.get("correctedStartTime", chapter["startTime"]))
            reason = result.get("reason", "")
            
            # Sanity check: corrected time should be >= search_start and <= original + 60s
            if corrected_time >= search_start and corrected_time <= chapter["startTime"] + 60:
                if abs(corrected_time - chapter["startTime"]) > 5:  # Only log if significant change
                    old_fmt = f"{int(chapter['startTime']//60):02d}:{int(chapter['startTime']%60):02d}"
                    new_fmt = f"{int(corrected_time//60):02d}:{int(corrected_time%60):02d}"
                    print(f"   ⏱️  '{chapter['title']}': {old_fmt} → {new_fmt} ({reason})")
                chapter["startTime"] = corrected_time
            
        except Exception as e:
            print(f"   ⚠️  Could not validate '{chapter['title']}': {e}")
        
        corrected_chapters.append(chapter)
    
    # Re-sort by start time in case corrections changed order
    corrected_chapters = sorted(corrected_chapters, key=lambda c: c["startTime"])
    
    # First chapter always starts at 0
    if corrected_chapters:
        corrected_chapters[0]["startTime"] = 0.0
    
    # Run merge logic again after timing corrections may have created new overlaps
    print("   🔄 Merging chapters with same timestamps or too short duration...")
    corrected_chapters = merge_similar_chapters(corrected_chapters)
    
    print("   ✅ Timing validation complete")
    return corrected_chapters


def generate_summary(segments: list, model_name: str, chapters: list) -> str:
    """Generate a brief overall summary."""
    chapter_list = "\n".join([
        f"- {ch['title']}: {ch['description']}"
        for ch in chapters
    ])
    
    prompt = f"""/no_think
Write a 2-3 sentence summary of this 1986 Christmas memoir based on these topics:

{chapter_list}

Be direct and factual."""

    try:
        response_text = ""
        for chunk in ollama.generate(
            model=model_name,
            prompt=prompt,
            stream=False,
            options={"temperature": 0.3, "num_ctx": 2048}
        ):
            response_text = chunk.get("response", "")
        
        return response_text.strip()
    except Exception:
        return "A personal memoir recording covering family memories and life stories."


def finalize_chapters(chapters: list) -> list:
    """Finalize chapters for the output format."""
    finalized = []
    for chapter in chapters:
        finalized.append({
            "title": chapter["title"],
            "startTime": chapter["startTime"],
            "description": chapter.get("description", ""),
        })
    
    return finalized


def process_recording(recording_folder: Path, model_name: str) -> bool:
    """Process a single recording folder."""
    relative_path = get_relative_recording_path(recording_folder)
    transcript_file = recording_folder / "transcript.json"
    chapters_file = recording_folder / "chapters.json"
    
    # Skip if already processed
    if chapters_file.exists():
        print(f"\n⏭️  Skipping {relative_path} (chapters.json exists)")
        return True
    
    print(f"\n{'='*60}")
    print(f"📂 Processing recording: {relative_path}")
    print(f"{'='*60}")
    
    if not transcript_file.exists():
        print(f"   ❌ Transcript file not found: {transcript_file}")
        print("   Run 01_transcribe.py first")
        return False
    
    print(f"\n📂 Loading transcript from: {transcript_file}")
    with open(transcript_file, "r", encoding="utf-8") as f:
        transcript_data = json.load(f)
    
    segments = transcript_data.get("segments", [])
    files_info = transcript_data.get("files", None)
    total_duration = transcript_data.get("totalDuration", transcript_data.get("duration", 0))
    
    print(f"   Found {len(segments)} segments")
    if files_info:
        print(f"   Source files: {len(files_info)}")
        for idx, fi in enumerate(files_info):
            print(f"      - Part {idx + 1}: {fi['duration']:.1f}s")
    
    # Analyze content
    result = analyze_content_for_chapters(segments, model_name, total_duration)
    
    if not result or "chapters" not in result:
        print("\n❌ Chapter analysis failed!")
        return False
    
    chapters = result["chapters"]
    print(f"\n📚 Identified {len(chapters)} chapters (first pass):")
    for ch in chapters:
        minutes = int(ch["startTime"] // 60)
        seconds = int(ch["startTime"] % 60)
        print(f"   [{minutes:02d}:{seconds:02d}] {ch['title']}")
    
    # Second pass: validate and correct chapter timing
    chapters = validate_chapter_timing(chapters, segments, model_name)
    
    print(f"\n📚 Final {len(chapters)} chapters (after timing correction):")
    for ch in chapters:
        minutes = int(ch["startTime"] // 60)
        seconds = int(ch["startTime"] % 60)
        print(f"   [{minutes:02d}:{seconds:02d}] {ch['title']}")
    
    # Finalize chapters
    finalized_chapters = finalize_chapters(chapters)
    
    # Save chapters data (files info is in transcript.json, not duplicated here)
    chapters_path = recording_folder / "chapters.json"
    chapters_output = {
        "chapters": finalized_chapters,
        "summary": result.get("summary", ""),
    }
    
    with open(chapters_path, "w", encoding="utf-8") as f:
        json.dump(chapters_output, f, indent=2, ensure_ascii=False)
    print(f"\n   ✅ Saved chapters: {chapters_path}")
    
    # Remove legacy files if they exist
    legacy_files = ["regions.json", "toc.json"]
    for legacy_file in legacy_files:
        legacy_path = recording_folder / legacy_file
        if legacy_path.exists():
            legacy_path.unlink()
            print(f"   🗑️  Removed legacy file: {legacy_file}")
    
    return True


def main():
    # Parse command line args for specific recording
    specific_recording = None
    if len(sys.argv) > 1:
        specific_recording = sys.argv[1]
        print(f"\n🎯 Processing specific recording: {specific_recording}")
    
    # Check Ollama connection
    if not check_ollama_connection():
        sys.exit(1)
    
    # Find available model
    model_name = get_available_model()
    if not model_name:
        print("\n❌ No suitable model found!")
        print("   Pull a model with: ollama pull gemma3:12b")
        sys.exit(1)
    
    print(f"\n📦 Using model: {model_name}")
    
    # Get recording folders to process
    recording_folders = get_recording_folders(specific_recording)
    if not recording_folders:
        print(f"\n❌ No recording folders with transcript.json found in {OUTPUT_BASE_DIR}")
        print("   Run 01_transcribe.py first to create transcripts.")
        sys.exit(1)
    
    print(f"\n📂 Found {len(recording_folders)} recording(s) to process:")
    for folder in recording_folders:
        rel_path = get_relative_recording_path(folder)
        print(f"   - {rel_path}")
    
    # Process each recording folder
    success_count = 0
    for recording_folder in recording_folders:
        if process_recording(recording_folder, model_name):
            success_count += 1
    
    # Unload model to free memory
    unload_model(model_name)
    
    print("\n" + "=" * 60)
    print(f"✅ CHAPTER ANALYSIS COMPLETE! ({success_count}/{len(recording_folders)} recordings)")
    print("=" * 60)


if __name__ == "__main__":
    main()
