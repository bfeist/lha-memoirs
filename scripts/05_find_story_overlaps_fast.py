#!/usr/bin/env python3
"""
Fast story overlap detection using a 3-phase approach:
1. Extract topic descriptions for each window (1 LLM call per window)
2. Use TF-IDF + cosine similarity for fast candidate matching
3. Verify top candidates with LLM comparison

This is MUCH faster than comparing every pair with LLM.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from transcript_utils import load_transcript

# === CONFIGURATION ===
SCRIPT_DIR = Path(__file__).parent
MEMOIRS_DIR = SCRIPT_DIR.parent / "public" / "recordings" / "memoirs"
OUTPUT_DIR = MEMOIRS_DIR
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gemma3:12b"

# Window settings
WINDOW_DURATION = 90
WINDOW_OVERLAP = 45
MIN_TEXT_LENGTH = 150

# TDK transcript limits
TDK_MIN_START = 115
TDK_CORRECTED_LIMIT = 10900

# Matching settings
SIMILARITY_THRESHOLD = 0.12  # TF-IDF similarity threshold for candidates (lowered from 0.15)
TOP_K_CANDIDATES = 500  # Max candidates to send to LLM verification
MATCH_THRESHOLD = 8  # LLM score threshold for final matches
PARALLEL_WORKERS = 4  # Number of parallel LLM requests


@dataclass
class Window:
    recording: str
    start: float
    end: float
    text: str
    topics: str = ""
    window_idx: int = 0


@dataclass
class Match:
    norm_start: float
    norm_end: float
    tdk_start: float
    tdk_end: float
    score: int
    norm_topics: str
    tdk_topics: str
    similarity: float = 0.0


def format_time(seconds: float) -> str:
    """Format seconds as MM:SS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def get_text_in_range(transcript: list[dict], start_time: float, end_time: float) -> str:
    """Extract all transcript text within a time range."""
    texts = []
    for seg in transcript:
        seg_start = seg.get('start', 0)
        seg_end = seg.get('end', 0)
        if seg_end >= start_time and seg_start < end_time:
            texts.append(seg.get('text', ''))
    return ' '.join(texts)


def create_windows(transcript: list[dict], recording_name: str, 
                   min_time: float = 0, max_time: float = None) -> list[Window]:
    """Create overlapping time windows from transcript."""
    if not transcript:
        return []
    
    windows = []
    total_duration = transcript[-1].get('end', 0)
    
    if max_time is not None:
        total_duration = min(total_duration, max_time)
    
    start_time = min_time
    idx = 0
    while start_time < total_duration:
        end_time = min(start_time + WINDOW_DURATION, total_duration)
        text = get_text_in_range(transcript, start_time, end_time)
        
        if text.strip() and len(text.strip()) >= MIN_TEXT_LENGTH:
            windows.append(Window(
                recording=recording_name,
                start=start_time,
                end=end_time,
                text=text.strip(),
                window_idx=idx
            ))
            idx += 1
        
        start_time += (WINDOW_DURATION - WINDOW_OVERLAP)
    
    return windows


def extract_topics_prompt(text: str) -> str:
    """Prompt for extracting topic description from a window."""
    return f"""Extract a brief topic description from this excerpt of Lindy Achen's voice memoirs.

CONTEXT: These are memoirs recorded by Linden "Lindy" Achen in the 1980s about his life
from 1902 onwards. He grew up in the Achen family with many siblings, worked as a lineman
and contractor, and lived across the upper Midwest, Saskatchewan, and Manitoba.

TRANSCRIPT:
{text}

Respond with a 2-3 sentence description covering:
- Main story/event (WHO did WHAT, WHERE, WHEN - be specific)
- Key people by name (siblings, family, coworkers)
- Key places mentioned
- Time period or dates

STYLE: Write as if describing Lindy's stories casually.
- GOOD: "Lindy worked on a power line crew near Frederick, SD in 1928..."
- GOOD: "The Achen family arrived in Canada during a heavy snowstorm..."
- BAD: "The narrator recounts..." or "This excerpt details..." (too formal)
- BAD: "A man's experiences..." (use names, we know it's Lindy)

Keep it under 100 words."""


