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
import re
import sys
import time
from pathlib import Path


def sanitize_llm_json(response_text: str) -> str:
    """Sanitize common LLM JSON errors before parsing.
    
    Fixes issues like:
    - "startTime": 4697s -> "startTime": 4697
    - "startTime": [4697s] -> "startTime": 4697
    - "startTime": 7603" -> "startTime": 7603 (missing opening quote)
    - "startTime": 7867s" -> "startTime": 7867 (s and trailing quote)
    - "correctedStartTime": 123s -> "correctedStartTime": 123
    """
    # Extract from markdown code blocks if present
    if "```json" in response_text:
        response_text = response_text.split("```json")[1].split("```")[0]
    elif "```" in response_text:
        response_text = response_text.split("```")[1].split("```")[0]
    
    # Fix numeric values with 's' suffix, brackets, or stray quotes
    # Handles: 4697s, [4697s], 4697", 4697s", [4697], etc.
    response_text = re.sub(r'"startTime"\s*:\s*\[?(\d+)s?"?\]?', r'"startTime": \1', response_text)
    response_text = re.sub(r'"endsAt"\s*:\s*\[?(\d+)s?"?\]?', r'"endsAt": \1', response_text)
    response_text = re.sub(r'"correctedStartTime"\s*:\s*\[?(\d+)s?"?\]?', r'"correctedStartTime": \1', response_text)
    
    return response_text.strip()


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
        # ollama.generate(model=model_name, prompt="", keep_alive=0)
        print("   ✅ Model unloaded from memory (Skipped to avoid conflict)")
    except Exception as e:
        print(f"   ⚠️ Could not unload model: {e}")


# Minimum chapter duration in seconds - chapters shorter than this will be merged
MIN_CHAPTER_DURATION = 180  # 3 minutes minimum for chapters
MIN_STORY_DURATION = 45  # 45 seconds minimum for stories


def snap_to_segment_start(target_time: float, segments: list, tolerance: float = 10.0) -> float:
    """Snap an LLM-provided time to the nearest actual segment start time.
    
    The LLM returns approximate integer times based on the prompt. This function
    finds the actual segment start time that's closest to the target.
    
    Args:
        target_time: The time returned by the LLM (often an integer)
        segments: List of transcript segments with 'start' times
        tolerance: Maximum seconds to search before/after target (default 10s)
    
    Returns:
        The exact segment start time, or target_time if no segment found nearby
    """
    if not segments:
        return target_time
    
    best_segment = None
    best_diff = float('inf')
    
    for seg in segments:
        seg_start = seg.get('start', 0)
        diff = abs(seg_start - target_time)
        
        # Only consider segments within tolerance
        if diff <= tolerance and diff < best_diff:
            best_diff = diff
            best_segment = seg
    
    if best_segment:
        return best_segment['start']
    
    return target_time


def analyze_opening_content(segments: list, model_name: str) -> dict | None:
    """
    Explicitly analyze the very beginning of the recording to identify the opening topic.
    This ensures we don't miss content before the first detected transition.
    """
    if not segments:
        return None
    
    # Get the first ~3 minutes of content (or all content if recording is shorter)
    opening_segments = [seg for seg in segments if seg["start"] < 180]
    
    if not opening_segments:
        return None
    
    # Build transcript text with timestamps
    transcript_lines = []
    for seg in opening_segments:
        transcript_lines.append(f"[{seg['start']:.0f}s] {seg['text']}")
    
    opening_text = "\n".join(transcript_lines)
    
    prompt = f"""/no_think
Analyze the OPENING of this recording and identify the FIRST topic being discussed.

The recording begins with:

{opening_text}

What is the narrator talking about at the very START of this recording (at timestamp 0)?
The title must describe the content that BEGINS the recording.

IMPORTANT: Common opening topics include:
- Recording introductions (date announcements, stating purpose)
- Obituary dictation
- Family history recitation
- Childhood memories
- Setting the scene for memoirs

Respond with ONLY valid JSON:
{{"title": "2-5 word title for opening topic", "description": "What the narrator discusses at the start", "endsAt": <approximate second when this topic ends or transitions>}}"""

    print("\n   🎬 Analyzing opening content...")
    sys.stdout.flush()
    
    try:
        response_text = ""
        for chunk in ollama.generate(
            model=model_name,
            prompt=prompt,
            stream=True,
            options={"temperature": 0.2, "num_ctx": 4096},
            keep_alive="10m"
        ):
            text = chunk.get("response", "")
            if text:
                response_text += text
                sys.stdout.write(text)
                sys.stdout.flush()
        
        print()  # Newline after stream
        
        # Parse JSON with sanitization
        response_text = sanitize_llm_json(response_text)
        result = json.loads(response_text)
        
        # Opening starts at the first segment's actual start time (not 0)
        first_segment_time = opening_segments[0]["start"] if opening_segments else 0.0
        
        # Return as a transition at the first segment time
        return {
            "title": result.get("title", "Introduction"),
            "startTime": first_segment_time,
            "description": result.get("description", ""),
            "endsAt": result.get("endsAt", 180)  # Default to 3 min if not specified
        }
        
    except Exception as e:
        print(f"   ⚠️  Could not analyze opening: {e}")
        return None


