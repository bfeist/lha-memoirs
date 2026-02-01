#!/usr/bin/env python3
"""
Test suite to compare gemma3:12b vs gpt-oss:20b for story overlap detection.

Tests:
1. Topic extraction from transcript windows
2. Window comparison (same story detection)

Saves results to temp files for comparison.
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime
import ollama

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))
from transcript_utils import load_transcript

BASE_DIR = SCRIPT_DIR.parent
MEMOIRS_DIR = BASE_DIR / "public" / "recordings" / "memoirs"
OUTPUT_DIR = SCRIPT_DIR / "model_test_output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Test windows - manually selected pairs that SHOULD match and pairs that SHOULD NOT
# Based on known matching stories found via keyword search
# Format: (norm_start, norm_end, tdk_start, tdk_end, expected_match, description)
TEST_PAIRS = [
    # SHOULD MATCH - "Daylight in the swamp" story (thrashing work, sleeping on floor)
    # Norm: 3060-3210 (51:00-53:30), TDK: 3030-3180 (50:30-53:00)
    (3060, 3210, 3030, 3180, True, "Daylight in swamp - thrashing/sleeping story"),
    
    # SHOULD MATCH - "all the glass" car accident story
    # Norm: 3180-3300 (53:00-55:00), TDK: 3200-3350 (53:20-55:50)
    (3180, 3300, 3200, 3350, True, "Car accident - rolled Model T, broke all glass"),
    
    # SHOULD MATCH - Family move from Iowa to Canada (early in both)
    (60, 180, 210, 330, True, "Family move from Iowa to Canada"),
    
    # SHOULD NOT MATCH - Totally different topics
    # Norm 2400-2520 (40:00-42:00) is about digging holes for wages
    # TDK 600-720 (10:00-12:00) is about early childhood/school
    (2400, 2520, 600, 720, False, "Norm digging holes vs TDK childhood"),
    
    # SHOULD NOT MATCH - Completely different time periods
    (6000, 6120, 600, 720, False, "Late Norm (1940s work) vs early TDK (childhood)"),
    
    # SHOULD NOT MATCH - Different stories at similar timestamps
    (1800, 1920, 1800, 1920, False, "Same timestamp but different stories"),
]

# Window configuration options to test
WINDOW_CONFIGS = [
    (60, 30),   # Original: 60s windows, 30s overlap
    (90, 45),   # Larger: 90s windows, 45s overlap
    (120, 60),  # Even larger: 120s windows, 60s overlap
]


def call_llm(prompt: str, model: str) -> str:
    """Call LLM via Ollama."""
    try:
        response = ollama.chat(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            options={"num_ctx": 16384},  # Larger context for gpt-oss
            keep_alive="10m",
        )
        return response.get('message', {}).get('content', '').strip()
    except Exception as e:
        return f"ERROR: {e}"


def load_transcripts():
    """Load both transcripts."""
    norm_dir = MEMOIRS_DIR / "Norm_red"
    tdk_dir = MEMOIRS_DIR / "TDK_D60_edited_through_air"
    
    norm_data = load_transcript(norm_dir)
    tdk_data = load_transcript(tdk_dir)
    
    return norm_data.get('segments', []), tdk_data.get('segments', [])


def get_text_in_range(transcript: list[dict], start_time: float, end_time: float) -> str:
    """Extract all transcript text within a time range."""
    texts = []
    for seg in transcript:
        seg_start = seg.get('start', 0)
        seg_end = seg.get('end', 0)
        if seg_end >= start_time and seg_start < end_time:
            texts.append(seg.get('text', ''))
    return ' '.join(texts)


def format_time(seconds: float) -> str:
    """Format seconds as MM:SS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


# =============================================================================
# TEST 1: Topic Extraction
# =============================================================================