def verify_match_prompt(text1: str, text2: str) -> str:
    """Prompt for verifying if two transcript excerpts are the same story."""
    return f"""Compare these two excerpts from Lindy Achen's memoirs.
These are from DIFFERENT recordings - Lindy often retold the same stories.
Determine if they describe the SAME specific story or event.

EXCERPT 1:
{text1}

EXCERPT 2:
{text2}

STRICT MATCHING CRITERIA:
- Same event = same specific action by the same people at the same place/time
- NOT same event: similar themes (both about "farm work") but different specific events  
- NOT same event: different time periods (e.g., 1907 vs 1924)
- NOT same event: different people or places as the focus

SCORING:
- 9-10: Clearly same specific event with matching names, places, dates
- 7-8: Same event with minor detail differences
- 4-6: Related topic but different specific stories
- 1-3: Different topics entirely

Respond with ONLY a number 1-10."""


def call_ollama(prompt: str, expect_number: bool = False) -> str:
    """Call Ollama API and return response."""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"num_ctx": 4096}
            },
            timeout=120
        )
        response.raise_for_status()
        result = response.json().get("response", "").strip()
        
        if expect_number:
            # Extract just the number
            numbers = re.findall(r'\b(\d+)\b', result)
            if numbers:
                return numbers[0]
            return "0"
        
        return result
    except Exception as e:
        print(f"  [ERROR] Ollama call failed: {e}")
        return "" if not expect_number else "0"


def phase1_extract_topics(windows: list[Window], desc: str) -> list[Window]:
    """Phase 1: Extract topic descriptions for all windows (parallel)."""
    print(f"\n{'='*60}")
    print(f"PHASE 1: Extracting topics for {len(windows)} {desc} windows")
    print(f"{'='*60}")
    
    start_time = time.time()
    completed = 0
    
    def process_window(idx: int) -> tuple[int, str]:
        w = windows[idx]
        prompt = extract_topics_prompt(w.text)
        return idx, call_ollama(prompt)
    
    with ThreadPoolExecutor(max_workers=PARALLEL_WORKERS) as executor:
        futures = {executor.submit(process_window, i): i for i in range(len(windows))}
        
        for future in as_completed(futures):
            idx, topics = future.result()
            windows[idx].topics = topics
            completed += 1
            
            if completed % 20 == 0 or completed == 1:
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 1
                remaining = (len(windows) - completed) / rate if rate > 0 else 0
                print(f"  [{completed}/{len(windows)}] "
                      f"({elapsed:.0f}s elapsed, ~{remaining:.0f}s remaining)")
    
    elapsed = time.time() - start_time
    print(f"  Completed in {elapsed:.1f}s ({elapsed/len(windows):.2f}s per window)")
    
    return windows


def phase2_fuzzy_match(norm_windows: list[Window], tdk_windows: list[Window],
                       similarity_threshold: float = SIMILARITY_THRESHOLD,
                       top_k: int = TOP_K_CANDIDATES) -> list[tuple]:
    """Phase 2: Use TF-IDF similarity to find candidate pairs."""
    print(f"\n{'='*60}")
    print(f"PHASE 2: Fast TF-IDF matching")
    print(f"{'='*60}")
    
    start_time = time.time()
    
    # Combine all topics for TF-IDF
    all_topics = [w.topics for w in norm_windows] + [w.topics for w in tdk_windows]
    
    # Create TF-IDF vectors
    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=1,
        stop_words='english'
    )
    tfidf_matrix = vectorizer.fit_transform(all_topics)
    
    # Split back into norm and tdk
    norm_vectors = tfidf_matrix[:len(norm_windows)]
    tdk_vectors = tfidf_matrix[len(norm_windows):]
    
    # Compute pairwise similarities
    similarities = cosine_similarity(norm_vectors, tdk_vectors)
    
    # Find candidates above threshold
    candidates = []
    for i in range(len(norm_windows)):
        for j in range(len(tdk_windows)):
            sim = similarities[i, j]
            if sim >= similarity_threshold:
                candidates.append((i, j, sim))
    
    # Sort by similarity and take top K
    candidates.sort(key=lambda x: x[2], reverse=True)
    candidates = candidates[:top_k]
    
    elapsed = time.time() - start_time
    print(f"  Found {len(candidates)} candidates above {similarity_threshold} threshold")
    print(f"  Completed in {elapsed:.2f}s")
    
    # Show similarity distribution
    if candidates:
        sims = [c[2] for c in candidates]
        print(f"  Similarity range: {min(sims):.3f} - {max(sims):.3f}")
    
    return candidates