def analyze_content_for_chapters(segments: list, model_name: str, total_duration: float = None) -> dict:
    """Use LLM to analyze transcript and identify logical chapters and stories."""
    
    print(f"\n🤖 Analyzing content with {model_name}...")
    print("   Processing transcript in chunks to identify topic transitions...")
    
    # Get total duration
    if total_duration is None:
        total_duration = segments[-1]["end"] if segments else 0
    
    # FIRST: Explicitly analyze the opening content
    opening_topic = analyze_opening_content(segments, model_name)
    
    # Process in 8-minute windows with 3-minute overlap for better transition detection
    WINDOW_SIZE = 480  # 8 minutes
    OVERLAP = 180  # 3 minutes overlap to catch transitions
    
    all_transitions = []
    
    # Add opening topic as first transition if found
    if opening_topic:
        all_transitions.append(opening_topic)
        print(f"   📍 Opening topic: '{opening_topic['title']}' (ends ~{opening_topic.get('endsAt', 180)}s)")
    
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
            # Check if this is a significant gap
            next_seg = next((seg for seg in segments if seg["start"] >= window_start), None)
            if next_seg and next_seg["start"] > window_end:
                gap_mins = (next_seg["start"] - window_start) / 60
                if gap_mins > 2:  # Only mention gaps > 2 minutes
                    print(f"\n   Chunk {chunk_num} ({int(window_start/60)}:{int(window_start%60):02d}-{int(window_end/60)}:{int(window_end%60):02d}): (no speech - next segment at {int(next_seg['start']/60)}:{int(next_seg['start']%60):02d})")
            window_start += WINDOW_SIZE - OVERLAP
            continue
        
        # Format for prompt - include seconds directly
        # For longer segments (WhisperX style), also include segment end times for clarity
        transcript_lines = []
        for seg in window_segments:
            start_secs = seg["start"]
            end_secs = seg.get("end", start_secs)
            duration = end_secs - start_secs
            # For longer segments, show the range
            if duration > 15:
                transcript_lines.append(f"[{start_secs:.0f}s-{end_secs:.0f}s] {seg['text']}")
            else:
                transcript_lines.append(f"[{start_secs:.0f}s] {seg['text']}")
        
        chunk_text = "\n".join(transcript_lines)
        
        # Create focused prompt - ask for topic TRANSITIONS, not just chapters
        # Improved prompt for longer WhisperX segments
        prompt = f"""/no_think
Analyze this transcript chunk and identify where the narrator TRANSITIONS to a new topic.

CRITICAL RULES:
1. The title must describe what is BEING SAID at that exact timestamp
2. Look for EXPLICIT transition phrases or clear topic shifts
3. Each segment may contain multiple sentences - a transition can occur MID-SEGMENT
4. Use the START time of the segment where the transition occurs

Look for transitions like:
- "Now I'll tell you about..." / "Now I'm going to..." / "Let me go back to..."
- "Another time..." / "And then..." / "After that..."
- Year/date changes (e.g., "In 1924...")
- "The next thing..." / "I also..."
- Location changes, new people introduced, life event shifts

Transcript (timestamps in seconds from recording start):

{chunk_text}

For EACH topic transition you find, provide:
- title: 2-5 word title describing what STARTS at this timestamp
- startTime: The [XXXs] number where this NEW topic begins
- description: What the narrator is specifically discussing (use "Lindy" as the name. Lindy is a male narrator.)

IMPORTANT: 
- Only identify transitions where the speaker clearly shifts to a NEW subject
- The title must match what is said AT that timestamp, not later
- Return empty array if no clear topic transitions occur

Respond with ONLY valid JSON:
{{"transitions": [{{"title": "Topic Title", "startTime": 103, "description": "Brief description of what starts here"}}]}}"""

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
                    "temperature": 0.2,  # Lower temperature for more consistent results
                    "num_ctx": 4096,
                },
                keep_alive="10m"  # Keep model loaded for 10 minutes between requests
            ):
                text = chunk.get("response", "")
                if text:
                    response_text += text
                    sys.stdout.write(text)
                    sys.stdout.flush()
            
            print()  # Newline after stream
            
            # Parse JSON with sanitization
            response_text = sanitize_llm_json(response_text)
            chunk_result = json.loads(response_text)
            
            # Add transitions from this chunk
            for transition in chunk_result.get("transitions", chunk_result.get("chapters", [])):
                # Sanitize startTime - LLM sometimes adds "s" suffix or brackets
                start_time = transition.get("startTime", 0)
                if isinstance(start_time, str):
                    # Remove brackets and 's' suffix, e.g. "[13220s]" -> 13220
                    start_time = start_time.replace("[", "").replace("]", "").replace("s", "").replace("-", "")
                    try:
                        start_time = float(start_time)
                    except ValueError:
                        start_time = 0.0
                
                # Snap to actual segment start time for precision
                start_time = snap_to_segment_start(float(start_time), segments)
                transition["startTime"] = start_time
                all_transitions.append(transition)
            
        except json.JSONDecodeError as e:
            print(f"   ⚠️  Could not parse JSON: {e}")
            print(f"   Response: {response_text[:200]}...")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Move to next window
        window_start += WINDOW_SIZE - OVERLAP
    
    # Deduplicate transitions that were found in overlapping windows
    all_transitions = deduplicate_transitions(all_transitions)
    
    # Validate each transition by checking the actual transcript content
    print("\n🔍 Validating transitions against actual transcript content...")
    validated_transitions = validate_transitions_against_content(all_transitions, segments, model_name)
    
    # Group into chapters (major) and stories (minor)
    chapters, stories = group_into_chapters_and_stories(validated_transitions, total_duration)
    
    # Generate overall summary
    print("\n   Generating overall summary...")
    summary = generate_summary(segments, model_name, chapters)
    
    return {
        "chapters": chapters,
        "stories": stories,
        "summary": summary
    }


