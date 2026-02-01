#!/usr/bin/env python3
"""
Update topic descriptions in alternate_tellings.json.

Reads the existing alternate_tellings.json and regenerates the "topic" field
for each match using the actual transcript text from both recordings.

The new topics describe what the story is about, rather than comparing excerpts.
"""

import argparse
import json
import sys
from pathlib import Path

import ollama

# Add scripts directory to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from transcript_utils import load_transcript

BASE_DIR = SCRIPT_DIR.parent
MEMOIRS_DIR = BASE_DIR / "public" / "recordings" / "memoirs"

# Model configuration
MODEL = "gemma3:12b"

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'


def call_llm(prompt: str, model: str = None) -> str:
    """Call LLM via Ollama."""
    if model is None:
        model = MODEL
    
    try:
        response = ollama.chat(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            options={"num_ctx": 8192},
            keep_alive="10m",
        )
        return response.get('message', {}).get('content', '').strip()
    except Exception as e:
        return f"ERROR: {e}"


def load_recording_transcript(recording_name: str) -> list[dict]:
    """Load transcript segments from a recording."""
    recording_dir = MEMOIRS_DIR / recording_name
    data = load_transcript(recording_dir)
    if data is None:
        return []
    return data.get('segments', [])


def get_text_in_range(transcript: list[dict], start_time: float, end_time: float) -> str:
    """Extract all transcript text within a time range."""
    texts = []
    for seg in transcript:
        seg_start = seg.get('start', 0)
        seg_end = seg.get('end', 0)
        
        # Include segment if it overlaps with our range
        if seg_end >= start_time and seg_start < end_time:
            texts.append(seg.get('text', ''))
    
    return ' '.join(texts)


def format_time(seconds: float) -> str:
    """Format seconds as MM:SS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def generate_topic(norm_text: str, tdk_text: str, model: str) -> str:
    """Generate a topic description for a story match."""
    
    # Combine both texts for context, truncate if needed
    combined_text = f"Recording 1:\n{norm_text[:800]}\n\nRecording 2:\n{tdk_text[:800]}"
    
    prompt = f"""/no_think
You are reading two versions of the same story from Linden "Lindy" Achen's voice memoirs, recorded in the 1980s about his life from 1902 onwards.

{combined_text}

Write a SHORT topic description (one sentence, max 15 words) that describes what this story is about.

Rules:
- Describe the STORY CONTENT, not the recordings
- Do NOT say "both excerpts", "the excerpts", "both recordings", etc.
- Do NOT say "the narrator" - use "Lindy" or specific names
- Start with the main subject (Lindy, the family, Dad, etc.)
- Be specific: include names, places, dates when relevant
- Use past tense

Examples of GOOD topics:
- "Lindy's family moves from Iowa to Halbrite, Canada in March 1907"
- "Dad buys a Titan tractor in 1918"
- "Lindy works at a blacksmith shop during an ice storm"
- "The family arrives at their new homestead six miles north of Halbrite"

Examples of BAD topics:
- "Both excerpts describe a family moving to Canada" (don't reference excerpts)
- "The narrator recounts his childhood" (too vague, don't say narrator)
- "A story about farming" (too vague)

Return ONLY the topic sentence, nothing else."""

    response = call_llm(prompt, model=model)
    
    # Clean up response - remove quotes if present
    topic = response.strip().strip('"\'')
    
    # Fallback if response is an error or too long
    if topic.startswith("ERROR:") or len(topic) > 200:
        return None
    
    return topic


def main():
    parser = argparse.ArgumentParser(
        description='Update topic descriptions in alternate_tellings.json'
    )
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show results without saving')
    parser.add_argument('--model', type=str, default=MODEL,
                       help=f'LLM model to use (default: {MODEL})')
    parser.add_argument('--limit', type=int, default=0,
                       help='Limit number of topics to update (for testing)')
    args = parser.parse_args()
    
    model = args.model
    
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}UPDATE ALTERNATE TELLING TOPICS{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"\nModel: {model}")
    
    # Load existing alternate_tellings.json
    alt_tellings_path = MEMOIRS_DIR / "alternate_tellings.json"
    
    if not alt_tellings_path.exists():
        print(f"{Colors.RED}Error: {alt_tellings_path} not found{Colors.ENDC}")
        print("Run 05_find_story_overlaps.py first to generate the file.")
        return
    
    with open(alt_tellings_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    tellings = data.get('alternateTellings', [])
    print(f"\nLoaded {len(tellings)} alternate tellings")
    
    # Load transcripts
    print(f"\n{Colors.CYAN}Loading transcripts...{Colors.ENDC}")
    norm_transcript = load_recording_transcript('Norm_red')
    tdk_transcript = load_recording_transcript('TDK_D60_edited_through_air')
    
    if not norm_transcript or not tdk_transcript:
        print(f"{Colors.RED}Error: Could not load transcripts{Colors.ENDC}")
        return
    
    print(f"  Norm_red: {len(norm_transcript)} segments")
    print(f"  TDK: {len(tdk_transcript)} segments")
    
    # Process each telling
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}Generating new topics{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")
    
    updated_count = 0
    process_count = len(tellings) if args.limit == 0 else min(args.limit, len(tellings))
    
    for i, telling in enumerate(tellings[:process_count]):
        norm_info = telling.get('Norm_red', {})
        tdk_info = telling.get('TDK_D60_edited_through_air', {})
        
        norm_start = norm_info.get('startTime', 0)
        norm_end = norm_info.get('endTime', 0)
        tdk_start = tdk_info.get('startTime', 0)
        tdk_end = tdk_info.get('endTime', 0)
        
        old_topic = telling.get('topic', '')
        
        print(f"{Colors.CYAN}[{i+1}/{process_count}]{Colors.ENDC} ", end="")
        print(f"Norm {format_time(norm_start)}-{format_time(norm_end)}, ", end="")
        print(f"TDK {format_time(tdk_start)}-{format_time(tdk_end)}")
        print(f"  {Colors.DIM}Old: {old_topic[:60]}...{Colors.ENDC}" if len(old_topic) > 60 else f"  {Colors.DIM}Old: {old_topic}{Colors.ENDC}")
        
        # Get transcript text for both regions
        norm_text = get_text_in_range(norm_transcript, norm_start, norm_end)
        tdk_text = get_text_in_range(tdk_transcript, tdk_start, tdk_end)
        
        if not norm_text or not tdk_text:
            print(f"  {Colors.YELLOW}Skipping - missing transcript text{Colors.ENDC}")
            continue
        
        # Generate new topic
        new_topic = generate_topic(norm_text, tdk_text, model)
        
        if new_topic:
            telling['topic'] = new_topic
            updated_count += 1
            print(f"  {Colors.GREEN}New: {new_topic}{Colors.ENDC}")
        else:
            print(f"  {Colors.RED}Failed to generate topic{Colors.ENDC}")
    
    # Summary
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}RESULTS{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"\nUpdated {updated_count}/{process_count} topics")
    
    # Save output
    if not args.dry_run and updated_count > 0:
        with open(alt_tellings_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\n{Colors.GREEN}Saved to: {alt_tellings_path}{Colors.ENDC}")
    else:
        if args.dry_run:
            print(f"\n{Colors.YELLOW}(Dry run - not saved){Colors.ENDC}")
        else:
            print(f"\n{Colors.YELLOW}(No updates to save){Colors.ENDC}")
    
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print("DONE")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")


if __name__ == "__main__":
    main()
