#!/usr/bin/env python3
"""
Find overlapping stories between memoir recordings using Gemma.

This analyzes the actual transcript text within chapters to identify:
1. Stories that appear in both recordings (different tellings)
2. The start times for each matched story in both recordings
3. Cross-references for the UI

Output: alternate_tellings.json with time-based references.
"""

import json
import subprocess
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
MEMOIRS_DIR = BASE_DIR / "public" / "recordings" / "memoirs"


def call_gemma(prompt: str, model: str = "gemma3:12b") -> str:
    """Call Gemma via Ollama and return the response."""
    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min timeout for deeper analysis
            encoding='utf-8'
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        return "ERROR: Timeout"
    except Exception as e:
        return f"ERROR: {e}"


def load_chapters(recording_name: str) -> list[dict]:
    """Load chapters from a recording."""
    path = MEMOIRS_DIR / recording_name / "chapters.json"
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('chapters', [])


def load_transcript(recording_name: str) -> list[dict]:
    """Load transcript segments from a recording."""
    path = MEMOIRS_DIR / recording_name / "transcript.json"
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('segments', [])


def get_chapter_text(transcript: list[dict], start_time: float, end_time: float, max_words: int = 300) -> str:
    """Extract transcript text for a chapter's time range."""
    words = []
    for segment in transcript:
        seg_start = segment.get('start', 0)
        seg_end = segment.get('end', 0)
        
        # Include segment if it overlaps with chapter time range
        if seg_end >= start_time and seg_start < end_time:
            words.extend(segment.get('text', '').split())
            if len(words) >= max_words:
                break
    
    return ' '.join(words[:max_words])