def deduplicate_transitions(transitions: list) -> list:
    """Remove duplicate transitions found in overlapping windows.
    
    Special handling: The first transition (from analyze_opening_content) 
    should be preserved as the opening topic.
    """
    if not transitions:
        return []
    
    # Sort by start time
    transitions = sorted(transitions, key=lambda t: t["startTime"])
    
    deduped = [transitions[0]]
    
    for trans in transitions[1:]:
        last = deduped[-1]
        time_diff = abs(trans["startTime"] - last["startTime"])
        
        # If within 45 seconds of each other, they're likely the same transition
        # (increased from 30 to handle longer WhisperX segments)
        if time_diff < 45:
            # Special case: if last is at time 0 (opening), prefer keeping it
            # unless the new one has a much better description
            if last["startTime"] == 0:
                # Keep the opening topic, but maybe update with better info
                if len(trans.get("description", "")) > len(last.get("description", "")) * 1.5:
                    # Significantly better description - merge the info
                    last["description"] = trans.get("description", last.get("description", ""))
                # Keep last (opening) either way
            else:
                # Keep the one with better description or combine them
                if len(trans.get("description", "")) > len(last.get("description", "")):
                    deduped[-1] = trans
        else:
            deduped.append(trans)
    
    print(f"   Deduplicated: {len(transitions)} -> {len(deduped)} transitions")
    return deduped


