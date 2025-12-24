"""
Analyze transcript content and generate chapter structure using Ollama.
Run with: uv run 03_analyze_chapters.py

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
OUTPUT_DIR = PROJECT_ROOT / "public" / "audio" / "christmas1986"
TRANSCRIPT_FILE = OUTPUT_DIR / "transcript.json"

# Model to use (try these in order - optimized for RTX 4090 24GB with ~17GB available)
PREFERRED_MODEL = "gemma3:12b"
MODELS_TO_TRY = ["gemma3:12b", "gpt-oss:20b", "qwen3:14b", "devstral:24b", "gemma3:27b"]


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
            # Check for exact match or partial match
            for avail in available:
                if model.split(":")[0] in avail:
                    print(f"   Using model: {avail}")
                    return avail
        
        # No preferred model found - try to pull the preferred one
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


def analyze_content_for_chapters(segments: list, model_name: str) -> dict:
    """Use LLM to analyze transcript and identify logical chapters."""
    
    print(f"\n🤖 Analyzing content with {model_name}...")
    print("   Processing transcript in chunks for better accuracy...")
    
    # Get total duration
    total_duration = segments[-1]["end"] if segments else 0
    
    # Process in 5-minute windows with 30-second overlap
    WINDOW_SIZE = 300  # 5 minutes
    OVERLAP = 30  # 30 seconds
    
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
        
        # Format for prompt
        transcript_lines = []
        for seg in window_segments:
            minutes = int(seg["start"] // 60)
            seconds = int(seg["start"] % 60)
            transcript_lines.append(f"[{minutes:02d}:{seconds:02d}] {seg['text']}")
        
        chunk_text = "\n".join(transcript_lines)
        
        # Create focused prompt for this chunk
        prompt = f"""You are analyzing a 5-minute segment of a 1986 Christmas memoir recording from a grandfather to his son.

Transcript segment ({int(window_start/60)}:{int(window_start%60):02d} to {int(window_end/60)}:{int(window_end%60):02d}):

{chunk_text}

Identify 1-3 distinct topics or stories in this segment. For each:
- Title: 2-4 words, descriptive (e.g., "Pie Crust Recipe", "Uncle's Health")
- startTime: MUST be in TOTAL SECONDS from start of recording. Example: [36:30] = 2190 seconds, not 36.30
- Description: Terse phrase WITHOUT "the speaker" or "he discusses". Just state the topic directly.
  Good: "Childhood memories; uncle and Lorry."
  Bad: "The speaker shares childhood memories about his uncle."

Respond with valid JSON only:
{{
  "chapters": [
    {{
      "id": 1,
      "title": "Short Topic Title",
      "startTime": 2190.0,
      "description": "Terse topic description"
    }}
  ]
}}

CRITICAL: startTime must be total seconds, NOT minutes. Convert [MM:SS] to (MM*60)+SS."""

        print(f"\n   Chunk {chunk_num} ({int(window_start/60)}:{int(window_start%60):02d}-{int(window_end/60)}:{int(window_end%60):02d}):")
        sys.stdout.flush()
        
        # Stream response
        response_text = ""
        thinking_text = ""
        
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
                thinking = chunk.get("thinking", "")
                if thinking:
                    thinking_text += thinking
                    sys.stdout.write(f"\033[93m{thinking}\033[0m")
                    sys.stdout.flush()
                
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
    """Merge chapters that are close together with similar content."""
    if not chapters:
        return []
    
    # Sort by start time
    chapters = sorted(chapters, key=lambda c: c["startTime"])
    
    merged = [chapters[0]]
    
    for chapter in chapters[1:]:
        last = merged[-1]
        time_diff = chapter["startTime"] - last["startTime"]
        
        # If chapters are within 60 seconds and have similar titles, merge them
        if time_diff < 60 and chapters_similar(last["title"], chapter["title"]):
            # Keep the earlier start time, combine descriptions
            last["description"] = f"{last['description']}; {chapter['description']}"
        else:
            # Renumber and add
            chapter["id"] = len(merged) + 1
            merged.append(chapter)
    
    # Renumber final list
    for i, chapter in enumerate(merged, 1):
        chapter["id"] = i
    
    return merged


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


def generate_summary(segments: list, model_name: str, chapters: list) -> str:
    """Generate a brief overall summary."""
    chapter_list = "\n".join([
        f"- {ch['title']}: {ch['description']}"
        for ch in chapters
    ])
    
    prompt = f"""Based on these chapter topics from a 1986 Christmas memoir, write a 2-3 sentence summary:

