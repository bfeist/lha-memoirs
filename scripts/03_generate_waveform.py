"""
Generate waveform data and convert audio to MP3 for web hosting.
Run with: uv run 02_generate_waveform.py [recording_path]

Processes all recording folders in source_audio/ (including nested folders),
or a specific one if path is provided (e.g., "memoirs/HF_60").

Converts source audio to MP3 CBR (concatenating multiple files if needed),
then generates waveform JSON for peaks.js visualization.

Skips recordings that already have audio.mp3 and waveform.json.

Requires:
  - ffmpeg: https://ffmpeg.org/download.html (add to PATH)
  - audiowaveform: https://github.com/bbc/audiowaveform/releases
"""

import re
import subprocess
import sys
import tempfile
from pathlib import Path

print("=" * 60)
print("WAVEFORM & AUDIO CONVERSION SCRIPT")
print("=" * 60)

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SOURCE_AUDIO_DIR = PROJECT_ROOT / "source_audio"
OUTPUT_BASE_DIR = PROJECT_ROOT / "public" / "static_assets"

# Supported audio extensions
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aiff"}


def natural_sort_key(text: str):
    """Sort key for natural ordering (e.g., 1, 2, 10 instead of 1, 10, 2)."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]


def check_ffmpeg():
    """Check if ffmpeg is installed."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
        )
        version_line = result.stdout.split("\n")[0] if result.stdout else "unknown"
        print(f"✅ ffmpeg found: {version_line}")
        return True
    except FileNotFoundError:
        print("\n❌ ffmpeg not found in PATH!")
        print("\nTo install:")
        print("  Windows: winget install ffmpeg")
        print("  macOS: brew install ffmpeg")
        print("  Linux: sudo apt install ffmpeg")
        return False


def check_audiowaveform():
    """Check if audiowaveform is installed."""
    try:
        result = subprocess.run(
            ["audiowaveform", "--version"],
            capture_output=True,
            text=True,
        )
        print(f"✅ audiowaveform found: {result.stdout.strip() or result.stderr.strip()}")
        return True
    except FileNotFoundError:
        print("\n❌ audiowaveform not found in PATH!")
        print("\nTo install:")
        print("  1. Download from: https://github.com/bbc/audiowaveform/releases")
        print("  2. Extract and add to your PATH")
        print("  3. Or use: winget install audiowaveform (if available)")
        return False


def get_audio_files_in_folder(folder: Path) -> list[Path]:
    """Find all audio files in a folder (non-recursive), sorted for proper ordering."""
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
        # Also check subdirectories
        for item in sorted(folder.iterdir()):
            if item.is_dir():
                scan_folder(item)
    
    scan_folder(base_dir)
    return recordings


def get_recording_folders(specific_recording: str | None = None) -> list[Path]:
    """Get recording folders from source_audio, or a specific one by relative path."""
    if specific_recording:
        folder = SOURCE_AUDIO_DIR / specific_recording
        if folder.exists() and folder.is_dir():
            audio_files = get_audio_files_in_folder(folder)
            if audio_files:
                return [folder]
            else:
                return find_all_recordings(folder)
        else:
            print(f"❌ Recording folder not found: {folder}")
            return []
    
    return find_all_recordings(SOURCE_AUDIO_DIR)


def get_relative_recording_path(recording_folder: Path) -> str:
    """Get the path of a recording relative to source_audio."""
    return str(recording_folder.relative_to(SOURCE_AUDIO_DIR)).replace("\\", "/")