def validate_transitions_against_content(transitions: list, segments: list, model_name: str) -> list:
    """
    Validate each transition by checking if the title matches the actual content
    at that timestamp. Fix misaligned titles or timestamps.
    """
    if not transitions:
        return []
    
    validated = []
    
    for i, trans in enumerate(transitions):
        start_time = trans["startTime"]
        title = trans["title"]
        
        # Get ~90 seconds of transcript starting at this timestamp (enough to see major events)
        context_segments = [
            seg for seg in segments
            if seg["start"] >= start_time and seg["start"] < start_time + 90
        ]
        
        if not context_segments:
            validated.append(trans)
            continue
        
        context_text = " ".join([seg["text"] for seg in context_segments])
        
        # Quick sanity check with LLM
        prompt = f"""/no_think
Does this title accurately describe what the narrator is talking about at this timestamp?

Title: "{title}"
Timestamp: {start_time:.0f}s

Transcript at this timestamp:
"{context_text[:500]}"

IMPORTANT: If the transcript discusses a MAJOR LIFE EVENT (death, funeral, marriage, birth, moving, 
starting a career, war service, etc.), the title MUST reflect that event explicitly.
For example, if someone is talking about their father dying, the title should mention "Father's Death" 
not something generic like "Harvesting Grain" even if that's mentioned first.

If the title is accurate, respond: {{"valid": true}}
If the title should be changed, respond: {{"valid": false, "betterTitle": "more accurate title", "reason": "brief explanation"}}

Respond with ONLY valid JSON."""

        try:
            response = ollama.generate(
                model=model_name,
                prompt=prompt,
                stream=False,
                options={"temperature": 0.1, "num_ctx": 4096},
                keep_alive="10m"  # Keep model loaded for 10 minutes between requests
            )
            response_text = response.get("response", "")
            
            # Parse JSON with sanitization
            response_text = sanitize_llm_json(response_text)
            result = json.loads(response_text)
            
            if result.get("valid", True):
                validated.append(trans)
            else:
                # Use the better title
                better_title = result.get("betterTitle", title)
                reason = result.get("reason", "")
                old_title = trans["title"]
                trans["title"] = better_title
                validated.append(trans)
                print(f"   📝 Fixed title at {start_time:.0f}s: '{old_title}' -> '{better_title}' ({reason})")
                
        except Exception as e:
            # If validation fails, keep the original
            validated.append(trans)
    
    return validated


def group_into_chapters_and_stories(transitions: list, total_duration: float) -> tuple[list, list]:
    """
    Group transitions into chapters (major sections) and stories (sub-sections).
    
    Chapters are major topic shifts (e.g., life stages, major events).
    Stories are individual anecdotes within chapters.
    """
    if not transitions:
        return [], []
    
    # Sort by time
    transitions = sorted(transitions, key=lambda t: t["startTime"])
    
    # First, identify natural chapter boundaries by looking at duration gaps
    # and topic significance
    chapters = []
    stories = []
    
    # The first transition should already have the correct start time from analyze_opening_content
    # (which uses the first segment's actual start time)
    first_trans = transitions[0]
    
    # If first transition is already near the beginning (within 30s of start), use it
    if first_trans["startTime"] <= 30:
        # Keep the actual startTime from the transition (don't force to 0.0)
        chapters.append({
            "title": first_trans["title"],
            "startTime": first_trans["startTime"],
            "description": first_trans.get("description", "")
        })
        first_trans["isChapter"] = True
    else:
        # First transition is NOT at the beginning - this shouldn't happen often
        # now that we have analyze_opening_content, but handle it gracefully
        # Create a generic intro chapter that ends at the first real transition
        chapters.append({
            "title": "Introduction",
            "startTime": 0.0,
            "description": "Recording introduction"
        })
        # The first transition becomes a potential chapter/story
        # It will be evaluated in the loop below
        # We need to include it in the transitions to process
        pass  # transitions list already includes first_trans
    
    current_chapter_start = 0.0
    
    # Process all transitions (including first if it wasn't at 0)
    start_idx = 1 if first_trans["startTime"] <= 30 else 0
    
    for i, trans in enumerate(transitions[start_idx:], start_idx):
        time_since_chapter = trans["startTime"] - current_chapter_start
        
        # Determine next transition time for duration calc
        if i + 1 < len(transitions):
            next_time = transitions[i + 1]["startTime"]
        else:
            next_time = total_duration
        
        # A transition becomes a chapter if:
        # 1. It's been at least MIN_CHAPTER_DURATION since last chapter
        # 2. OR it represents a major life transition (detected by keywords)
        is_major = is_major_transition(trans["title"], trans.get("description", ""))
        
        if time_since_chapter >= MIN_CHAPTER_DURATION or is_major:
            chapters.append({
                "title": trans["title"],
                "startTime": trans["startTime"],
                "description": trans.get("description", "")
            })
            current_chapter_start = trans["startTime"]
            trans["isChapter"] = True
        else:
            # It's a story within the current chapter
            trans["isChapter"] = False
    
    # Now assign stories - skip transitions that became chapters (same title/time)
    story_id = 0
    for trans in transitions:
        chapter_idx = find_chapter_index(trans["startTime"], chapters)
        chapter = chapters[chapter_idx] if chapter_idx < len(chapters) else None
        
        # Skip if this transition is the same as the chapter it belongs to
        if chapter and abs(trans["startTime"] - chapter["startTime"]) < 1.0 and trans["title"] == chapter["title"]:
            continue
        
        stories.append({
            "title": trans["title"],
            "startTime": trans["startTime"],
            "description": trans.get("description", ""),
            "chapterIndex": chapter_idx,
            "id": f"story-{story_id}"
        })
        story_id += 1
    
    # Merge chapters that are too short
    chapters = merge_short_chapters(chapters, total_duration)
    
    # Update story chapter indices after merge
    for story in stories:
        story["chapterIndex"] = find_chapter_index(story["startTime"], chapters)
    
    return chapters, stories


