#!/usr/bin/env python3
"""
Consolidate duplicate alternate tellings into unique story matches.

Problem: The sliding window approach creates multiple matches when adjacent 
Norm windows all match the same TDK window. This results in duplicate entries
for the same story.

Solution: 
1. Group entries by overlapping TDK time ranges (but don't chain too far)
2. Within each group, merge overlapping Norm time ranges  
3. Keep the highest score and best topic for each consolidated entry
4. Optionally filter out likely false positives (low score + large time gap)

This is a fast post-processing step that doesn't require re-running LLM comparisons.
"""

import json
import argparse
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# Paths
SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
MEMOIRS_DIR = BASE_DIR / "public" / "recordings" / "memoirs"

# How much overlap (in seconds) counts as "same story"
# Use exact TDK match rather than overlap to avoid chaining
TDK_EXACT_MATCH = False  # Use overlapping TDK matching for better consolidation
TDK_OVERLAP_THRESHOLD = 45  # TDK ranges must overlap by at least 45 seconds

# How close Norm ranges need to be to merge
NORM_GAP_THRESHOLD = 60  # seconds

# Filter settings for likely false positives
# If time difference > threshold AND score < score_threshold, filter it out
FILTER_TIME_DIFF_THRESHOLD = 1800  # 30 minutes
FILTER_MIN_SCORE = 8  # Entries with score < 8 and time diff > 30min are filtered


@dataclass
class StoryEntry:
    """A single alternate telling entry."""
    topic: str
    confidence: str
    score: float
    norm_start: float
    norm_end: float
    tdk_start: float
    tdk_end: float
    norm_preview: str
    tdk_preview: str


def load_alternate_tellings() -> tuple[dict, list[StoryEntry]]:
    """Load the alternate_tellings.json file."""
    path = MEMOIRS_DIR / "alternate_tellings.json"
    with open(path) as f:
        data = json.load(f)
    
    entries = []
    for t in data.get('alternateTellings', []):
        entries.append(StoryEntry(
            topic=t['topic'],
            confidence=t['confidence'],
            score=t['score'],
            norm_start=t['Norm_red']['startTime'],
            norm_end=t['Norm_red']['endTime'],
            tdk_start=t['TDK_D60_edited_through_air']['startTime'],
            tdk_end=t['TDK_D60_edited_through_air']['endTime'],
            norm_preview=t['Norm_red']['preview'],
            tdk_preview=t['TDK_D60_edited_through_air']['preview'],
        ))
    
    return data, entries


def ranges_overlap(start1: float, end1: float, start2: float, end2: float, threshold: float = 0) -> bool:
    """Check if two time ranges overlap by at least threshold seconds."""
    overlap_start = max(start1, start2)
    overlap_end = min(end1, end2)
    overlap = overlap_end - overlap_start
    return overlap >= threshold


def filter_false_positives(entries: list[StoryEntry], filter_enabled: bool = True) -> tuple[list[StoryEntry], list[StoryEntry]]:
    """Filter out likely false positives based on time difference and score.
    
    Legitimate alternate tellings: same story told at different points
    False positives: coincidental keyword matches for different stories
    
    Heuristic: If Norm and TDK times differ by >30min AND score < 8, likely false positive.
    """
    if not filter_enabled:
        return entries, []
    
    kept = []
    filtered = []
    
    for e in entries:
        norm_mid = (e.norm_start + e.norm_end) / 2
        tdk_mid = (e.tdk_start + e.tdk_end) / 2
        time_diff = abs(norm_mid - tdk_mid)
        
        if time_diff > FILTER_TIME_DIFF_THRESHOLD and e.score < FILTER_MIN_SCORE:
            filtered.append(e)
        else:
            kept.append(e)
    
    return kept, filtered


def group_by_tdk_exact(entries: list[StoryEntry]) -> list[list[StoryEntry]]:
    """Group entries by exact TDK time range match."""
    from collections import defaultdict
    
    by_tdk = defaultdict(list)
    for e in entries:
        key = (e.tdk_start, e.tdk_end)
        by_tdk[key].append(e)
    
    return list(by_tdk.values())


def group_by_tdk_overlap(entries: list[StoryEntry]) -> list[list[StoryEntry]]:
    """Group entries that have overlapping TDK time ranges.
    
    Note: This can chain together entries that don't directly overlap,
    so we use a more conservative approach with exact matching by default.
    """
    if TDK_EXACT_MATCH:
        return group_by_tdk_exact(entries)
    
    if not entries:
        return []
    
    # Sort by TDK start time
    sorted_entries = sorted(entries, key=lambda e: e.tdk_start)
    
    groups = []
    current_group = [sorted_entries[0]]
    current_tdk_end = sorted_entries[0].tdk_end
    
    for entry in sorted_entries[1:]:
        # Check if this entry overlaps with the current group's TDK range
        # Use a small threshold to only merge truly overlapping ranges
        overlap_threshold = 30  # seconds
        if ranges_overlap(entry.tdk_start, entry.tdk_end, 
                         current_group[0].tdk_start, current_tdk_end,
                         threshold=overlap_threshold):
            current_group.append(entry)
            current_tdk_end = max(current_tdk_end, entry.tdk_end)
        else:
            groups.append(current_group)
            current_group = [entry]
            current_tdk_end = entry.tdk_end
    
    groups.append(current_group)
    return groups


