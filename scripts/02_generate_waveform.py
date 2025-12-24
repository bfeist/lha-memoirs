"""
Generate waveform data using audiowaveform for peaks.js visualization.
Also converts WAV to MP3 (CBR) using FFmpeg for efficient web playback.

Run with: uv run 02_generate_waveform.py

Requires:
  - audiowaveform: https://github.com/bbc/audiowaveform/releases
  - ffmpeg: https://ffmpeg.org/download.html (add to PATH)
"""

import subprocess
import sys
from pathlib import Path

print("=" * 60)
print("WAVEFORM & AUDIO CONVERSION SCRIPT")
print("=" * 60)

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SOURCE_AUDIO_DIR = PROJECT_ROOT / "source_audio"
OUTPUT_DIR = PROJECT_ROOT / "public" / "audio" / "christmas1986"
AUDIO_MP3 = OUTPUT_DIR / "audio.mp3"


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


def convert_wav_to_mp3(wav_path: Path, mp3_path: Path, bitrate: str = "192k"):
    """Convert WAV to MP3 using FFmpeg with CBR for reliable seeking."""
    print(f"\n🔄 Converting WAV to MP3 (CBR {bitrate})...")
    print(f"   Input: {wav_path}")
    print(f"   Output: {mp3_path}")
    
    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output file
        "-i", str(wav_path),
        "-codec:a", "libmp3lame",
        "-b:a", bitrate,  # Constant bitrate for reliable seeking
        "-ar", "44100",  # Sample rate
        "-ac", "2",  # Stereo (or mono if source is mono)
        str(mp3_path),
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ Error converting to MP3:")
        print(result.stderr)
        return False
    
    # Show file size comparison
    wav_size = wav_path.stat().st_size / (1024 * 1024)
    mp3_size = mp3_path.stat().st_size / (1024 * 1024)
    reduction = (1 - mp3_size / wav_size) * 100
    
    print(f"   ✅ MP3 created!")
    print(f"   📊 Size: {wav_size:.1f} MB → {mp3_size:.1f} MB ({reduction:.0f}% smaller)")
    return True


def generate_waveform_json(audio_path: Path, output_path: Path, pixels_per_second: int = 20):
    """Generate waveform data in JSON format for peaks.js."""
    print(f"\n🔄 Generating waveform data...")
    print(f"   Input: {audio_path}")
    print(f"   Output: {output_path}")
    print(f"   Resolution: {pixels_per_second} pixels/second")
    
    cmd = [
        "audiowaveform",
        "-i", str(audio_path),
        "-o", str(output_path),
        "--pixels-per-second", str(pixels_per_second),
        "-b", "8",  # 8-bit resolution for smaller file
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"❌ Error generating waveform:")
        print(result.stderr)
        return False
    
    print(f"   ✅ Waveform JSON generated!")
    return True


def generate_waveform_dat(audio_path: Path, output_path: Path, pixels_per_second: int = 20):
    """Generate waveform data in binary DAT format (more efficient for peaks.js)."""
    print(f"\n🔄 Generating binary waveform data...")
    print(f"   Input: {audio_path}")
    print(f"   Output: {output_path}")
    
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
    
    print(f"   ✅ Waveform DAT generated!")
    return True


def get_source_audio():
    """Find the source audio file in source_audio directory."""
    audio_extensions = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
    for f in SOURCE_AUDIO_DIR.iterdir():
        if f.suffix.lower() in audio_extensions:
            return f
    return None


def main():
    # Check for required tools
    if not check_audiowaveform():
        sys.exit(1)
    
    if not check_ffmpeg():
        sys.exit(1)
    
    # Find source audio file
    source_audio = get_source_audio()
    if not source_audio:
        print(f"\n❌ No audio file found in: {SOURCE_AUDIO_DIR}")
        print("   Add a WAV, MP3, M4A, FLAC, or OGG file to source_audio/")
        sys.exit(1)
    
    print(f"\n📂 Source audio: {source_audio}")
    
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Convert to MP3 (CBR for reliable seeking)
    if not convert_wav_to_mp3(source_audio, AUDIO_MP3):
        sys.exit(1)
    
    # Generate JSON waveform (used by peaks.js)
    json_output = OUTPUT_DIR / "waveform.json"
    if not generate_waveform_json(source_audio, json_output):
        sys.exit(1)
    
    # Clean up old unused files if they exist
    old_files = ["waveform.dat", "audio.wav"]
    for old_file in old_files:
        old_path = OUTPUT_DIR / old_file
        if old_path.exists():
            old_path.unlink()
            print(f"   🧹 Removed unused file: {old_file}")
    
    # Show file sizes
    print("\n📊 Generated files:")
    print(f"   - {AUDIO_MP3.name}: {AUDIO_MP3.stat().st_size / (1024*1024):.1f} MB (for web playback)")
    print(f"   - {json_output.name}: {json_output.stat().st_size / 1024:.1f} KB")
    
    print("\n" + "=" * 60)
    print("✅ WAVEFORM & AUDIO CONVERSION COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