def convert_single_to_mp3(input_path: Path, output_path: Path, bitrate: str = "192k") -> bool:
    """Convert a single audio file to MP3 CBR."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-codec:a", "libmp3lame",
        "-b:a", bitrate,
        "-ar", "44100",
        "-ac", "2",
        str(output_path),
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ Error converting to MP3:")
        print(result.stderr)
        return False
    
    return True


def concatenate_and_convert_to_mp3(audio_files: list[Path], output_path: Path, bitrate: str = "192k") -> bool:
    """Concatenate multiple audio files and convert to MP3 CBR."""
    print(f"   Concatenating {len(audio_files)} files...")
    
    for af in audio_files:
        print(f"      - {af.name}")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for audio_file in audio_files:
            escaped_path = str(audio_file).replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")
        concat_file = Path(f.name)
    
    try:
        cmd = [
            "ffmpeg",
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-codec:a", "libmp3lame",
            "-b:a", bitrate,
            "-ar", "44100",
            "-ac", "2",
            str(output_path),
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"❌ Error converting to MP3:")
            print(result.stderr)
            return False
        
        return True
    
    finally:
        concat_file.unlink()


def generate_waveform_json(audio_path: Path, output_path: Path, pixels_per_second: int = 20) -> bool:
    """Generate waveform data in JSON format for peaks.js."""
    print(f"\n🔄 Generating waveform data...")
    
    cmd = [
        "audiowaveform",
        "-i", str(audio_path),
        "-o", str(output_path),
        "--pixels-per-second", str(pixels_per_second),
        "-b", "8",
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ Error generating waveform:")
        print(result.stderr)
        return False
    
    print(f"   ✅ Waveform generated: {output_path.stat().st_size / 1024:.1f} KB")
    return True


def process_recording(recording_folder: Path) -> bool:
    """Process a single recording folder."""
    relative_path = get_relative_recording_path(recording_folder)
    output_dir = OUTPUT_BASE_DIR / relative_path
    output_mp3 = output_dir / "audio_original.mp3"
    output_waveform = output_dir / "waveform.json"
    
    # Skip if already processed
    if output_mp3.exists() and output_waveform.exists():
        print(f"\n⏭️  Skipping {relative_path} (audio_original.mp3 and waveform.json exist)")
        return True
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*60}")
    print(f"📂 Processing recording: {relative_path}")
    print(f"   Output: {output_dir}")
    print(f"{'='*60}")
    
    audio_files = get_audio_files_in_folder(recording_folder)
    if not audio_files:
        print(f"   ⚠️  No audio files found in {recording_folder}")
        return False
    
    # Convert to MP3 if needed
    if not output_mp3.exists():
        total_source_size = sum(f.stat().st_size for f in audio_files)
        
        print(f"\n🔄 Converting to MP3 (CBR 192k)...")
        
        if len(audio_files) == 1:
            print(f"   Input: {audio_files[0].name}")
            if not convert_single_to_mp3(audio_files[0], output_mp3):
                return False
        else:
            if not concatenate_and_convert_to_mp3(audio_files, output_mp3):
                return False
        
        mp3_size = output_mp3.stat().st_size
        reduction = (1 - mp3_size / total_source_size) * 100 if total_source_size > 0 else 0
        print(f"   ✅ MP3 created: {mp3_size / (1024*1024):.1f} MB ({reduction:.0f}% smaller)")
    else:
        print(f"\n   ℹ️  audio_original.mp3 already exists")
    
    # Generate waveform if needed
    if not output_waveform.exists():
        if not generate_waveform_json(output_mp3, output_waveform):
            return False
    else:
        print(f"   ℹ️  waveform.json already exists")
    
    # Clean up old unused files
    old_files = ["waveform.dat", "audio.wav", "audio.mp3"]
    for old_file in old_files:
        old_path = output_dir / old_file
        if old_path.exists():
            old_path.unlink()
            print(f"   🧹 Removed unused file: {old_file}")
    
    return True


def main():
    specific_recording = None
    if len(sys.argv) > 1:
        specific_recording = sys.argv[1]
        print(f"\n🎯 Processing specific recording: {specific_recording}")
    
    if not check_ffmpeg():
        sys.exit(1)
    
    if not check_audiowaveform():
        sys.exit(1)
    
    recording_folders = get_recording_folders(specific_recording)
    if not recording_folders:
        print(f"\n❌ No recording folders found in {SOURCE_AUDIO_DIR}")
        sys.exit(1)
    
    print(f"\n📂 Found {len(recording_folders)} recording(s) to process:")
    for folder in recording_folders:
        rel_path = get_relative_recording_path(folder)
        audio_count = len(get_audio_files_in_folder(folder))
        print(f"   - {rel_path} ({audio_count} audio file(s))")
    
    success_count = 0
    for recording_folder in recording_folders:
        if process_recording(recording_folder):
            success_count += 1
    
    print("\n" + "=" * 60)
    print(f"✅ WAVEFORM & AUDIO CONVERSION COMPLETE! ({success_count}/{len(recording_folders)} recordings)")
    print("=" * 60)


if __name__ == "__main__":
    main()
