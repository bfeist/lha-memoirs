#!/usr/bin/env python3
"""
Find overlapping stories between memoir recordings using sliding window topic extraction.

Strategy:
1. Break transcripts into overlapping time windows (60s windows, 30s overlap)
2. Extract key topics/entities from each window using LLM
3. Match windows across recordings based on topic similarity
4. Merge adjacent matches into story spans

This approach finds matches at any point in the transcript, not just at chapter boundaries.

Output: alternate_tellings.json with timestamp-to-timestamp story matches.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
import ollama

# Add scripts directory to path for imports
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from transcript_utils import load_transcript

BASE_DIR = SCRIPT_DIR.parent
MEMOIRS_DIR = BASE_DIR / "public" / "recordings" / "memoirs"

# Model configuration - can switch between models
MODEL = "gemma3:12b"  # Default model
# MODEL = "gpt-oss:20b"  # Alternative with larger context

# Window configuration
WINDOW_DURATION = 60  # 60 second windows
WINDOW_OVERLAP = 30   # 30 second overlap

# Match threshold for topic similarity (0-10 scale)
# 7+ = good confidence same story (comparison prompt now more flexible)
MATCH_THRESHOLD = 7

# TDK transcript is only corrected up to this point (seconds)
TDK_CORRECTED_LIMIT = 3169  # ~52:49

# Minimum text length (chars) for a window to be considered for matching
# Filters out tape noise / introduction segments
MIN_TEXT_LENGTH = 150

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


@dataclass
class TimeWindow:
    """A time window with extracted topics."""
    start_time: float
    end_time: float
    text: str
    topics: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)  # people, places, dates
    summary: str = ""


@dataclass 
class StoryMatch:
    """A matched story between recordings."""
    norm_start: float
    norm_end: float
    tdk_start: float
    tdk_end: float
    topic: str
    confidence: str
    score: float
    norm_text_preview: str = ""
    tdk_text_preview: str = ""


def call_llm(prompt: str, model: str = None, stream: bool = False) -> str:
    """Call LLM via Ollama."""
    if model is None:
        model = MODEL
    
    try:
        if stream:
            response_text = ""
            for chunk in ollama.chat(
                model=model,
                messages=[{'role': 'user', 'content': prompt}],
                stream=True,
                options={"num_ctx": 8192},
                keep_alive="10m",
            ):
                part = chunk.get('message', {}).get('content', '')
                if part:
                    print(part, end='', flush=True)
                    response_text += part
            return response_text.strip()
        else:
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


def create_windows(transcript: list[dict], window_duration: float = WINDOW_DURATION, 
                   overlap: float = WINDOW_OVERLAP, max_time: float = None) -> list[TimeWindow]:
    """Create overlapping time windows from transcript.
    
    Args:
        transcript: List of transcript segments
        window_duration: Duration of each window in seconds
        overlap: Overlap between windows in seconds
        max_time: Optional maximum time limit (for partially corrected transcripts)
    """
    if not transcript:
        return []
    
    windows = []
    total_duration = transcript[-1].get('end', 0)
    
    # Apply max_time limit if specified
    if max_time is not None:
        total_duration = min(total_duration, max_time)
    
    start_time = 0
    while start_time < total_duration:
        end_time = min(start_time + window_duration, total_duration)
        text = get_text_in_range(transcript, start_time, end_time)
        
        # Only create window if there's enough actual content (filters tape noise)
        if text.strip() and len(text.strip()) >= MIN_TEXT_LENGTH:
            windows.append(TimeWindow(
                start_time=start_time,
                end_time=end_time,
                text=text
            ))
        
        start_time += (window_duration - overlap)
    
    return windows


def format_time(seconds: float) -> str:
    """Format seconds as MM:SS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def extract_topics_batch(windows: list[TimeWindow], recording_name: str, model: str) -> list[TimeWindow]:
    """Extract topics from windows in batches for efficiency."""
    prefix = "N" if "Norm" in recording_name else "T"
    
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}Extracting topics from {recording_name}{Colors.ENDC}")
    print(f"{Colors.DIM}Processing {len(windows)} windows...{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")
    
    # Process in batches of 5 windows
    BATCH_SIZE = 5
    
    for batch_start in range(0, len(windows), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(windows))
        batch = windows[batch_start:batch_end]
        
        # Build batch prompt
        window_texts = []
        for i, w in enumerate(batch):
            idx = batch_start + i
            window_texts.append(f"[{prefix}{idx}] ({format_time(w.start_time)}-{format_time(w.end_time)}):\n{w.text[:400]}...")
        
        prompt = f"""/no_think
Extract STORY ELEMENTS from these memoir transcript windows. These are voice memoirs by Linden "Lindy" Achen, recorded in the 1980s about his life from 1902 onwards.

{chr(10).join(window_texts)}

For EACH window [{prefix}0] through [{prefix}{len(batch)-1}], extract:
1. topics: 3-5 story elements capturing WHO did WHAT, WHERE, WHEN
   Focus on: the core event/action, rough time period, key people involved
   Style: Specific but casual. "Lindy gets a job", not "Lindy secures employment".
   GOOD: "Lindy moved from Iowa to Canada", "worked at blacksmith shop", "Dad died", "train journey to Canada"
   BAD: "relocation", "employment", "travel" (too formal/generic)
   Note: Same story may be told with different details - capture the CORE STORY not exact quotes
2. entities: ALL specific names, places, years mentioned
   Include: people (Joe, Zip, Mac), places (Halbrite, Iowa, Canada), years/ages (1907, age 8)
3. summary: One sentence describing THE STORY being told. 
   Style: "Lindy does X..." or "The Achen family does Y...". Avoid "The story concerns...".

Return ONLY valid JSON array:
[{{"id": "{prefix}0", "topics": ["story element 1", "story element 2"], "entities": ["Joe", "Halbrite", "1907"], "summary": "..."}}]"""

        print(f"{Colors.CYAN}Batch {batch_start//BATCH_SIZE + 1}/{(len(windows) + BATCH_SIZE - 1)//BATCH_SIZE}: ", end="")
        print(f"Windows {prefix}{batch_start}-{prefix}{batch_end-1}{Colors.ENDC}")
        
        response = call_llm(prompt, model=model)
        
        # Check for error
        if response.startswith("ERROR:"):
            print(f"  {Colors.RED}{response}{Colors.ENDC}")
            continue
        
        # Parse response
        try:
            # Extract JSON from response
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                results = json.loads(json_match.group())
                
                for result in results:
                    # Find matching window
                    id_match = re.search(r'(\d+)', result.get('id', ''))
                    if id_match:
                        idx = int(id_match.group())
                        if batch_start <= idx < batch_end:
                            local_idx = idx - batch_start
                            if local_idx < len(batch):
                                # Support both 'topics' (primary) and 'events' (fallback) keys
                                batch[local_idx].topics = result.get('topics', result.get('events', []))
                                batch[local_idx].entities = result.get('entities', [])
                                batch[local_idx].summary = result.get('summary', '')
                
                # Print extracted topics
                for i, w in enumerate(batch):
                    idx = batch_start + i
                    topics_str = ", ".join(w.topics[:4]) if w.topics else "(no topics)"
                    print(f"  {Colors.GREEN}[{prefix}{idx}]{Colors.ENDC} {format_time(w.start_time)}: {topics_str}")
                    
        except json.JSONDecodeError as e:
            print(f"  {Colors.RED}JSON parse error: {e}{Colors.ENDC}")
            print(f"  Response: {response[:200]}...")
    
    return windows


