#!/usr/bin/env python3
"""
Analyze transcript content within chapters to identify individual stories/anecdotes.

This creates a finer-grained layer than chapters:
- Chapters: Major topic sections (~5-10 min each)
- Stories: Individual anecdotes/stories within chapters (~1-3 min each)

Stories are used for more precise alternate telling detection between recordings.

Run with: uv run 04_analyze_stories.py [recording_path]

Requires chapters.json to exist (run 03_analyze_chapters.py first).
"""

import json
import sys
from pathlib import Path

print("=" * 60)
print("STORY ANALYSIS SCRIPT")
print("=" * 60)

# Check for required packages
try:
    import ollama
except ImportError as e:
    print(f"\nMissing required package: {e}")
    print("\nInstall with:")
    print("  uv pip install ollama")
    sys.exit(1)

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_BASE_DIR = PROJECT_ROOT / "public" / "recordings"

# Model settings
PREFERRED_MODEL = "gemma3:12b"
MODELS_TO_TRY = ["gemma3:12b", "qwen3:14b", "gpt-oss:20b", "devstral:24b", "gemma3:27b"]

# Story duration constraints
MIN_STORY_DURATION = 30  # seconds - stories shorter than this get merged
MAX_STORY_DURATION = 180  # seconds - suggest splitting stories longer than this


def find_all_recordings(base_dir: Path) -> list[Path]:
    """Recursively find all folders containing chapters.json."""
    recordings = []
    
    def scan_folder(folder: Path):
        if (folder / "chapters.json").exists():
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
            if (folder / "chapters.json").exists():
                return [folder]
            else:
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
        model_list = models.get('models', []) if isinstance(models, dict) else models.models if hasattr(models, 'models') else []
        available = [m.get('name', m.model) if isinstance(m, dict) else m.model for m in model_list]
        if available:
            print(f"   Available models: {available}")
        return True
    except Exception as e:
        print(f"\n❌ Cannot connect to Ollama: {e}")
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


def unload_model(model_name: str):
    """Unload the model from memory after use."""
    print(f"\n🔄 Unloading model {model_name}...")
    try:
        ollama.generate(model=model_name, prompt="", keep_alive=0)
        print("   ✅ Model unloaded from memory")
    except Exception as e:
        print(f"   ⚠️ Could not unload model: {e}")


def get_chapter_transcript(segments: list, start_time: float, end_time: float) -> str:
    """Extract transcript text for a chapter's time range."""
    lines = []
    for seg in segments:
        seg_start = seg.get('start', 0)
        seg_end = seg.get('end', 0)
        
        # Include segment if it overlaps with chapter time range
        if seg_end >= start_time and seg_start < end_time:
            lines.append(f"[{seg_start:.0f}s] {seg['text']}")
    
    return "\n".join(lines)


def analyze_chapter_for_stories(
    chapter: dict,
    chapter_index: int,
    chapter_transcript: str,
    chapter_start: float,
    chapter_end: float,
    model_name: str
) -> list[dict]:
    """Use LLM to identify individual stories within a chapter."""
    
    chapter_duration = chapter_end - chapter_start
    
    # For short chapters, the whole thing is likely one story
    if chapter_duration < 120:  # Less than 2 minutes
        return [{
            "title": chapter["title"],
            "startTime": chapter_start,
            "description": chapter.get("description", ""),
            "chapterIndex": chapter_index
        }]
    
    prompt = f"""/no_think
Analyze this transcript excerpt from Linden "Lindy" Achen's memoirs.
Chapter: "{chapter['title']}"

Identify individual stories or anecdotes within this chapter.

A "story" is a self-contained narrative about a specific:
- Event (e.g., "Lindy's first day at the farm")
- Person (e.g., "Meeting Uncle Joe")
- Place (e.g., "The old farmhouse")
- Time period (e.g., "Harvest of 1918")

Chapter starts at {chapter_start:.0f}s, ends at {chapter_end:.0f}s (duration: {chapter_duration:.0f}s)

Transcript:
{chapter_transcript}

RULES:
- Each story should be 30-180 seconds (0.5-3 minutes)
- Look for transitions like "and then", "another time", "I remember when"
- If the chapter is one continuous narrative, return just one story
- Stories must be within the chapter time range ({chapter_start:.0f}s to {chapter_end:.0f}s)
- In titles and descriptions, refer to "Lindy" by name (not "the speaker" or "he")

Return ONLY valid JSON:
{{"stories": [{{"title": "Brief Story Title", "startTime": <seconds>, "description": "One sentence about this specific anecdote"}}]}}"""

    try:
        response_text = ""
        sys.stdout.write(f"      ")
        
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
        
        print()
        
        # Parse JSON
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0]
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0]
        
        result = json.loads(response_text.strip())
        stories = result.get("stories", [])
        
        # Validate and fix stories
        validated = []
        for story in stories:
            start = float(story.get("startTime", chapter_start))
            
            # Ensure start time is within chapter bounds
            if start < chapter_start:
                start = chapter_start
            if start >= chapter_end:
                continue  # Skip stories outside chapter
            
            validated.append({
                "title": story.get("title", "Untitled"),
                "startTime": start,
                "description": story.get("description", ""),
                "chapterIndex": chapter_index
            })
        
        # If no valid stories, use the whole chapter as one story
        if not validated:
            validated = [{
                "title": chapter["title"],
                "startTime": chapter_start,
                "description": chapter.get("description", ""),
                "chapterIndex": chapter_index
            }]
        
        return validated
        
    except Exception as e:
        print(f"   ⚠️ Error analyzing chapter: {e}")
        # Fallback: use chapter as single story
        return [{
            "title": chapter["title"],
            "startTime": chapter_start,
            "description": chapter.get("description", ""),
            "chapterIndex": chapter_index
        }]