def is_major_transition(title: str, description: str) -> bool:
    """Check if a transition represents a major life event.
    
    Major events are things like death, marriage, birth - significant life moments
    that should NEVER be merged into unrelated chapters.
    """
    text = (title + " " + description).lower()
    
    # High-priority major events - these MUST be their own chapters
    critical_keywords = [
        "death", "died", "passed away", "funeral", "dying", "illness",
        "father's death", "mother's death", "dad died", "dad's death",
        "marriage", "married", "wedding", "engaged",
        "born", "birth", "baby",
    ]
    
    # Lower-priority but still significant transitions
    significant_keywords = [
        "moved", "move to", "moving", "left for", "departed",
        "career", "first job", "started working", "hired",
        "war", "military", "army", "navy", "enlisted",
        "graduated", "college", "university",
        "business", "company", "started", "bought",
        "retired", "retirement",
    ]
    
    # Critical keywords are always major
    if any(kw in text for kw in critical_keywords):
        return True
    
    # Significant keywords need some context
    if any(kw in text for kw in significant_keywords):
        return True
    
    return False


def find_chapter_index(time: float, chapters: list) -> int:
    """Find which chapter a given timestamp belongs to."""
    for i in range(len(chapters) - 1, -1, -1):
        if time >= chapters[i]["startTime"]:
            return i
    return 0


def merge_short_chapters(chapters: list, total_duration: float) -> list:
    """Merge chapters that are too short into adjacent chapters.
    
    IMPORTANT: Never merge major life events (death, marriage, birth, etc.) 
    into unrelated chapters - they should stand alone even if short.
    """
    if len(chapters) < 2:
        return chapters
    
    merged = [chapters[0]]
    
    for i, chapter in enumerate(chapters[1:], 1):
        prev = merged[-1]
        prev_duration = chapter["startTime"] - prev["startTime"]
        
        # Check if current chapter is about a major life event
        current_is_major = is_major_transition(chapter["title"], chapter.get("description", ""))
        prev_is_major = is_major_transition(prev["title"], prev.get("description", ""))
        
        # Don't merge if current chapter is a major event and previous is not related
        if current_is_major and not topics_related(prev["title"], chapter["title"]):
            # Major events get their own chapter even if previous was short
            merged.append(chapter)
            continue
        
        if prev_duration < MIN_CHAPTER_DURATION:
            # Previous chapter is too short, merge current into it
            if chapter.get('description') and chapter['description'] not in prev.get('description', ''):
                prev["description"] = f"{prev.get('description', '')}; {chapter['description']}".strip('; ')
            
            # If current chapter is more significant, use its title instead
            if current_is_major and not prev_is_major:
                old_title = prev["title"]
                prev["title"] = chapter["title"]
                print(f"   ⚡ Merged short chapter: '{old_title}' into '{chapter['title']}' (promoted major event, {prev_duration:.0f}s)")
            else:
                print(f"   ⚡ Merged short chapter: '{chapter['title']}' into '{prev['title']}' ({prev_duration:.0f}s)")
        else:
            merged.append(chapter)
    
    # Check last chapter duration
    if len(merged) > 1:
        last = merged[-1]
        last_duration = total_duration - last["startTime"]
        last_is_major = is_major_transition(last["title"], last.get("description", ""))
        
        # Don't merge if the last chapter is a major life event
        if last_duration < MIN_CHAPTER_DURATION and not last_is_major:
            prev = merged[-2]
            if last.get('description') and last['description'] not in prev.get('description', ''):
                prev["description"] = f"{prev.get('description', '')}; {last['description']}".strip('; ')
            merged.pop()
            print(f"   ⚡ Merged final short chapter into previous")
    
    return merged