def compare_windows(norm_window: TimeWindow, tdk_window: TimeWindow, 
                   norm_idx: int, tdk_idx: int, model: str, verbose: bool = False) -> tuple[float, str]:
    """Compare two windows and return similarity score and matching topic."""
    
    # Quick pre-filter: check for any overlapping topics/entities
    norm_terms = set(t.lower() for t in norm_window.topics + norm_window.entities)
    tdk_terms = set(t.lower() for t in tdk_window.topics + tdk_window.entities)
    
    # Check for obvious matches
    overlap = norm_terms & tdk_terms
    if not overlap and norm_terms and tdk_terms:
        # No keyword overlap - do a quick semantic check
        # Look for year/date patterns that might match
        norm_years = set(re.findall(r"'?\d{2,4}", ' '.join(norm_window.topics + norm_window.entities)))
        tdk_years = set(re.findall(r"'?\d{2,4}", ' '.join(tdk_window.topics + tdk_window.entities)))
        
        if not (norm_years & tdk_years):
            # No year overlap and no keyword overlap - likely not a match
            return 0, ""
    
    # Build comparison prompt
    prompt = f"""/no_think
Do these two memoir excerpts describe the SAME story/event?

Both are from Linden "Lindy" Achen, telling his life story.
Excerpt A = "Memoirs Recording"
Excerpt B = "Memoirs Draft Recording"

EXCERPT A (at {format_time(norm_window.start_time)}):
Topics: {', '.join(norm_window.topics)}
Entities: {', '.join(norm_window.entities)}
Text: {norm_window.text[:400]}...

EXCERPT B (at {format_time(tdk_window.start_time)}):
Topics: {', '.join(tdk_window.topics)}
Entities: {', '.join(tdk_window.entities)}
Text: {tdk_window.text[:400]}...

If SAME STORY (score 7+), write a brief description.
STYLE GUIDELINES for description:
1. CASUAL & DIRECT: Use plain English. "Lindy is told to go..." not "Lindy is instructed...". "Lindy's plan..." not "Lindy's intentions...". "Working at specific place" not "Employment experience".
2. SPECIFIC: Use "Lindy" or "The Achen family" or "Dad/Joe/Zip". Avoid "The narrator", "A family".
3. UNIFIED: Describe the SHARED EVENT. Do not say "Both excerpts describe..." or "Excerpt A says X while B says Y". Just tell the story.
4. NO FLUFF: Start with the action. "The Achen family moves to Canada..." not "The story concerns a family's relocation...".

Score 0-10:
- 9-10: SAME STORY. Core event matches clearly.
- 7-8: LIKELY SAME. Key elements align.
- 0-6: DIFFERENT or unclear.

Respond with ONLY: SCORE|description
Example: 9|The Achen family takes a train from Iowa to Canada during a snowstorm."""

    response = call_llm(prompt, model=model, stream=verbose)
    if verbose:
        print()  # newline after stream
    
    # Parse response
    match = re.search(r'(\d+)\s*\|?\s*(.+)?', response)
    if match:
        score = min(10, max(0, int(match.group(1))))
        topic = match.group(2).strip() if match.group(2) else ""
        return score, topic
    
    return 0, ""