def merge_norm_ranges(entries: list[StoryEntry]) -> list[tuple[float, float, list[StoryEntry]]]:
    """Within a group, merge entries with overlapping/adjacent Norm ranges.
    
    Returns list of (norm_start, norm_end, entries_in_range).
    """
    if not entries:
        return []
    
    # Sort by Norm start time
    sorted_entries = sorted(entries, key=lambda e: e.norm_start)
    
    merged = []
    current_start = sorted_entries[0].norm_start
    current_end = sorted_entries[0].norm_end
    current_entries = [sorted_entries[0]]
    
    for entry in sorted_entries[1:]:
        # Check if this entry is close enough to merge
        if entry.norm_start <= current_end + NORM_GAP_THRESHOLD:
            current_end = max(current_end, entry.norm_end)
            current_entries.append(entry)
        else:
            merged.append((current_start, current_end, current_entries))
            current_start = entry.norm_start
            current_end = entry.norm_end
            current_entries = [entry]
    
    merged.append((current_start, current_end, current_entries))
    return merged


def consolidate_group(group: list[StoryEntry]) -> list[StoryEntry]:
    """Consolidate a group of entries with overlapping TDK ranges.
    
    Strategy:
    1. Merge overlapping Norm ranges
    2. For each merged range, pick the best topic (highest score)
    3. Combine TDK ranges
    """
    if len(group) == 1:
        return group
    
    # Merge by Norm ranges
    norm_ranges = merge_norm_ranges(group)
    
    consolidated = []
    for norm_start, norm_end, entries in norm_ranges:
        # Pick the entry with highest score as the representative
        best = max(entries, key=lambda e: e.score)
        
        # Compute combined TDK range
        tdk_start = min(e.tdk_start for e in entries)
        tdk_end = max(e.tdk_end for e in entries)
        
        # Update confidence based on best score
        if best.score >= 9:
            confidence = "HIGH"
        elif best.score >= 7:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        
        consolidated.append(StoryEntry(
            topic=best.topic,
            confidence=confidence,
            score=best.score,
            norm_start=norm_start,
            norm_end=norm_end,
            tdk_start=tdk_start,
            tdk_end=tdk_end,
            norm_preview=best.norm_preview,
            tdk_preview=best.tdk_preview,
        ))
    
    return consolidated


def consolidate_all(entries: list[StoryEntry]) -> list[StoryEntry]:
    """Consolidate all entries by grouping and merging."""
    # Group by overlapping TDK ranges
    groups = group_by_tdk_overlap(entries)
    
    # Consolidate each group
    consolidated = []
    for group in groups:
        consolidated.extend(consolidate_group(group))
    
    # Sort by Norm start time for final output
    consolidated.sort(key=lambda e: e.norm_start)
    
    return consolidated


