"""
Temporary script to transcribe Dad_xmas-1986.wav to transcript_orig.json
For internal reference only - won't overwrite existing files.
Run with: uv run temp_transcribe_orig.py
"""

import json
import sys
from pathlib import Path

print("=" * 60)
print("TEMPORARY TRANSCRIPTION TO transcript_orig.json")
print("=" * 60)

# Check for required packages
try:
    from faster_whisper import WhisperModel
    import torch
except ImportError as e:
    print(f"\nMissing required package: {e}")
    print("\nInstall with:")
    print("  uv pip install faster-whisper torch")
    sys.exit(1)

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
AUDIO_FILE = PROJECT_ROOT / "source_audio" / "Dad_xmas-1986.wav"
OUTPUT_FILE = PROJECT_ROOT / "public" / "audio" / "christmas1986" / "transcript_orig.json"

# Check if audio file exists
if not AUDIO_FILE.exists():
    print(f"\n❌ Audio file not found: {AUDIO_FILE}")
    sys.exit(1)

print(f"\n📂 Input: {AUDIO_FILE.name}")
print(f"📄 Output: {OUTPUT_FILE.name}")


def transcribe_with_segments(audio_path: Path, model):
    """Transcribe audio with segment-level timestamps."""
    print(f"\n📝 Transcribing...")
    print("   This may take a while...")
    
    segments, info = model.transcribe(
        str(audio_path),
        language="en",
        word_timestamps=True,
        beam_size=5,
        vad_filter=True,
    )
    
    print(f"   Detected language: {info.language} (probability: {info.language_probability:.2f})")
    print(f"   Audio duration: {info.duration:.1f}s")
    
    # Convert generator to list with progress
    segment_list = []
    for segment in segments:
        segment_list.append(segment)
        if len(segment_list) % 10 == 0:
            progress = segment.end / info.duration * 100
            print(f"   Progress: {progress:.1f}%", end="\r")
    
    print(f"   Progress: 100.0%")
    
    return segment_list, info


def format_transcript_data(segments, info):
    """Format faster-whisper result into structured data."""
    formatted_segments = []
    
    for segment in segments:
        seg_data = {
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip(),
        }
        formatted_segments.append(seg_data)
    
    return {
        "segments": formatted_segments,
        "language": info.language,
        "duration": info.duration,
    }


def main():
    # Check CUDA availability
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    
    print(f"\n🖥️  Using device: {device}")
    if device == "cuda":
        print(f"   GPU: {torch.cuda.get_device_name(0)}")
        print(f"   Compute type: {compute_type}")
    else:
        print("   ⚠️  CUDA not available, using CPU (will be slower)")
    
    # Load faster-whisper model
    print("\n🔄 Loading faster-whisper large-v3 model...")
    
    model = WhisperModel(
        "large-v3",
        device=device,
        compute_type=compute_type,
        num_workers=4,
    )
    print("   ✅ Model loaded!")
    
    # Transcribe
    segments, info = transcribe_with_segments(AUDIO_FILE, model)
    
    # Format the data
    transcript_data = format_transcript_data(segments, info)
    
    # Save to transcript_orig.json
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(transcript_data, f, indent=2, ensure_ascii=False)
    print(f"\n   ✅ Saved: {OUTPUT_FILE}")
    
    print("\n" + "=" * 60)
    print("✅ TRANSCRIPTION COMPLETE!")
    print(f"   Output: transcript_orig.json")
    print("=" * 60)


if __name__ == "__main__":
    main()