def find_story_matches(norm_windows: list[TimeWindow], tdk_windows: list[TimeWindow], 
                      model: str, verbose: bool = False) -> list[StoryMatch]:
    """Find matching stories between recordings using extracted topics."""
    
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}Finding story matches{Colors.ENDC}")
    print(f"{Colors.DIM}Comparing {len(norm_windows)} Norm windows x {len(tdk_windows)} TDK windows{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")
    
    matches = []
    
    # For each Norm window, find best matching TDK window
    for norm_idx, norm_w in enumerate(norm_windows):
        if not norm_w.topics:
            continue
            
        print(f"{Colors.CYAN}[N{norm_idx}]{Colors.ENDC} {format_time(norm_w.start_time)} - ", end="")
        print(f"{Colors.DIM}{', '.join(norm_w.topics[:2])}{Colors.ENDC}")
        
        best_score = 0
        best_tdk_idx = -1
        best_topic = ""
        
        # Score display
        scores_display = []
        
        for tdk_idx, tdk_w in enumerate(tdk_windows):
            if not tdk_w.topics:
                continue
            
            score, topic = compare_windows(norm_w, tdk_w, norm_idx, tdk_idx, model, verbose=verbose)
            
            if score >= 5:  # Only show significant scores
                scores_display.append(f"T{tdk_idx}={score}")
            
            if score > best_score:
                best_score = score
                best_tdk_idx = tdk_idx
                best_topic = topic
        
        # Print score summary
        if scores_display:
            print(f"  {Colors.DIM}Scores: {' '.join(scores_display[:10])}{Colors.ENDC}")
        
        # Record match if above threshold
        if best_score >= MATCH_THRESHOLD and best_tdk_idx >= 0:
            tdk_w = tdk_windows[best_tdk_idx]
            
            confidence = "HIGH" if best_score >= 9 else "MEDIUM" if best_score >= 7 else "LOW"
            
            match = StoryMatch(
                norm_start=norm_w.start_time,
                norm_end=norm_w.end_time,
                tdk_start=tdk_w.start_time,
                tdk_end=tdk_w.end_time,
                topic=best_topic or norm_w.summary or ', '.join(norm_w.topics[:2]),
                confidence=confidence,
                score=best_score,
                norm_text_preview=norm_w.text[:100],
                tdk_text_preview=tdk_w.text[:100]
            )
            matches.append(match)
            
            print(f"  {Colors.GREEN}[MATCH] -> T{best_tdk_idx} ({format_time(tdk_w.start_time)}) ", end="")
            print(f"score={best_score} \"{best_topic}\"{Colors.ENDC}")
        else:
            print(f"  {Colors.DIM}(no match, best={best_score}){Colors.ENDC}")
    
    return matches