def phase3_verify_matches(norm_windows: list[Window], tdk_windows: list[Window],
                          candidates: list[tuple]) -> list[Match]:
    """Phase 3: Verify candidates with LLM."""
    print(f"\n{'='*60}")
    print(f"PHASE 3: LLM verification of {len(candidates)} candidates")
    print(f"{'='*60}")
    
    start_time = time.time()
    matches = []
    
    # Track which TDK windows are already matched (greedy assignment)
    matched_tdk = set()
    
    for idx, (norm_idx, tdk_idx, sim) in enumerate(candidates):
        if tdk_idx in matched_tdk:
            continue
            
        norm_w = norm_windows[norm_idx]
        tdk_w = tdk_windows[tdk_idx]
        
        # Compare original transcript text, not topic descriptions
        prompt = verify_match_prompt(norm_w.text, tdk_w.text)
        score_str = call_ollama(prompt, expect_number=True)
        
        try:
            score = int(score_str)
        except ValueError:
            score = 0
        
        if score >= MATCH_THRESHOLD:
            matches.append(Match(
                norm_start=norm_w.start,
                norm_end=norm_w.end,
                tdk_start=tdk_w.start,
                tdk_end=tdk_w.end,
                score=score,
                norm_topics=norm_w.topics,
                tdk_topics=tdk_w.topics,
                similarity=sim
            ))
            matched_tdk.add(tdk_idx)
            print(f"  ✓ MATCH: Norm {format_time(norm_w.start)} ↔ TDK {format_time(tdk_w.start)} "
                  f"(score={score}, sim={sim:.3f})")
        
        if (idx + 1) % 50 == 0:
            elapsed = time.time() - start_time
            rate = (idx + 1) / elapsed
            remaining = (len(candidates) - idx - 1) / rate if rate > 0 else 0
            print(f"  [{idx+1}/{len(candidates)}] {len(matches)} matches so far "
                  f"({elapsed:.0f}s elapsed, ~{remaining:.0f}s remaining)")
    
    elapsed = time.time() - start_time
    print(f"  Found {len(matches)} matches in {elapsed:.1f}s")
    
    return matches


def save_results(matches: list[Match], norm_windows: list[Window], 
                 tdk_windows: list[Window], output_path: Path):
    """Save results in the expected format."""
    
    # Convert to the format expected by consolidation script
    alt_tellings = []
    for m in matches:
        alt_tellings.append({
            "norm_window": {
                "start": m.norm_start,
                "end": m.norm_end,
                "topics": m.norm_topics
            },
            "tdk_window": {
                "start": m.tdk_start,
                "end": m.tdk_end,
                "topics": m.tdk_topics
            },
            "similarity_score": m.score,
            "tfidf_similarity": m.similarity
        })
    
    output = {
        "generated_at": datetime.now().isoformat(),
        "algorithm": "fast_3phase",
        "settings": {
            "window_duration": WINDOW_DURATION,
            "window_overlap": WINDOW_OVERLAP,
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "match_threshold": MATCH_THRESHOLD,
            "model": MODEL
        },
        "stats": {
            "norm_windows": len(norm_windows),
            "tdk_windows": len(tdk_windows),
            "matches_found": len(matches)
        },
        "alt_tellings": alt_tellings
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nSaved {len(matches)} matches to {output_path}")


def save_topics_cache(norm_windows: list[Window], tdk_windows: list[Window], cache_path: Path):
    """Save extracted topics for reuse."""
    cache = {
        "norm": [{"start": w.start, "end": w.end, "topics": w.topics} for w in norm_windows],
        "tdk": [{"start": w.start, "end": w.end, "topics": w.topics} for w in tdk_windows]
    }
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2)
    print(f"Saved topics cache to {cache_path}")


