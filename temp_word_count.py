import json
import os
from pathlib import Path

recordings_dir = Path("public/recordings")
total_words = 0
word_counts = {}

# Find all transcript.json files
for transcript_path in recordings_dir.rglob("transcript.json"):
    try:
        with open(transcript_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Extract text based on structure
        text = ""
        if isinstance(data, dict):
            # If it's a dictionary with segments key
            if 'segments' in data and isinstance(data['segments'], list):
                for segment in data['segments']:
                    if isinstance(segment, dict) and 'text' in segment:
                        text += " " + segment['text']
            # If it's a dictionary with transcript key
            elif 'transcript' in data:
                if isinstance(data['transcript'], list):
                    for segment in data['transcript']:
                        if isinstance(segment, dict) and 'text' in segment:
                            text += " " + segment['text']
                else:
                    text = data['transcript']
            elif 'text' in data:
                text = data['text']
        elif isinstance(data, list):
            # If it's a list of segments
            for segment in data:
                if isinstance(segment, dict):
                    if 'text' in segment:
                        text += " " + segment['text']
                    elif 'transcript' in segment:
                        text += " " + segment['transcript']
        
        # Count words
        word_count = len(text.split())
        relative_path = transcript_path.relative_to(recordings_dir)
        word_counts[str(relative_path)] = word_count
        total_words += word_count
        
    except Exception as e:
        print(f"Error processing {transcript_path}: {e}")

# Display results
print("\n=== Word Count by Recording ===\n")
for recording, count in sorted(word_counts.items()):
    print(f"{recording}: {count:,} words")

print(f"\n=== TOTAL: {total_words:,} words ===")