def merge_adjacent_matches(matches: list[StoryMatch], gap_threshold: float = 60) -> list[StoryMatch]:
    """Merge matches that are adjacent in both recordings into story spans.
    
    Only merges if:
    1. Both Norm and TDK have small gaps
    2. TDK timestamps are progressing in the same direction
    """
    if len(matches) < 2:
        return matches
    
    # Sort by Norm start time
    matches = sorted(matches, key=lambda m: m.norm_start)
    
    merged = [matches[0]]
    
    for m in matches[1:]:
        prev = merged[-1]
        
        # Check if this match is adjacent to previous in BOTH recordings
        norm_gap = m.norm_start - prev.norm_end
        
        # Check if TDK is also progressing (allow some flexibility for overlapping windows)
        tdk_progressing = m.tdk_start >= prev.tdk_start - 30  # TDK should be at same spot or later
        tdk_close = abs(m.tdk_start - prev.tdk_end) <= gap_threshold
        
        if norm_gap <= gap_threshold and tdk_close and tdk_progressing:
            # Merge: extend the previous match
            prev.norm_end = max(prev.norm_end, m.norm_end)
            prev.tdk_end = max(prev.tdk_end, m.tdk_end)
            prev.score = max(prev.score, m.score)
            # Keep higher confidence
            if m.confidence == "HIGH":
                prev.confidence = "HIGH"
        else:
            merged.append(m)
    
    return merged


def create_alternate_tellings_json(matches: list[StoryMatch]) -> dict:
    """Create the output JSON structure."""
    
    tellings = []
    for m in matches:
        tellings.append({
            'topic': m.topic,
            'confidence': m.confidence,
            'score': m.score,
            'Norm_red': {
                'startTime': m.norm_start,
                'endTime': m.norm_end,
                'preview': m.norm_text_preview
            },
            'TDK_D60_edited_through_air': {
                'startTime': m.tdk_start,
                'endTime': m.tdk_end,
                'preview': m.tdk_text_preview
            }
        })
    
    return {
        'version': '2.0',
        'description': 'Timestamp-to-timestamp story matches between memoir recordings',
        'primaryRecording': 'Norm_red',
        'secondaryRecording': 'TDK_D60_edited_through_air',
        'matchingMethod': 'sliding_window_topic_extraction',
        'windowConfig': {
            'duration': WINDOW_DURATION,
            'overlap': WINDOW_OVERLAP
        },
        'alternateTellings': tellings,
        'stats': {
            'totalMatches': len(tellings),
            'highConfidence': sum(1 for m in matches if m.confidence == "HIGH"),
            'mediumConfidence': sum(1 for m in matches if m.confidence == "MEDIUM"),
        }
    }