def test_topic_extraction(model: str, norm_transcript: list, tdk_transcript: list) -> dict:
    """Test topic extraction on sample windows."""
    
    results = {"model": model, "tests": []}
    
    # Sample windows to test
    test_windows = [
        ("Norm_red", 60, 120),    # Iowa to Canada move
        ("Norm_red", 2040, 2100), # Dad's death
        ("Norm_red", 3510, 3570), # Martin Twight separator
        ("TDK", 210, 300),        # Iowa to Canada (TDK version)
        ("TDK", 1710, 1800),      # Dad's funeral (TDK version)
        ("TDK", 3030, 3090),      # Martin Twight (TDK version)
    ]
    
    for recording, start, end in test_windows:
        transcript = norm_transcript if recording == "Norm_red" else tdk_transcript
        text = get_text_in_range(transcript, start, end)
        
        prompt = f"""/no_think
Extract STORY ELEMENTS from this memoir transcript window. This is from Linden "Lindy" Achen, recorded in the 1980s about his life from 1902 onwards.

[{recording} {format_time(start)}-{format_time(end)}]:
{text}

Extract:
1. topics: 3-5 story elements capturing WHO did WHAT, WHERE, WHEN
   Focus on: the core event/action, rough time period, key people involved
   Style: Specific but casual. "Lindy gets a job", not "Lindy secures employment".
2. entities: ALL specific names, places, years mentioned
3. summary: One sentence describing THE STORY being told.

Return ONLY valid JSON:
{{"topics": ["..."], "entities": ["..."], "summary": "..."}}"""

        print(f"  Testing topic extraction: {recording} {format_time(start)}-{format_time(end)}...")
        response = call_llm(prompt, model)
        
        # Try to parse JSON
        parsed = None
        try:
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
        except:
            pass
        
        results["tests"].append({
            "recording": recording,
            "time_range": f"{format_time(start)}-{format_time(end)}",
            "text_preview": text[:200] + "...",
            "raw_response": response,
            "parsed": parsed,
            "success": parsed is not None
        })
    
    return results


# =============================================================================
# TEST 2: Window Comparison (Story Matching)
# =============================================================================

COMPARISON_PROMPT_V1 = """Do these two memoir excerpts describe the SAME story/event?

Both are from Lindy Achen telling his life story in two separate recordings.

EXCERPT A ({time_a}):
{text_a}

EXCERPT B ({time_b}):
{text_b}

Score 0-10:
- 9-10: Clearly the SAME story/event
- 7-8: Likely the same, key elements match
- 0-6: Different stories or unclear

Respond ONLY: SCORE|description
Example: 9|Lindy describes the family's train journey from Iowa to Canada."""

COMPARISON_PROMPT_V2 = """COMPARE these two memoir excerpts. Determine if they describe the EXACT SAME specific event/story.

Context: Lindy Achen telling his life story in two different recording sessions.

EXCERPT A ({time_a}):
{text_a}

EXCERPT B ({time_b}):
{text_b}

CRITERIA:
1. SHARED FACTS: Do they mention the same people, places, or specific numbers/dates?
2. SAME EVENT: Is it the same specific incident (e.g. "breaking a leg in 1912") vs just same topic (e.g. "farming is hard")?
3. CONTRADICTIONS: Are the details compatible?

SCORING (0-10):
- 0-4: Different events entirely.
- 5-6: Similar general topics but different specific events.
- 7-8: Plausible match with some shared details.
- 9-10: DEFINITE match. Shared proper nouns (names/places) AND same action sequence.

Respond: SCORE | one-sentence summary if score >= 7
Example: 9 | Lindy describes the family's train journey from Iowa to Canada."""

COMPARISON_PROMPT_V3 = """You are comparing two memoir excerpts to determine if they describe the SAME SPECIFIC EVENT.

EXCERPT A (Norm_red recording, {time_a}):
{text_a}

EXCERPT B (TDK recording, {time_b}):
{text_b}

ANALYSIS REQUIRED:
1. List proper nouns in A: (names, places, years)
2. List proper nouns in B: (names, places, years)
3. Overlapping proper nouns: (list any shared)
4. Core event in A: (one sentence)
5. Core event in B: (one sentence)
6. Same event? (yes/no/maybe)

SCORE (0-10):
- 0-4: No shared proper nouns OR clearly different events
- 5-6: Some overlap but different specific events
- 7-8: Same event with some variation
- 9-10: Clearly same event with multiple shared details

Format your response EXACTLY as:
SCORE: [number]
SUMMARY: [one sentence if score >= 7, otherwise "different events"]"""