def format_time(seconds: float) -> str:
    """Format seconds as MM:SS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def create_output_json(original_data: dict, consolidated: list[StoryEntry]) -> dict:
    """Create the output JSON structure."""
    tellings = []
    for e in consolidated:
        tellings.append({
            'topic': e.topic,
            'confidence': e.confidence,
            'score': e.score,
            'Norm_red': {
                'startTime': e.norm_start,
                'endTime': e.norm_end,
                'preview': e.norm_preview
            },
            'TDK_D60_edited_through_air': {
                'startTime': e.tdk_start,
                'endTime': e.tdk_end,
                'preview': e.tdk_preview
            }
        })
    
    # Build output with updated stats
    output = {
        'version': '2.1',
        'description': 'Consolidated timestamp-to-timestamp story matches between memoir recordings',
        'primaryRecording': original_data.get('primaryRecording', 'Norm_red'),
        'secondaryRecording': original_data.get('secondaryRecording', 'TDK_D60_edited_through_air'),
        'matchingMethod': 'sliding_window_topic_extraction_consolidated',
        'windowConfig': original_data.get('windowConfig', {}),
        'consolidationConfig': {
            'tdk_exact_match': TDK_EXACT_MATCH,
            'norm_gap_threshold': NORM_GAP_THRESHOLD,
            'filter_time_diff_threshold': FILTER_TIME_DIFF_THRESHOLD,
            'filter_min_score': FILTER_MIN_SCORE,
        },
        'alternateTellings': tellings,
        'stats': {
            'totalMatches': len(tellings),
            'highConfidence': sum(1 for e in consolidated if e.confidence == "HIGH"),
            'mediumConfidence': sum(1 for e in consolidated if e.confidence == "MEDIUM"),
            'originalCount': original_data.get('stats', {}).get('totalMatches', 0),
        }
    }
    
    return output


def main():
    parser = argparse.ArgumentParser(
        description='Consolidate duplicate alternate tellings'
    )
    parser.add_argument('--dry-run', action='store_true',
                       help='Show results without saving')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show detailed consolidation info')
    parser.add_argument('--no-filter', action='store_true',
                       help='Disable false positive filtering')
    args = parser.parse_args()
    
    print("=" * 60)
    print("ALTERNATE TELLINGS CONSOLIDATION")
    print("=" * 60)
    
    # Load data
    print("\nLoading alternate_tellings.json...")
    original_data, entries = load_alternate_tellings()
    print(f"  Loaded {len(entries)} entries")
    
    # Filter false positives
    filter_enabled = not args.no_filter
    print(f"\nFiltering likely false positives (enabled={filter_enabled})...")
    print(f"  Criteria: time_diff > {FILTER_TIME_DIFF_THRESHOLD/60:.0f}min AND score < {FILTER_MIN_SCORE}")
    entries, filtered = filter_false_positives(entries, filter_enabled=filter_enabled)
    print(f"  Kept: {len(entries)} entries")
    print(f"  Filtered: {len(filtered)} likely false positives")
    
    if args.verbose and filtered:
        print("\n  Filtered entries:")
        for e in filtered[:5]:
            norm_mid = (e.norm_start + e.norm_end) / 2
            tdk_mid = (e.tdk_start + e.tdk_end) / 2
            diff = abs(norm_mid - tdk_mid)
            print(f"    Norm {format_time(e.norm_start)}-{format_time(e.norm_end)} | TDK {format_time(e.tdk_start)}-{format_time(e.tdk_end)} | diff={diff/60:.0f}min score={e.score}")
            print(f"      \"{e.topic[:60]}...\"")
        if len(filtered) > 5:
            print(f"    ... and {len(filtered) - 5} more")
    
    # Group by TDK
    print(f"\nGrouping by TDK (exact_match={TDK_EXACT_MATCH})...")
    groups = group_by_tdk_overlap(entries)
    print(f"  Found {len(groups)} TDK groups")
    
    multi_groups = [g for g in groups if len(g) > 1]
    print(f"  Groups with duplicates: {len(multi_groups)}")
    
    if args.verbose and multi_groups:
        print("\n  Duplicate groups:")
        for i, group in enumerate(multi_groups[:5]):
            print(f"\n    Group {i+1}: TDK {format_time(group[0].tdk_start)}-{format_time(max(e.tdk_end for e in group))}")
            for e in group[:3]:
                print(f"      Norm {format_time(e.norm_start)}-{format_time(e.norm_end)} score={e.score}")
            if len(group) > 3:
                print(f"      ... and {len(group) - 3} more")
    
    # Consolidate
    print(f"\nConsolidating (Norm gap threshold={NORM_GAP_THRESHOLD}s)...")
    consolidated = consolidate_all(entries)
    print(f"  Result: {len(consolidated)} unique story matches")
    print(f"  Removed: {len(entries) - len(consolidated)} duplicates (plus {len(filtered)} filtered)")
    
    # Show results
    print("\n" + "=" * 60)
    print("CONSOLIDATED STORIES")
    print("=" * 60)
    
    for i, e in enumerate(consolidated):
        conf_marker = "🟢" if e.confidence == "HIGH" else "🟡"
        print(f"\n{i+1}. {conf_marker} [{e.confidence}] score={e.score}")
        print(f"   Norm: {format_time(e.norm_start)} - {format_time(e.norm_end)}")
        print(f"   TDK:  {format_time(e.tdk_start)} - {format_time(e.tdk_end)}")
        print(f"   \"{e.topic[:80]}\"")
    
    # Save
    if not args.dry_run:
        output = create_output_json(original_data, consolidated)
        output_path = MEMOIRS_DIR / "alternate_tellings.json"
        
        # Backup original
        backup_path = MEMOIRS_DIR / "alternate_tellings_backup.json"
        import shutil
        shutil.copy(output_path, backup_path)
        print(f"\n  Backup saved to: {backup_path}")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"  Saved consolidated results to: {output_path}")
    else:
        print(f"\n(Dry run - not saved)")
    
    print("\n" + "=" * 60)
    print("DONE")
    print("=" * 60)


if __name__ == "__main__":
    main()