def main():
    parser = argparse.ArgumentParser(
        description='Find overlapping stories between memoir recordings using topic extraction'
    )
    parser.add_argument('--dry-run', action='store_true', 
                       help='Show results without saving')
    parser.add_argument('--model', type=str, default=MODEL,
                       help=f'LLM model to use (default: {MODEL})')
    parser.add_argument('--limit', type=int, default=0,
                       help='Limit number of windows to process (for testing)')
    parser.add_argument('--verbose', action='store_true',
                       help='Stream LLM output during comparison (for debugging)')
    args = parser.parse_args()
    
    model = args.model
    verbose = args.verbose
    
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}STORY OVERLAP DETECTION v2.0{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"\nMethod: Sliding window topic extraction")
    print(f"Model: {model}")
    print(f"Window: {WINDOW_DURATION}s duration, {WINDOW_OVERLAP}s overlap")
    print(f"Match threshold: {MATCH_THRESHOLD}/10")
    if verbose:
        print(f"{Colors.YELLOW}Verbose mode: streaming LLM output{Colors.ENDC}")
    
    # Load transcripts
    print(f"\n{Colors.CYAN}Loading transcripts...{Colors.ENDC}")
    norm_transcript = load_recording_transcript('Norm_red')
    tdk_transcript = load_recording_transcript('TDK_D60_edited_through_air')
    
    if not norm_transcript or not tdk_transcript:
        print(f"{Colors.RED}Error: Could not load transcripts{Colors.ENDC}")
        return
    
    print(f"  Norm_red: {len(norm_transcript)} segments, {format_time(norm_transcript[-1]['end'])} duration")
    print(f"  TDK: {len(tdk_transcript)} segments, {format_time(tdk_transcript[-1]['end'])} duration (corrected to {format_time(TDK_CORRECTED_LIMIT)})")
    
    # Create windows
    # Note: TDK is limited to corrected portion only
    print(f"\n{Colors.CYAN}Creating time windows...{Colors.ENDC}")
    norm_windows = create_windows(norm_transcript)
    tdk_windows = create_windows(tdk_transcript, max_time=TDK_CORRECTED_LIMIT)
    
    if args.limit:
        norm_windows = norm_windows[:args.limit]
        tdk_windows = tdk_windows[:args.limit]
        print(f"  {Colors.YELLOW}(Limited to {args.limit} windows for testing){Colors.ENDC}")
    
    print(f"  Norm_red: {len(norm_windows)} windows")
    print(f"  TDK: {len(tdk_windows)} windows (up to {format_time(TDK_CORRECTED_LIMIT)})")
    
    # Extract topics from each recording
    norm_windows = extract_topics_batch(norm_windows, 'Norm_red', model)
    tdk_windows = extract_topics_batch(tdk_windows, 'TDK_D60_edited_through_air', model)
    
    # Find matches
    matches = find_story_matches(norm_windows, tdk_windows, model, verbose=verbose)
    
    # Merge adjacent matches
    print(f"\n{Colors.CYAN}Merging adjacent matches...{Colors.ENDC}")
    original_count = len(matches)
    matches = merge_adjacent_matches(matches)
    print(f"  {original_count} matches → {len(matches)} story spans")
    
    # Summary
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}RESULTS{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"\nFound {len(matches)} story matches:")
    
    for i, m in enumerate(matches):
        conf_color = Colors.GREEN if m.confidence == "HIGH" else Colors.YELLOW
        print(f"\n{i+1}. {conf_color}[{m.confidence}]{Colors.ENDC} {m.topic}")
        print(f"   Norm_red: {format_time(m.norm_start)} - {format_time(m.norm_end)}")
        print(f"   TDK:      {format_time(m.tdk_start)} - {format_time(m.tdk_end)}")
        print(f"   Score: {m.score}/10")
    
    # Save output
    if not args.dry_run:
        output = create_alternate_tellings_json(matches)
        output_path = MEMOIRS_DIR / "alternate_tellings.json"
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"\n{Colors.GREEN}Saved to: {output_path}{Colors.ENDC}")
    else:
        print(f"\n{Colors.YELLOW}(Dry run - not saved){Colors.ENDC}")
    
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print("DONE")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")


if __name__ == "__main__":
    main()
