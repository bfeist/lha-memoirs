#!/usr/bin/env python3
"""
Shared utilities for reading and writing transcript files in CSV format.

CSV Format:
- Pipe-delimited (|) to avoid issues with commas in text
- Header row: start|end|text
- Data rows with timestamps and transcribed text

Example:
    start|end|text
    6.45|10.61|I go right back, and it starts in where I taped ...
    25.24|28.24|I'll roll this back now and see what's happening.
"""
import csv
import json
import re
from pathlib import Path

DELIMITER = "|"


def read_transcript_csv(path: Path) -> dict:
    """Read a transcript CSV file and return segment data.
    
    Returns:
        dict with key: segments (list of {start, end, text} dicts)
    """
    segments = []
    
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find data start (skip comments and header)
    data_start = 0
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith('#'):
            # Skip comment lines
            continue
        elif line.lower().startswith('start'):
            # Skip header row
            data_start = i + 1
            break
        elif line:
            # Non-empty, non-comment, non-header line - data starts here
            data_start = i
            break
    
    # Parse data rows
    for line in lines[data_start:]:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # Split by delimiter, but only first 2 splits (text may contain |)
        parts = line.split(DELIMITER, 2)
        if len(parts) >= 3:
            try:
                start = float(parts[0])
                end = float(parts[1])
                text = parts[2]
                segments.append({
                    'start': start,
                    'end': end,
                    'text': text
                })
            except ValueError:
                # Skip malformed lines
                continue
    
    return {'segments': segments}


def write_transcript_csv(path: Path, data: dict) -> None:
    """Write a transcript dict to CSV format.
    
    Args:
        path: Output file path
        data: dict with key: segments
    """
    with open(path, 'w', encoding='utf-8', newline='') as f:
        # Write header
        f.write(f"start{DELIMITER}end{DELIMITER}text\n")
        
        # Write segments
        for seg in data['segments']:
            start = seg['start']
            end = seg['end']
            text = seg['text']
            # Escape any pipe characters in text (rare but possible)
            # We use double-pipe to escape
            text = text.replace('|', '||')
            f.write(f"{start}{DELIMITER}{end}{DELIMITER}{text}\n")


def read_transcript_json(path: Path) -> dict:
    """
    Read a transcript JSON file (for conversion purposes).
    """
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def convert_json_to_csv(json_path: Path, csv_path: Path) -> None:
    """
    Convert a transcript.json file to transcript.csv format.
    """
    data = read_transcript_json(json_path)
    write_transcript_csv(csv_path, data)


def get_transcript_path(recording_dir: Path, prefer_csv: bool = True) -> Path | None:
    """
    Get the transcript file path for a recording directory.
    
    Prefers CSV if it exists when prefer_csv=True, otherwise returns JSON path.
    Returns None if neither exists.
    """
    csv_path = recording_dir / "transcript.csv"
    json_path = recording_dir / "transcript.json"
    
    if prefer_csv and csv_path.exists():
        return csv_path
    if json_path.exists():
        return json_path
    if csv_path.exists():
        return csv_path
    return None


def load_transcript(recording_dir: Path) -> dict | None:
    """
    Load a transcript from a recording directory, supporting both CSV and JSON formats.
    Prefers CSV if both exist.
    """
    path = get_transcript_path(recording_dir)
    if path is None:
        return None
    
    if path.suffix == '.csv':
        return read_transcript_csv(path)
    else:
        return read_transcript_json(path)


def save_transcript(recording_dir: Path, data: dict, format: str = 'csv') -> Path:
    """
    Save a transcript to a recording directory.
    
    Args:
        recording_dir: Directory to save to
        data: Transcript data dict
        format: 'csv' or 'json'
    
    Returns:
        Path to the saved file
    """
    if format == 'csv':
        path = recording_dir / "transcript.csv"
        write_transcript_csv(path, data)
    else:
        path = recording_dir / "transcript.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return path