COMPARISON_PROMPT_V4 = """Compare these two memoir excerpts. Both are from Lindy Achen recounting his life in separate recordings.

EXCERPT A ({time_a}):
{text_a}

EXCERPT B ({time_b}):
{text_b}

KEY QUESTION: Are these the SAME STORY told twice, or DIFFERENT STORIES?

Think about:
- Do they describe the same job, trip, farm, or life event?
- Even if told with different words or details, is it the same memory?
- Shared elements: similar wages ($12/day, 35c/hour), same places (Iowa, Canada), same people

SCORE 0-10:
- 0-3: Completely different stories
- 4-5: Same general life period but different specific events  
- 6-7: Probably the same story, recognizable overlap
- 8-10: Definitely the same story/memory being retold

Output format:
SCORE: [0-10]
REASON: [brief explanation]
SUMMARY: [one sentence describing the shared story if score >= 6]"""


def test_window_comparison(model: str, norm_transcript: list, tdk_transcript: list, 
                           prompt_version: int = 2) -> dict:
    """Test window comparison on known pairs."""
    
    prompt_templates = {
        1: COMPARISON_PROMPT_V1,
        2: COMPARISON_PROMPT_V2,
        3: COMPARISON_PROMPT_V3,
        4: COMPARISON_PROMPT_V4,
    }
    prompt_template = prompt_templates[prompt_version]
    
    results = {"model": model, "prompt_version": prompt_version, "tests": []}
    
    for norm_start, norm_end, tdk_start, tdk_end, expected, description in TEST_PAIRS:
        norm_text = get_text_in_range(norm_transcript, norm_start, norm_end)
        tdk_text = get_text_in_range(tdk_transcript, tdk_start, tdk_end)
        
        prompt = prompt_template.format(
            time_a=format_time(norm_start),
            text_a=norm_text,
            time_b=format_time(tdk_start),
            text_b=tdk_text
        )
        
        # Add /no_think for gemma3
        if "gemma" in model:
            prompt = "/no_think\n" + prompt
        
        print(f"  Testing comparison: {description}...")
        response = call_llm(prompt, model)
        
        # Parse score from response
        score = None
        summary = ""
        
        # Try different parsing patterns
        match = re.search(r'SCORE[:\s]*(\d+)', response, re.IGNORECASE)
        if match:
            score = int(match.group(1))
            sum_match = re.search(r'SUMMARY[:\s]*(.+?)(?:\n|$)', response, re.IGNORECASE)
            if sum_match:
                summary = sum_match.group(1).strip()
        else:
            # Try simple pattern
            match = re.search(r'^(\d+)\s*[|\-]\s*(.+)?', response, re.MULTILINE)
            if match:
                score = int(match.group(1))
                summary = match.group(2).strip() if match.group(2) else ""
        
        # Determine if correct
        predicted_match = score >= 7 if score is not None else None
        correct = None
        if expected is not None and predicted_match is not None:
            correct = predicted_match == expected
        
        results["tests"].append({
            "description": description,
            "norm_time": f"{format_time(norm_start)}-{format_time(norm_end)}",
            "tdk_time": f"{format_time(tdk_start)}-{format_time(tdk_end)}",
            "expected_match": expected,
            "predicted_score": score,
            "predicted_match": predicted_match,
            "correct": correct,
            "summary": summary,
            "raw_response": response[:500],
        })
    
    return results


