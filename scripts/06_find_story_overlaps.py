#!/usr/bin/env python3
"""
Find overlapping stories between memoir recordings using LLM.

This analyzes the actual transcript text within STORIES (not chapters) to identify:
1. Stories that appear in both recordings (different tellings)
2. The start times for each matched story in both recordings
3. Cross-references for the UI

Output: alternate_tellings.json with time-based references at the story level.

Requires: Run 05_analyze_stories.py first to generate story data.
"""

import json
import re
import sys
from pathlib import Path
from ollama import Client

BASE_DIR = Path(__file__).parent.parent
MEMOIRS_DIR = BASE_DIR / "public" / "recordings" / "memoirs"

# Model to use - gemma3 works well with simple prompts
MODEL = "gemma3:12b"

# Match threshold (8+ = match)
MATCH_THRESHOLD = 8

# Create client with longer timeout
ollama_client = Client(timeout=300.0)


def call_llm(prompt: str, model: str = None, stream_output: bool = False) -> str:
    """Call LLM via Ollama for simple yes/no comparison."""
    if model is None:
        model = MODEL
    try:
        if stream_output:
            stream = ollama_client.chat(
                model=model,
                messages=[{'role': 'user', 'content': prompt}],
                stream=True,
            )
            content = ''
            for chunk in stream:
                if chunk.message.content:
                    print(chunk.message.content, end='', flush=True)
                    content += chunk.message.content
            return content.strip()
        else:
            response = ollama_client.chat(
                model=model,
                messages=[{'role': 'user', 'content': prompt}],
            )
            return response.message.content.strip()
    except Exception as e:
        return f"ERROR: {e}"


def load_chapters_and_stories(recording_name: str) -> tuple[list[dict], list[dict]]:
    """Load chapters and stories from a recording."""
    path = MEMOIRS_DIR / recording_name / "chapters.json"
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('chapters', []), data.get('stories', [])


def load_transcript(recording_name: str) -> list[dict]:
    """Load transcript segments from a recording."""
    path = MEMOIRS_DIR / recording_name / "transcript.json"
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('segments', [])


def get_story_text(transcript: list[dict], start_time: float, end_time: float, max_words: int = 100) -> str:
    """Extract transcript text for a story's time range.
    
    Only uses the FIRST max_words to focus on the story's opening,
    which typically identifies the specific event being discussed.
    """
    words = []
    for segment in transcript:
        seg_start = segment.get('start', 0)
        seg_end = segment.get('end', 0)
        
        # Include segment if it overlaps with story time range
        if seg_end >= start_time and seg_start < end_time:
            words.extend(segment.get('text', '').split())
            if len(words) >= max_words:
                break
    
    return ' '.join(words[:max_words])


def get_story_end_time(stories: list[dict], story_index: int, total_duration: float) -> float:
    """Get the end time of a story (start of next story or end of recording)."""
    if story_index + 1 < len(stories):
        return stories[story_index + 1].get('startTime', total_duration)
    return total_duration