def merge_short_stories(stories: list, min_duration: float = MIN_STORY_DURATION) -> list:
    """Merge stories that are too short."""
    if len(stories) < 2:
        return stories
    
    # Sort by start time
    stories = sorted(stories, key=lambda s: s["startTime"])
    
    merged = [stories[0]]
    
    for story in stories[1:]:
        prev = merged[-1]
        duration = story["startTime"] - prev["startTime"]
        
        if duration < min_duration:
            # Merge into previous
            if story.get('description') and story['description'] not in prev.get('description', ''):
                prev["description"] = f"{prev.get('description', '')}; {story['description']}".strip('; ')
            print(f"   ⚡ Merged short story: '{story['title']}' into '{prev['title']}' (was {duration:.0f}s)")
        else:
            merged.append(story)
    
    return merged


def process_recording(recording_folder: Path, model_name: str) -> bool:
    """Process a single recording folder to identify stories within chapters."""
    relative_path = get_relative_recording_path(recording_folder)
    transcript_file = recording_folder / "transcript.json"
    chapters_file = recording_folder / "chapters.json"
    
    print(f"\n{'='*60}")
    print(f"📂 Processing recording: {relative_path}")
    print(f"{'='*60}")
    
    if not chapters_file.exists():
        print(f"   ❌ Chapters file not found: {chapters_file}")
        print("   Run 03_analyze_chapters.py first")
        return False
    
    if not transcript_file.exists():
        print(f"   ❌ Transcript file not found: {transcript_file}")
        return False
    
    # Load data
    print(f"\n📂 Loading data...")
    with open(chapters_file, "r", encoding="utf-8") as f:
        chapters_data = json.load(f)
    
    with open(transcript_file, "r", encoding="utf-8") as f:
        transcript_data = json.load(f)
    
    chapters = chapters_data.get("chapters", [])
    segments = transcript_data.get("segments", [])
    total_duration = transcript_data.get("totalDuration", transcript_data.get("duration", 0))
    
    print(f"   Found {len(chapters)} chapters, {len(segments)} transcript segments")
    
    # Check if stories already exist
    if "stories" in chapters_data and chapters_data["stories"]:
        print(f"   ⏭️ Stories already exist ({len(chapters_data['stories'])} stories)")
        print("   Delete 'stories' key from chapters.json to regenerate")
        return True
    
    # Analyze each chapter for stories
    print(f"\n🔍 Analyzing chapters for individual stories...")
    all_stories = []
    
    for i, chapter in enumerate(chapters):
        chapter_start = chapter["startTime"]
        
        # Determine chapter end time
        if i + 1 < len(chapters):
            chapter_end = chapters[i + 1]["startTime"]
        else:
            chapter_end = total_duration
        
        print(f"\n   Chapter {i + 1}/{len(chapters)}: {chapter['title']} ({chapter_start:.0f}s - {chapter_end:.0f}s)")
        
        # Get transcript for this chapter
        chapter_transcript = get_chapter_transcript(segments, chapter_start, chapter_end)
        
        if not chapter_transcript:
            print(f"      No transcript text found, using chapter as single story")
            all_stories.append({
                "title": chapter["title"],
                "startTime": chapter_start,
                "description": chapter.get("description", ""),
                "chapterIndex": i
            })
            continue
        
        # Analyze for stories
        stories = analyze_chapter_for_stories(
            chapter, i, chapter_transcript,
            chapter_start, chapter_end, model_name
        )
        
        print(f"      Found {len(stories)} stories")
        all_stories.extend(stories)
    
    # Merge short stories
    print(f"\n🔄 Merging short stories...")
    all_stories = merge_short_stories(all_stories)
    
    # Sort by start time and assign IDs
    all_stories = sorted(all_stories, key=lambda s: s["startTime"])
    for i, story in enumerate(all_stories):
        story["id"] = f"story-{i}"
    
    print(f"\n📚 Final: {len(all_stories)} stories across {len(chapters)} chapters")
    
    # Print summary
    for story in all_stories:
        mins = int(story["startTime"] // 60)
        secs = int(story["startTime"] % 60)
        ch_idx = story.get("chapterIndex", 0)
        print(f"   [{mins:02d}:{secs:02d}] Ch{ch_idx + 1}: {story['title']}")
    
    # Save updated chapters.json with stories
    chapters_data["stories"] = all_stories
    
    with open(chapters_file, "w", encoding="utf-8") as f:
        json.dump(chapters_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n   ✅ Saved {len(all_stories)} stories to: {chapters_file}")
    
    return True


def main():
    # Parse command line args
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
        sys.exit(1)
    
    print(f"\n📦 Using model: {model_name}")
    
    # Get recording folders
    recording_folders = get_recording_folders(specific_recording)
    if not recording_folders:
        print(f"\n❌ No recording folders with chapters.json found")
        print("   Run 03_analyze_chapters.py first")
        sys.exit(1)
    
    print(f"\n📂 Found {len(recording_folders)} recording(s) to process:")
    for folder in recording_folders:
        rel_path = get_relative_recording_path(folder)
        print(f"   - {rel_path}")
    
    # Process each recording
    success_count = 0
    for recording_folder in recording_folders:
        if process_recording(recording_folder, model_name):
            success_count += 1
    
    # Unload model
    unload_model(model_name)
    
    print("\n" + "=" * 60)
    print(f"✅ STORY ANALYSIS COMPLETE! ({success_count}/{len(recording_folders)} recordings)")
    print("=" * 60)


if __name__ == "__main__":
    main()
