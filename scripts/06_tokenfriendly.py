"""
Convert transcript and chapter JSON files into token-friendly plain text format.
Run with: uv run 06_tokenfriendly.py [recording_path]

Processes all recording folders in public/recordings/ (including nested folders),
or a specific one if path is provided (e.g., "memoirs/Norm_red").

Output: Creates a {recording_id}.txt file in public/recordings/gemini_store/
with timestamps embedded on every line for RAG retrieval.

Format:
METADATA:
Title: {chapter_title_or_recording_id}
Tape ID: {recording_path}

CHAPTERS:
[00:00:06] Chapter: Narrator's Birth and Early Life
Description: The narrator initially discusses technical difficulties...

TRANSCRIPT:
[00:00:06] I go right back, and it starts in where I taped ...
[00:00:25] I'll roll this back now and see what's happening.
...
"""

import json
import sys
from pathlib import Path


def format_timestamp(seconds: float) -> str:
    """Convert seconds to [HH:MM:SS] format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"[{hours:02d}:{minutes:02d}:{secs:02d}]"


def load_json_file(filepath: Path) -> dict | list | None:
    """Load and parse a JSON file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"  Warning: Could not load {filepath}: {e}")
        return None


def convert_recording_to_text(recording_path: Path, output_dir: Path) -> bool:
    """
    Convert a single recording's transcript and chapters to plain text.
    
    Args:
        recording_path: Path to the recording folder (e.g., public/recordings/christmas1986)
        output_dir: Directory to write the output text file
        
    Returns:
        True if successful, False otherwise
    """
    transcript_file = recording_path / "transcript.json"
    chapters_file = recording_path / "chapters.json"
    
    # Load transcript (required)
    transcript_data = load_json_file(transcript_file)
    if not transcript_data or "segments" not in transcript_data:
        print(f"  Skipping {recording_path.name}: No valid transcript.json found")
        return False
    
    # Load chapters (optional)
    chapters_data = load_json_file(chapters_file)
    chapters = chapters_data.get("chapters", []) if chapters_data else []
    
    # Build the output text
    lines: list[str] = []
    
    # Derive a tape ID from the path relative to recordings/
    # e.g., "memoirs/Norm_red" or "christmas1986"
    tape_id = recording_path.name
    parent_name = recording_path.parent.name
    if parent_name != "recordings":
        tape_id = f"{parent_name}/{tape_id}"
    
    # Get first chapter title as a potential title, or use tape_id
    title = chapters[0]["title"] if chapters else tape_id.replace("_", " ").replace("/", " - ")
    
    # METADATA section
    lines.append("METADATA:")
    lines.append(f"Title: {title}")
    lines.append(f"Tape ID: {tape_id}")
    lines.append("")
    
    # CHAPTERS section (if available)
    if chapters:
        lines.append("CHAPTERS:")
        for chapter in chapters:
            start_time = chapter.get("startTime", 0)
            chapter_title = chapter.get("title", "Untitled")
            description = chapter.get("description", "")
            timestamp = format_timestamp(start_time)
            
            lines.append(f"{timestamp} Chapter: {chapter_title}")
            if description:
                lines.append(f"  Description: {description}")
        lines.append("")
    
    # TRANSCRIPT section
    lines.append("TRANSCRIPT:")
    segments = transcript_data["segments"]
    
    for segment in segments:
        start_time = segment.get("start", 0)
        text = segment.get("text", "").strip()
        if text:
            timestamp = format_timestamp(start_time)
            lines.append(f"{timestamp} {text}")
    
    # Write output file
    output_dir.mkdir(parents=True, exist_ok=True)
    # Sanitize the tape_id for filename (replace / with _)
    safe_filename = tape_id.replace("/", "_").replace("\\", "_")
    output_file = output_dir / f"{safe_filename}.txt"
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    print(f"  ✓ Created {output_file.name}")
    return True


def find_recordings_with_transcripts(recordings_dir: Path) -> list[Path]:
    """Find all recording folders that have transcript.json files."""
    recordings = []
    
    for transcript_file in recordings_dir.rglob("transcript.json"):
        recording_folder = transcript_file.parent
        recordings.append(recording_folder)
    
    return sorted(recordings)


def main():
    # Determine the project root (parent of scripts/)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    recordings_dir = project_root / "public" / "recordings"
    output_dir = project_root / "token_friendly"
    
    print("=" * 60)
    print("TOKEN-FRIENDLY TEXT GENERATOR")
    print("=" * 60)
    
    if not recordings_dir.exists():
        print(f"Error: Recordings directory not found: {recordings_dir}")
        sys.exit(1)
    
    # Check if a specific recording path was provided
    if len(sys.argv) > 1:
        specific_path = sys.argv[1]
        target_path = recordings_dir / specific_path
        
        if not target_path.exists():
            print(f"Error: Recording path not found: {target_path}")
            sys.exit(1)
        
        if not (target_path / "transcript.json").exists():
            print(f"Error: No transcript.json found in: {target_path}")
            sys.exit(1)
        
        print(f"\nProcessing specific recording: {specific_path}")
        success = convert_recording_to_text(target_path, output_dir)
        
        if success:
            print("\n✓ Conversion complete!")
        else:
            print("\n✗ Conversion failed")
            sys.exit(1)
    else:
        # Process all recordings
        recordings = find_recordings_with_transcripts(recordings_dir)
        
        if not recordings:
            print("\nNo recordings with transcript.json found.")
            sys.exit(0)
        
        print(f"\nFound {len(recordings)} recording(s) with transcripts:")
        for r in recordings:
            rel_path = r.relative_to(recordings_dir)
            print(f"  - {rel_path}")
        
        print("\nProcessing recordings...")
        success_count = 0
        fail_count = 0
        
        for recording in recordings:
            rel_path = recording.relative_to(recordings_dir)
            print(f"\n[{rel_path}]")
            
            if convert_recording_to_text(recording, output_dir):
                success_count += 1
            else:
                fail_count += 1
        
        print("\n" + "=" * 60)
        print(f"SUMMARY: {success_count} succeeded, {fail_count} failed")
        print(f"Output directory: {output_dir}")
        print("=" * 60)


if __name__ == "__main__":
    main()