def format_stories_for_analysis(recording_name: str, stories: list[dict], transcript: list[dict], total_duration: float) -> str:
    """Format stories with actual transcript excerpts for Gemma analysis."""
    # Use clear prefix for each recording
    prefix = "N" if "Norm" in recording_name else "T"
    lines = [f"=== {recording_name} ({len(stories)} stories) ==="]
    
    for i, story in enumerate(stories):
        title = story.get('title', 'Untitled')
        time = story.get('startTime', 0)
        end_time = get_story_end_time(stories, i, total_duration)
        
        # Extract transcript text
        text = get_story_text(transcript, time, end_time, max_words=150)
        
        mins = int(time // 60)
        secs = int(time % 60)
        
        lines.append(f"\n[{prefix}{i}] {title} (starts at {mins}:{secs:02d})")
        lines.append(f"Text: {text}...")
    
    return "\n".join(lines)


def find_story_overlaps(recordings: list[str]) -> dict:
    """Use LLM to find overlapping stories between recordings.
    
    Process each Norm_red story against each TDK story one-by-one.
    At the end of each Norm_red story, store the best match if any.
    """
    
    print("Loading stories and transcripts...")
    all_stories = {}
    all_transcripts = {}
    
    for rec in recordings:
        chapters, stories = load_chapters_and_stories(rec)
        transcript = load_transcript(rec)
        
        if not stories:
            print(f"  WARNING: {rec}: No stories found! Run 05_analyze_stories.py first")
            return {'error': f'No stories found in {rec}'}
        
        all_stories[rec] = stories
        all_transcripts[rec] = transcript
        print(f"  {rec}: {len(stories)} stories, {len(transcript)} transcript segments")
    
    norm_stories = all_stories['Norm_red']
    tdk_stories = all_stories['TDK_D60_edited_through_air']
    norm_transcript = all_transcripts['Norm_red']
    tdk_transcript = all_transcripts['TDK_D60_edited_through_air']
    
    norm_duration = norm_transcript[-1].get('end', 0) if norm_transcript else 0
    tdk_duration = tdk_transcript[-1].get('end', 0) if tdk_transcript else 0
    
    all_matches = []
    
    # Pre-extract all TDK story texts (100 words = focus on story opening)
    tdk_texts = []
    for i, tdk_story in enumerate(tdk_stories):
        if i + 1 < len(tdk_stories):
            tdk_end = tdk_stories[i + 1].get('startTime', tdk_duration)
        else:
            tdk_end = tdk_duration
        tdk_texts.append(get_story_text(tdk_transcript, tdk_story['startTime'], tdk_end, max_words=100))
    
    print(f"\nComparing {len(norm_stories)} Norm_red stories against {len(tdk_stories)} TDK stories...")
    print("   One-by-one comparison for each pair.\n")
    
    for norm_idx, norm_story in enumerate(norm_stories):
        # Get the end time for this story
        if norm_idx + 1 < len(norm_stories):
            norm_end = norm_stories[norm_idx + 1].get('startTime', norm_duration)
        else:
            norm_end = norm_duration
        
        # Get actual transcript text (100 words = focus on story opening)
        norm_text = get_story_text(norm_transcript, norm_story['startTime'], norm_end, max_words=100)
        norm_time = norm_story.get('startTime', 0)
        
        mins = int(norm_time // 60)
        secs = int(norm_time % 60)
        
        print(f"   [R{norm_idx+1}/{len(norm_stories)}] ({mins}:{secs:02d}) ", end="", flush=True)
        
        # Track best match for this Norm story
        best_match = None
        best_score = 0
        
        # Compare against each TDK story one-by-one
        for tdk_idx, tdk_text in enumerate(tdk_texts):
            score = compare_two_stories(norm_text, tdk_text, verbose=False)
            print(f"T{tdk_idx}={score} ", end="", flush=True)
            
            if score > best_score:
                best_score = score
                best_match = tdk_idx
        
        print()  # newline after all T comparisons
        
        # Store best match if found (threshold 8+ for stricter matching)
        if best_match is not None and best_score >= MATCH_THRESHOLD:
            # Generate a topic from the matched stories
            tdk_story = tdk_stories[best_match]
            topic = generate_topic(norm_story['title'], tdk_story['title'])
            
            all_matches.append({
                'norm_red_story': norm_idx,
                'tdk_story': best_match,
                'topic': topic,
                'confidence': 'HIGH' if best_score >= 9 else 'MEDIUM',
                'score': best_score
            })
            print(f"   BEST -> T{best_match} (score: {best_score}) - {topic}")
        else:
            print(f"   no match (best: {best_score})")
    
    print(f"\nFound {len(all_matches)} total matches")
    
    return {
        'recordings': recordings,
        'stories': all_stories,
        'transcripts': all_transcripts,
        'matches': all_matches
    }


def compare_two_stories(text_a: str, text_b: str, verbose: bool = False) -> int:
    """Compare two story texts and return a similarity score 0-10."""
    prompt = f"""These are two excerpts from memoir recordings. Do they describe the SAME job or event?

A: {text_a}

B: {text_b}

Answer: Score 0-10 where 10 means definitely the same event. Just the number."""

    response = call_llm(prompt, stream_output=verbose)
    
    # Parse the score
    match = re.search(r'\b(\d+)\b', response)
    if match:
        score = int(match.group(1))
        return min(10, max(0, score))  # Clamp to 0-10
    return 0


def generate_topic(title_a: str, title_b: str) -> str:
    """Generate a brief topic description from two matched story titles."""
    prompt = f"""These two story titles describe the same event from different recordings:

Title 1: {title_a}
Title 2: {title_b}

Write a brief topic label (3-6 words) that captures what both are about. Just the topic, no quotes or punctuation."""

    response = call_llm(prompt)
    
    # Clean up the response
    topic = response.strip().strip('"\'').strip()
    # Limit length and clean up
    if len(topic) > 60:
        topic = topic[:57] + "..."
    return topic if topic else "Matched Story"


def create_alternate_tellings_json(
    recordings: list[str],
    stories: dict,
    matches: list[dict]
) -> dict:
    """Create alternate_tellings.json with proper story-level time references."""
    
    primary = 'Norm_red'
    secondary = 'TDK_D60_edited_through_air'
    
    alternate_tellings = []
    
    for m in matches:
        norm_idx = m['norm_red_story']
        tdk_idx = m['tdk_story']
        
        # Validate indices
        if norm_idx >= len(stories[primary]):
            print(f"  WARNING: Invalid Norm_red story index {norm_idx}, skipping")
            continue
        if tdk_idx >= len(stories[secondary]):
            print(f"  WARNING: Invalid TDK story index {tdk_idx}, skipping")
            continue
        
        norm_story = stories[primary][norm_idx]
        tdk_story = stories[secondary][tdk_idx]
        
        alternate_tellings.append({
            'topic': m['topic'],
            'confidence': m['confidence'],
            'Norm_red': {
                'storyId': norm_story.get('id', f'story-{norm_idx}'),
                'startTime': norm_story.get('startTime'),
                'title': norm_story.get('title')
            },
            'TDK_D60_edited_through_air': {
                'storyId': tdk_story.get('id', f'story-{tdk_idx}'),
                'startTime': tdk_story.get('startTime'),
                'title': tdk_story.get('title')
            }
        })
    
    return {
        'primaryRecording': primary,
        'secondaryRecording': secondary,
        'description': 'Cross-references between overlapping stories in both memoir recordings (story-level precision)',
        'alternateTellings': alternate_tellings,
        'stats': {
            'totalMatches': len(alternate_tellings),
            'primaryStoryCount': len(stories[primary]),
            'secondaryStoryCount': len(stories[secondary])
        }
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Find overlapping stories between memoir recordings using transcript analysis'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show results without saving to alternate_tellings.json file'
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("MEMOIR STORY OVERLAP ANALYSIS (STORY-LEVEL PRECISION)")
    print("=" * 60)
    print("\nNarrator: Linden 'Lindy' Achen")
    print("Recordings: Norm_red (later), TDK_D60_edited_through_air (earlier)")
    print("\nThis will analyze the actual spoken text within each STORY")
    print("to find matching anecdotes between recordings.")
    
    recordings = ['Norm_red', 'TDK_D60_edited_through_air']
    
    # Analyze with Gemma
    result = find_story_overlaps(recordings)
    
    if 'error' in result:
        print(f"\n❌ Error: {result['error']}")
        return
    
    # Get matches from result (already parsed during iteration)
    matches = result.get('matches', [])
    
    print(f"\n\nTotal: {len(matches)} story matches found")
    
    if matches:
        print("\nMatched Stories:")
        for m in matches:
            # Validate indices before accessing
            if m['norm_red_story'] >= len(result['stories']['Norm_red']):
                print(f"  WARNING: Invalid Norm_red index {m['norm_red_story']}, skipping")
                continue
            if m['tdk_story'] >= len(result['stories']['TDK_D60_edited_through_air']):
                print(f"  WARNING: Invalid TDK index {m['tdk_story']}, skipping")
                continue
                
            norm_st = result['stories']['Norm_red'][m['norm_red_story']]
            tdk_st = result['stories']['TDK_D60_edited_through_air'][m['tdk_story']]
            print(f"  R{m['norm_red_story']}: {norm_st['title']} ({norm_st['startTime']:.0f}s)")
            print(f"  T{m['tdk_story']}: {tdk_st['title']} ({tdk_st['startTime']:.0f}s)")
            print(f"    Score: {m.get('score', '?')}, Confidence: {m['confidence']}")
            print()
    
    if not args.dry_run:
        # Create alternate_tellings.json
        output = create_alternate_tellings_json(
            recordings,
            result['stories'],
            matches
        )
        
        output_path = MEMOIRS_DIR / "alternate_tellings.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"\nAlternate tellings saved to: {output_path}")
        print(f"Total matches: {len(output['alternateTellings'])}")
    else:
        print(f"\nDry run - results not saved")
    
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()