def print_comparison_results(results: dict):
    """Pretty print comparison results."""
    print(f"\n{'='*60}")
    print(f"Model: {results['model']} | Prompt V{results.get('prompt_version', '?')}")
    print(f"{'='*60}")
    
    correct = 0
    total = 0
    
    for test in results["tests"]:
        exp = test["expected_match"]
        pred = test["predicted_match"]
        score = test["predicted_score"]
        
        if exp is not None:
            total += 1
            if test["correct"]:
                correct += 1
                status = "✓"
            else:
                status = "✗"
        else:
            status = "?"
        
        exp_str = "MATCH" if exp else ("NO MATCH" if exp is False else "AMBIG")
        pred_str = f"score={score}" if score is not None else "PARSE_FAIL"
        
        print(f"  [{status}] {test['description'][:40]:<40} | Expected: {exp_str:<8} | {pred_str}")
    
    if total > 0:
        print(f"\nAccuracy: {correct}/{total} ({100*correct/total:.0f}%)")


def run_all_tests(model: str):
    """Run all tests for a model and save results."""
    print(f"\n{'#'*60}")
    print(f"# TESTING MODEL: {model}")
    print(f"{'#'*60}")
    
    print("\nLoading transcripts...")
    norm_transcript, tdk_transcript = load_transcripts()
    print(f"  Norm: {len(norm_transcript)} segments")
    print(f"  TDK: {len(tdk_transcript)} segments")
    
    all_results = {"model": model, "timestamp": datetime.now().isoformat()}
    
    # Test 1: Topic extraction
    print("\n--- TEST 1: Topic Extraction ---")
    topic_results = test_topic_extraction(model, norm_transcript, tdk_transcript)
    all_results["topic_extraction"] = topic_results
    
    successes = sum(1 for t in topic_results["tests"] if t["success"])
    print(f"\nTopic extraction: {successes}/{len(topic_results['tests'])} parsed successfully")
    
    # Test 2: Window comparison with different prompt versions
    for prompt_v in [3, 4]:
        print(f"\n--- TEST 2: Window Comparison (Prompt V{prompt_v}) ---")
        comparison_results = test_window_comparison(
            model, norm_transcript, tdk_transcript, prompt_version=prompt_v
        )
        all_results[f"comparison_v{prompt_v}"] = comparison_results
        print_comparison_results(comparison_results)
    
    # Save results
    safe_model_name = model.replace(":", "_").replace("/", "_")
    output_file = OUTPUT_DIR / f"test_results_{safe_model_name}.json"
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to: {output_file}")
    
    return all_results


def compare_models():
    """Compare results from both models."""
    gemma_file = OUTPUT_DIR / "test_results_gemma3_12b.json"
    gptoss_file = OUTPUT_DIR / "test_results_gpt-oss_20b.json"
    
    if not gemma_file.exists() or not gptoss_file.exists():
        print("Run tests for both models first!")
        return
    
    with open(gemma_file) as f:
        gemma = json.load(f)
    with open(gptoss_file) as f:
        gptoss = json.load(f)
    
    print("\n" + "="*60)
    print("MODEL COMPARISON SUMMARY")
    print("="*60)
    
    for prompt_v in [3, 4]:
        key = f"comparison_v{prompt_v}"
        print(f"\n--- Prompt V{prompt_v} ---")
        
        for model_name, results in [("gemma3:12b", gemma), ("gpt-oss:20b", gptoss)]:
            if key not in results:
                continue
            comp = results[key]
            correct = sum(1 for t in comp["tests"] if t.get("correct") is True)
            total = sum(1 for t in comp["tests"] if t.get("expected_match") is not None)
            print(f"  {model_name}: {correct}/{total} correct")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, default="gemma3:12b",
                       help="Model to test (gemma3:12b or gpt-oss:20b)")
    parser.add_argument("--compare", action="store_true",
                       help="Compare results from both models")
    parser.add_argument("--all", action="store_true",
                       help="Run tests for both models sequentially")
    args = parser.parse_args()
    
    if args.compare:
        compare_models()
    elif args.all:
        # Run gemma first (likely already loaded)
        run_all_tests("gemma3:12b")
        # Then gpt-oss
        run_all_tests("gpt-oss:20b")
        # Compare
        compare_models()
    else:
        run_all_tests(args.model)