{chapter_list}

Write a concise summary of what this recording covers. Be direct and factual."""

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


def create_peaks_regions(chapters: list, segments: list) -> list:
    """Convert chapters to peaks.js region format."""
    regions = []
    
    # Get the total duration from last segment
    total_duration = segments[-1]["end"] if segments else 0
    
    for i, chapter in enumerate(chapters):
        # Determine end time (start of next chapter or end of recording)
        if i < len(chapters) - 1:
            end_time = chapters[i + 1]["startTime"]
        else:
            end_time = total_duration
        
        # Create region in peaks.js format
        region = {
            "id": f"chapter-{chapter['id']}",
            "startTime": chapter["startTime"],
            "endTime": end_time,
            "labelText": chapter["title"],
            "color": f"rgba(100, 149, 237, 0.3)",  # Cornflower blue with transparency
        }
        regions.append(region)
    
    return regions


def create_table_of_contents(chapters: list) -> list:
    """Create table of contents data for the UI."""
    toc = []
    for chapter in chapters:
        # Format time as MM:SS
        minutes = int(chapter["startTime"] // 60)
        seconds = int(chapter["startTime"] % 60)
        
        toc.append({
            "id": chapter["id"],
            "title": chapter["title"],
            "startTime": chapter["startTime"],
            "formattedTime": f"{minutes:02d}:{seconds:02d}",
            "description": chapter.get("description", ""),
        })
    
    return toc


def main():
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
    
    # Load segments from transcript.json
    if not TRANSCRIPT_FILE.exists():
        print(f"\n❌ Transcript file not found: {TRANSCRIPT_FILE}")
        print("   Run 01_transcribe.py first")
        sys.exit(1)
    
    print(f"\n📂 Loading transcript from: {TRANSCRIPT_FILE}")
    with open(TRANSCRIPT_FILE, "r", encoding="utf-8") as f:
        transcript_data = json.load(f)
    
    segments = transcript_data.get("segments", [])
    print(f"   Found {len(segments)} segments")
    
    # Analyze content
    result = analyze_content_for_chapters(segments, model_name)
    
    if not result or "chapters" not in result:
        print("\n❌ Chapter analysis failed!")
        unload_model(model_name)
        sys.exit(1)
    
    chapters = result["chapters"]
    print(f"\n📚 Identified {len(chapters)} chapters:")
    for ch in chapters:
        minutes = int(ch["startTime"] // 60)
        seconds = int(ch["startTime"] % 60)
        print(f"   [{minutes:02d}:{seconds:02d}] {ch['title']}")
    
    # Create peaks.js regions
    regions = create_peaks_regions(chapters, segments)
    
    # Create table of contents
    toc = create_table_of_contents(chapters)
    
    # Save chapters data
    chapters_path = OUTPUT_DIR / "chapters.json"
    with open(chapters_path, "w", encoding="utf-8") as f:
        json.dump({
            "chapters": chapters,
            "summary": result.get("summary", ""),
        }, f, indent=2, ensure_ascii=False)
    print(f"\n   ✅ Saved chapters: {chapters_path}")
    
    # Save peaks.js regions
    regions_path = OUTPUT_DIR / "regions.json"
    with open(regions_path, "w", encoding="utf-8") as f:
        json.dump(regions, f, indent=2)
    print(f"   ✅ Saved regions: {regions_path}")
    
    # Save table of contents
    toc_path = OUTPUT_DIR / "toc.json"
    with open(toc_path, "w", encoding="utf-8") as f:
        json.dump(toc, f, indent=2, ensure_ascii=False)
    print(f"   ✅ Saved TOC: {toc_path}")
    
    # Unload model to free memory
    unload_model(model_name)
    
    print("\n" + "=" * 60)
    print("✅ CHAPTER ANALYSIS COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