def topics_related(title1: str, title2: str) -> bool:
    """Check if two chapter topics are related (share key concepts)."""
    # Normalize
    t1 = title1.lower()
    t2 = title2.lower()
    
    # Extract key topic words (nouns, not articles/prepositions)
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
    words1 = set(w for w in t1.split() if w not in stop_words and len(w) > 2)
    words2 = set(w for w in t2.split() if w not in stop_words and len(w) > 2)
    
    # Check for overlapping significant words
    overlap = words1 & words2
    if overlap:
        return True
    
    # Check for semantic relationships
    related_groups = [
        {'death', 'died', 'dying', 'funeral', 'illness', 'sick', 'health', 'hospital', 'passed'},
        {'farm', 'farming', 'harvest', 'crop', 'field', 'cattle', 'livestock'},
        {'job', 'work', 'career', 'employment', 'hired', 'wages', 'pay'},
        {'family', 'father', 'mother', 'brother', 'sister', 'parents', 'relatives'},
        {'school', 'education', 'teacher', 'class', 'learning'},
        {'travel', 'trip', 'journey', 'moving', 'move', 'moved'},
    ]
    
    for group in related_groups:
        has1 = any(word in t1 for word in group)
        has2 = any(word in t2 for word in group)
        if has1 and has2:
            return True
    
    return False


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
                options={"temperature": 0.1, "num_ctx": 4096},
                keep_alive="10m"  # Keep model loaded for 10 minutes between requests
            ):
                text = chunk.get("response", "")
                if text:
                    response_text += text
                    sys.stdout.write(text)
                    sys.stdout.flush()
            print()  # Newline after stream
            
            # Parse JSON with sanitization
            response_text = sanitize_llm_json(response_text)
            result = json.loads(response_text)
            corrected_time = float(result.get("correctedStartTime", chapter["startTime"]))
            reason = result.get("reason", "")
            
            # Snap to actual segment start time for precision
            corrected_time = snap_to_segment_start(corrected_time, segments)
            
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
    
    # First chapter starts at the first segment's actual start time
    if corrected_chapters and segments:
        first_segment_time = segments[0].get("start", 0.0)
        corrected_chapters[0]["startTime"] = first_segment_time
    
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
            options={"temperature": 0.3, "num_ctx": 4096},
            keep_alive="10m"  # Keep model loaded for 10 minutes between requests
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
    stories = result.get("stories", [])
    
    print(f"\n📚 Identified {len(chapters)} chapters:")
    for ch in chapters:
        minutes = int(ch["startTime"] // 60)
        seconds = int(ch["startTime"] % 60)
        print(f"   [{minutes:02d}:{seconds:02d}] {ch['title']}")
    
    if stories:
        print(f"\n📖 Identified {len(stories)} stories")
    
    # Finalize chapters
    finalized_chapters = finalize_chapters(chapters)
    
    # Update story chapterIndex references after chapter finalization
    for story in stories:
        story["chapterIndex"] = find_chapter_index(story["startTime"], finalized_chapters)
    
    # Save chapters data (files info is in transcript.json, not duplicated here)
    chapters_path = recording_folder / "chapters.json"
    chapters_output = {
        "chapters": finalized_chapters,
        "summary": result.get("summary", ""),
        "stories": stories,
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
    # unload_model(model_name)
    
    print("\n" + "=" * 60)
    print(f"✅ CHAPTER ANALYSIS COMPLETE! ({success_count}/{len(recording_folders)} recordings)")
    print("=" * 60)


if __name__ == "__main__":
    main()
