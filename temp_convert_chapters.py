"""
Temporary script to convert existing chapters.json files to the new format.

The new format:
- Merges stories into the chapters array
- Stories become chapters with `minor: true` property
- Removes the separate `stories` array

Run with: python temp_convert_chapters.py
"""

import json
from pathlib import Path


def find_all_chapters_files(base_dir: Path) -> list[Path]:
    """Recursively find all chapters.json files."""
    return list(base_dir.rglob("chapters.json"))


def convert_chapters_file(chapters_path: Path) -> bool:
    """Convert a single chapters.json file to the new format."""
    print(f"\n📂 Processing: {chapters_path}")
    
    with open(chapters_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    chapters = data.get("chapters", [])
    stories = data.get("stories", [])
    summary = data.get("summary", "")
    
    # If no stories, nothing to convert
    if not stories:
        print("   ⏭️  No stories to convert, skipping")
        return False
    
    print(f"   Found {len(chapters)} chapters and {len(stories)} stories")
    
    # Convert stories to minor chapters
    minor_chapters = []
    for story in stories:
        minor_chapter = {
            "title": story["title"],
            "startTime": story["startTime"],
            "description": story.get("description", ""),
            "minor": True
        }
        minor_chapters.append(minor_chapter)
    
    # Merge all chapters and sort by startTime
    all_chapters = chapters + minor_chapters
    all_chapters = sorted(all_chapters, key=lambda c: c["startTime"])
    
    # Create new format (without stories array)
    new_data = {
        "chapters": all_chapters,
        "summary": summary
    }
    
    # Write back
    with open(chapters_path, "w", encoding="utf-8") as f:
        json.dump(new_data, f, indent=2, ensure_ascii=False)
    
    print(f"   ✅ Converted: {len(chapters)} major + {len(stories)} minor = {len(all_chapters)} total chapters")
    return True


def main():
    print("=" * 60)
    print("CHAPTERS.JSON CONVERSION SCRIPT")
    print("Converting from stories array to minor chapters format")
    print("=" * 60)
    
    # Find all chapters.json files in public/recordings
    script_dir = Path(__file__).parent
    recordings_dir = script_dir / "public" / "recordings"
    
    if not recordings_dir.exists():
        print(f"\n❌ Recordings directory not found: {recordings_dir}")
        return
    
    chapters_files = find_all_chapters_files(recordings_dir)
    
    if not chapters_files:
        print(f"\n❌ No chapters.json files found in {recordings_dir}")
        return
    
    print(f"\n📚 Found {len(chapters_files)} chapters.json file(s)")
    
    converted_count = 0
    for chapters_path in chapters_files:
        if convert_chapters_file(chapters_path):
            converted_count += 1
    
    print("\n" + "=" * 60)
    print(f"✅ CONVERSION COMPLETE! ({converted_count}/{len(chapters_files)} files converted)")
    print("=" * 60)


if __name__ == "__main__":
    main()