def load_topics_cache(norm_windows: list[Window], tdk_windows: list[Window], 
                      cache_path: Path) -> bool:
    """Load topics from cache if available."""
    if not cache_path.exists():
        return False
    
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache = json.load(f)
        
        # Match by time windows
        norm_cache = {(w['start'], w['end']): w['topics'] for w in cache.get('norm', [])}
        tdk_cache = {(w['start'], w['end']): w['topics'] for w in cache.get('tdk', [])}
        
        loaded_norm = 0
        for w in norm_windows:
            key = (w.start, w.end)
            if key in norm_cache:
                w.topics = norm_cache[key]
                loaded_norm += 1
        
        loaded_tdk = 0
        for w in tdk_windows:
            key = (w.start, w.end)
            if key in tdk_cache:
                w.topics = tdk_cache[key]
                loaded_tdk += 1
        
        print(f"Loaded {loaded_norm}/{len(norm_windows)} Norm topics from cache")
        print(f"Loaded {loaded_tdk}/{len(tdk_windows)} TDK topics from cache")
        
        return loaded_norm == len(norm_windows) and loaded_tdk == len(tdk_windows)
    except Exception as e:
        print(f"Failed to load cache: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Fast story overlap detection")
    parser.add_argument("--limit", type=int, help="Limit windows for testing")
    parser.add_argument("--skip-cache", action="store_true", help="Skip loading topic cache")
    parser.add_argument("--phase1-only", action="store_true", help="Only run phase 1 (topic extraction)")
    parser.add_argument("--similarity", type=float, default=SIMILARITY_THRESHOLD,
                        help="TF-IDF similarity threshold")
    parser.add_argument("--top-k", type=int, default=TOP_K_CANDIDATES,
                        help="Max candidates for LLM verification")
    args = parser.parse_args()
    
    # Use local variables instead of modifying globals
    similarity_threshold = args.similarity
    top_k_candidates = args.top_k
    
    total_start = time.time()
    
    print("=" * 70)
    print("FAST STORY OVERLAP DETECTION (3-Phase Algorithm)")
    print("=" * 70)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load transcripts
    print("\nLoading transcripts...")
    norm_data = load_transcript(MEMOIRS_DIR / "Norm_red")
    tdk_data = load_transcript(MEMOIRS_DIR / "TDK_D60_edited_through_air")
    
    norm_transcript = norm_data.get('segments', [])
    tdk_transcript = tdk_data.get('segments', [])
    
    # Create windows
    print("\nCreating windows...")
    norm_windows = create_windows(norm_transcript, "Norm_red")
    tdk_windows = create_windows(tdk_transcript, "TDK_D60_edited_through_air",
                                  min_time=TDK_MIN_START, max_time=TDK_CORRECTED_LIMIT)
    
    if args.limit:
        norm_windows = norm_windows[:args.limit]
        tdk_windows = tdk_windows[:args.limit]
    
    print(f"  Norm windows: {len(norm_windows)}")
    print(f"  TDK windows: {len(tdk_windows)}")
    
    # Check for cached topics (stored next to script for faster iteration)
    cache_path = SCRIPT_DIR / "topics_cache.json"
    cache_loaded = False
    if not args.skip_cache:
        cache_loaded = load_topics_cache(norm_windows, tdk_windows, cache_path)
    
    # Phase 1: Extract topics
    if not cache_loaded:
        norm_windows = phase1_extract_topics(norm_windows, "Norm")
        tdk_windows = phase1_extract_topics(tdk_windows, "TDK")
        # Save topics cache for faster iteration
        save_topics_cache(norm_windows, tdk_windows, cache_path)
    else:
        print("\nUsing cached topics from Phase 1")
    
    if args.phase1_only:
        print("\n--phase1-only specified, stopping after topic extraction")
        return
    
    # Phase 2: Fast matching
    candidates = phase2_fuzzy_match(norm_windows, tdk_windows,
                                     similarity_threshold, top_k_candidates)
    
    if not candidates:
        print("\nNo candidates found! Try lowering --similarity threshold")
        return
    
    # Phase 3: LLM verification
    matches = phase3_verify_matches(norm_windows, tdk_windows, candidates)
    
    # Save results
    output_path = OUTPUT_DIR / "alternate_tellings.json"
    save_results(matches, norm_windows, tdk_windows, output_path)
    
    # Summary
    total_elapsed = time.time() - total_start
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total runtime: {total_elapsed:.1f}s ({total_elapsed/60:.1f} minutes)")
    print(f"Windows processed: {len(norm_windows)} Norm + {len(tdk_windows)} TDK")
    print(f"Candidates found: {len(candidates)}")
    print(f"Matches verified: {len(matches)}")
    print(f"Output saved to: {output_path}")


if __name__ == "__main__":
    main()
