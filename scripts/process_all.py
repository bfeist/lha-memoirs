"""
Master script to run all processing steps in order.
Run with: uv run process_all.py [recording_path]

If a recording_path is specified (e.g., "memoirs/HF_60"), only that recording 
will be processed. Otherwise, all recordings in source_audio/ (including nested
folders) will be processed.

Each step will skip recordings that already have the output files.

This script will:
1. Transcribe audio with Whisper (segment-level alignment)
2. Convert audio to MP3 and generate waveform data
3. Analyze content and create chapters with Ollama
"""

import re
import subprocess
import sys
from pathlib import Path

print("=" * 60)
print("LHA MEMOIRS - AUDIO PROCESSING PIPELINE")
print("=" * 60)
print("\nThis will process your audio recordings.")
print("Each step may take several minutes depending on audio length.\n")

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SOURCE_AUDIO_DIR = PROJECT_ROOT / "source_audio"

# Supported audio extensions
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aiff"}

# Scripts to run in order (with optional recording_path arg)
SCRIPTS = [
    ("01_transcribe.py", "Transcribing audio with Whisper..."),
    ("02_generate_waveform.py", "Converting audio to MP3 and generating waveform..."),
    ("03_analyze_chapters.py", "Analyzing content for chapters..."),
]


def natural_sort_key(text: str):
    """Sort key for natural ordering."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]


def get_audio_files_in_folder(folder: Path) -> list[Path]:
    """Find all audio files in a folder (non-recursive)."""
    audio_files = []
    for f in folder.iterdir():
        if f.is_file() and f.suffix.lower() in AUDIO_EXTENSIONS:
            audio_files.append(f)
    return sorted(audio_files, key=lambda f: natural_sort_key(f.name))


def find_all_recordings(base_dir: Path) -> list[Path]:
    """Recursively find all folders containing audio files."""
    recordings = []
    
    def scan_folder(folder: Path):
        audio_files = get_audio_files_in_folder(folder)
        if audio_files:
            recordings.append(folder)
        for item in sorted(folder.iterdir()):
            if item.is_dir():
                scan_folder(item)
    
    scan_folder(base_dir)
    return recordings


def get_relative_path(folder: Path) -> str:
    """Get the path of a folder relative to source_audio."""
    return str(folder.relative_to(SOURCE_AUDIO_DIR)).replace("\\", "/")


def run_script(script_name: str, description: str, recording_path: str | None = None) -> bool:
    """Run a script and return success status."""
    print("\n" + "=" * 60)
    print(f"📌 STEP: {description}")
    print("=" * 60)
    
    script_path = SCRIPT_DIR / script_name
    
    if not script_path.exists():
        print(f"❌ Script not found: {script_path}")
        return False
    
    # Build command with optional recording path
    cmd = [sys.executable, str(script_path)]
    if recording_path:
        cmd.append(recording_path)
    
    # Run the script
    result = subprocess.run(
        cmd,
        cwd=SCRIPT_DIR,
    )
    
    return result.returncode == 0


def print_output_tree(base_dir: Path, indent: int = 0):
    """Recursively print the output directory tree."""
    prefix = "   " * indent
    
    for item in sorted(base_dir.iterdir()):
        if item.is_dir():
            print(f"{prefix}📁 {item.name}/")
            print_output_tree(item, indent + 1)
        elif item.is_file():
            size_kb = item.stat().st_size / 1024
            if size_kb > 1024:
                print(f"{prefix}   - {item.name} ({size_kb/1024:.1f} MB)")
            else:
                print(f"{prefix}   - {item.name} ({size_kb:.1f} KB)")


def main():
    # Check for recording path argument
    recording_path = None
    if len(sys.argv) > 1:
        recording_path = sys.argv[1]
        print(f"🎯 Processing specific recording: {recording_path}")
        
        # Verify it exists
        recording_folder = SOURCE_AUDIO_DIR / recording_path
        if not recording_folder.exists() or not recording_folder.is_dir():
            print(f"❌ Recording folder not found: {recording_folder}")
            sys.exit(1)
        
        # Check if it has audio files directly or is a parent folder
        audio_files = get_audio_files_in_folder(recording_folder)
        if audio_files:
            print(f"✅ Found {len(audio_files)} audio file(s)")
            for f in audio_files:
                print(f"   - {f.name}")
        else:
            # It's a parent folder, find nested recordings
            nested = find_all_recordings(recording_folder)
            if nested:
                print(f"✅ Found {len(nested)} nested recording(s)")
                for folder in nested:
                    rel_path = get_relative_path(folder)
                    audio_count = len(get_audio_files_in_folder(folder))
                    print(f"   - {rel_path} ({audio_count} file(s))")
            else:
                print(f"❌ No audio files found in: {recording_folder}")
                sys.exit(1)
    else:
        # Check for all recordings
        print("Checking for recordings to process...\n")
        
        recording_folders = find_all_recordings(SOURCE_AUDIO_DIR)
        
        if not recording_folders:
            print("❌ No recording folders with audio files found in /source_audio/")
            print("   Please add your audio files in subdirectories and try again.")
            sys.exit(1)
        
        print(f"✅ Found {len(recording_folders)} recording(s)")
        for folder in recording_folders:
            rel_path = get_relative_path(folder)
            audio_count = len(get_audio_files_in_folder(folder))
            print(f"   - {rel_path} ({audio_count} audio file(s))")
    
    # Run each script
    failed = []
    for script_name, description in SCRIPTS:
        success = run_script(script_name, description, recording_path)
        if not success:
            failed.append(script_name)
            print(f"\n⚠️ Script {script_name} failed. Continuing with remaining scripts...")
    
    # Summary
    print("\n" + "=" * 60)
    print("PROCESSING SUMMARY")
    print("=" * 60)
    
    if failed:
        print(f"\n⚠️ Some scripts failed: {failed}")
        print("   Review the errors above and fix any issues.")
    else:
        print("\n✅ All processing complete!")
    
    # Show output files
    output_base = PROJECT_ROOT / "public" / "recordings"
    if output_base.exists():
        print(f"\n📂 Output recordings in {output_base}:")
        print_output_tree(output_base)
    
    print("\n" + "=" * 60)
    print("You can now run the React app with: npm run dev")
    print("=" * 60)


if __name__ == "__main__":
    main()