def format_chapters_for_analysis(recording_name: str, chapters: list[dict], transcript: list[dict]) -> str:
    """Format chapters with actual transcript excerpts for Gemma analysis."""
    lines = [f"=== {recording_name} ==="]
    
    for i, ch in enumerate(chapters):
        title = ch.get('title', 'Untitled')
        time = ch.get('startTime', 0)
        
        # Get end time (next chapter start or end of transcript)
        if i + 1 < len(chapters):
            end_time = chapters[i + 1].get('startTime')
        else:
            end_time = transcript[-1].get('end', time + 600) if transcript else time + 600
        
        # Extract transcript text
        text = get_chapter_text(transcript, time, end_time, max_words=200)
        
        mins = int(time // 60)
        secs = int(time % 60)
        
        lines.append(f"\n[{i}] {title} (starts at {mins}:{secs:02d})")
        lines.append(f"Text: {text}...")
    
    return "\n".join(lines)


def find_story_overlaps(recordings: list[str]) -> dict:
    """Use Gemma to find overlapping stories between recordings by analyzing actual transcript text."""
    
    print("Loading chapters and transcripts...")
    all_chapters = {}
    all_transcripts = {}
    formatted = []
    
    for rec in recordings:
        chapters = load_chapters(rec)
        transcript = load_transcript(rec)
        all_chapters[rec] = chapters
        all_transcripts[rec] = transcript
        formatted.append(format_chapters_for_analysis(rec, chapters, transcript))
        print(f"  {rec}: {len(chapters)} chapters, {len(transcript)} transcript segments")
    
    chapters_text = "\n\n".join(formatted)
    
    prompt = f"""You are analyzing two audio memoir recordings from the same person, Linden "Lindy" Achen. 
He recorded his life story on two different occasions (TDK was recorded earlier, Norm_red later). 
Some stories appear in BOTH recordings (told differently), while other stories are unique to one recording.

Your task: Identify which chapters tell the SAME STORY in both recordings by analyzing the actual spoken text.

IMPORTANT: Focus on the TEXT content, not just chapter titles. Match stories where:
- The same event or time period is being described
- The same people or places are mentioned
- Similar narrative elements appear
- Even if told with different details or emphasis

When describing topics, refer to Lindy by name (e.g., "Lindy's work experience" not "narrator's work experience").

CHAPTERS AND TEXT FROM BOTH RECORDINGS:
{chapters_text}

INSTRUCTIONS:
1. Compare the actual transcript text, not just titles
2. Look for matching stories about same events, people, time periods
3. Be thorough - analyze all chapters carefully
4. A story might be shorter or longer in one recording vs the other

For EACH match you find, respond in exactly this format:
MATCH: [Norm_red chapter index] <-> [TDK chapter index]
TOPIC: Brief description of the shared story/event
CONFIDENCE: HIGH/MEDIUM/LOW

Then provide a brief summary of how many overlaps you found.

Be thorough and careful - this is important for helping users navigate between recordings."""

    print("\nAnalyzing with Gemma (this will take several minutes)...")
    print("(Analyzing actual transcript text for each chapter)")
    response = call_gemma(prompt)
    
    print("\n" + "=" * 60)
    print("GEMMA ANALYSIS")
    print("=" * 60)
    print(response)
    
    return {
        'recordings': recordings,
        'chapters': all_chapters,
        'transcripts': all_transcripts,
        'analysis': response
    }


def parse_matches(response: str) -> list[dict]:
    """Parse Gemma's response to extract matches."""
    matches = []
    
    # Pattern 1: **MATCH: [Norm_X] <-> [TDK_Y]** (with ** bold markers)
    pattern1 = re.compile(
        r'\*\*MATCH:\s*\[(?:Norm[_\s]?red[_\s]?)?(\d+)\]\s*<->\s*\[(?:TDK[^\]]*?)?(\d+)\]\*\*.*?'
        r'TOPIC:\s*([^\n]+?)(?:\n|CONFIDENCE)',
        re.IGNORECASE | re.DOTALL
    )
    
    # Pattern 2: MATCH: [Norm_red X] <-> [TDK Y] (without bold)
    pattern2 = re.compile(
        r'MATCH:\s*\[(?:Norm[_\s]?red[_\s]?)?(\d+)\]\s*<->\s*\[(?:TDK[^\]]*?)?(\d+)\].*?'
        r'TOPIC:\s*([^\n]+?)(?:\n|CONFIDENCE)',
        re.IGNORECASE | re.DOTALL
    )
    
    # Try pattern 1 first (more specific, with bold markers)
    for match in pattern1.finditer(response):
        matches.append({
            'norm_red_chapter': int(match.group(1)),
            'tdk_chapter': int(match.group(2)),
            'topic': match.group(3).strip(),
            'confidence': 'HIGH'  # Default, we'll try to parse it separately
        })
    
    # If no matches with pattern 1, try pattern 2
    if not matches:
        for match in pattern2.finditer(response):
            matches.append({
                'norm_red_chapter': int(match.group(1)),
                'tdk_chapter': int(match.group(2)),
                'topic': match.group(3).strip(),
                'confidence': 'HIGH'  # Default
            })
    
    # Now try to extract confidence levels for each match
    confidence_pattern = re.compile(r'CONFIDENCE:\s*(HIGH|MEDIUM|LOW)', re.IGNORECASE)
    confidence_matches = confidence_pattern.findall(response)
    
    for i, conf in enumerate(confidence_matches):
        if i < len(matches):
            matches[i]['confidence'] = conf.upper()
    
    return matches


def create_alternate_tellings_json(
    recordings: list[str],
    chapters: dict,
    matches: list[dict]
) -> dict:
    """Create alternate_tellings.json with proper time references."""
    
    primary = 'Norm_red'
    secondary = 'TDK_D60_edited_through_air'
    
    alternate_tellings = []
    
    for m in matches:
        norm_idx = m['norm_red_chapter']
        tdk_idx = m['tdk_chapter']
        
        # Validate indices
        if norm_idx >= len(chapters[primary]):
            print(f"  WARNING: Invalid Norm_red chapter index {norm_idx}, skipping")
            continue
        if tdk_idx >= len(chapters[secondary]):
            print(f"  WARNING: Invalid TDK chapter index {tdk_idx}, skipping")
            continue
        
        norm_chapter = chapters[primary][norm_idx]
        tdk_chapter = chapters[secondary][tdk_idx]
        
        alternate_tellings.append({
            'topic': m['topic'],
            'confidence': m['confidence'],
            'Norm_red': {
                'startTime': norm_chapter.get('startTime'),
                'title': norm_chapter.get('title')
            },
            'TDK_D60_edited_through_air': {
                'startTime': tdk_chapter.get('startTime'),
                'title': tdk_chapter.get('title')
            }
        })
    
    return {
        'primaryRecording': primary,
        'secondaryRecording': secondary,
        'description': 'Cross-references between overlapping stories in both memoir recordings',
        'alternateTellings': alternate_tellings,
        'stats': {
            'totalMatches': len(alternate_tellings),
            'primaryChapterCount': len(chapters[primary]),
            'secondaryChapterCount': len(chapters[secondary])
        }
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Find overlapping stories between memoir recordings using transcript analysis'
    )
    parser.add_argument(
        '--save',
        action='store_true',
        help='Save results to alternate_tellings.json file'
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("MEMOIR STORY OVERLAP ANALYSIS (DEEP TRANSCRIPT ANALYSIS)")
    print("=" * 60)
    print("\nNarrator: Linden 'Lindy' Achen")
    print("Recordings: Norm_red (later), TDK_D60_edited_through_air (earlier)")
    print("\nThis will analyze the actual spoken text within each chapter")
    print("to find matching stories between recordings.")
    
    recordings = ['Norm_red', 'TDK_D60_edited_through_air']
    
    # Analyze with Gemma
    result = find_story_overlaps(recordings)
    
    # Parse matches
    matches = parse_matches(result['analysis'])
    
    print(f"\n\nParsed {len(matches)} story matches")
    
    if matches:
        print("\nMatched Stories:")
        for m in matches:
            # Validate indices before accessing
            if m['norm_red_chapter'] >= len(result['chapters']['Norm_red']):
                print(f"  WARNING: Invalid Norm_red index {m['norm_red_chapter']}, skipping")
                continue
            if m['tdk_chapter'] >= len(result['chapters']['TDK_D60_edited_through_air']):
                print(f"  WARNING: Invalid TDK index {m['tdk_chapter']}, skipping")
                continue
                
            norm_ch = result['chapters']['Norm_red'][m['norm_red_chapter']]
            tdk_ch = result['chapters']['TDK_D60_edited_through_air'][m['tdk_chapter']]
            print(f"  [{m['norm_red_chapter']}] {norm_ch['title']} (Norm @ {norm_ch['startTime']:.0f}s)")
            print(f"  [{m['tdk_chapter']}] {tdk_ch['title']} (TDK @ {tdk_ch['startTime']:.0f}s)")
            print(f"    Topic: {m['topic']}")
            print(f"    Confidence: {m['confidence']}")
            print()
    
    if args.save:
        # Create alternate_tellings.json
        output = create_alternate_tellings_json(
            recordings,
            result['chapters'],
            matches
        )
        
        output_path = MEMOIRS_DIR / "alternate_tellings.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"\nAlternate tellings saved to: {output_path}")
        print(f"Total matches: {len(output['alternateTellings'])}")
    
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
