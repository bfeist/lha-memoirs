import json
import os
from pathlib import Path

recordings_dir = Path("public/recordings")
total_words = 0
word_counts = {}

# Find all transcript.json files
for transcript_path in recordings_dir.rglob("transcript.json"):
    # Skip transcripts under tibbits_cd directory
    relative = transcript_path.relative_to(recordings_dir)
    if relative.parts and relative.parts[0] == "tibbits_cd":
        print(f"Skipping {relative} (tibbits_cd)")
        continue
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
            elif 'text' in data:
                text = data['text']        
        
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
