"""
Transcribe audio using faster-whisper (CTranslate2) with word-level alignment.
Run with: uv run 01_transcribe.py

Requires: pip install faster-whisper torch
Or with uv: uv pip install faster-whisper torch
"""

import json
import os
import sys
from pathlib import Path

# Add progress indication
print("=" * 60)
print("FASTER-WHISPER TRANSCRIPTION SCRIPT")
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
SOURCE_AUDIO_DIR = PROJECT_ROOT / "source_audio"
OUTPUT_DIR = PROJECT_ROOT / "public" / "audio" / "christmas1986"

# Ensure output directory exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_audio_files():
    """Find all audio files in source_audio directory."""
    audio_extensions = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
    audio_files = []
    for f in SOURCE_AUDIO_DIR.iterdir():
        if f.suffix.lower() in audio_extensions:
            audio_files.append(f)
    return audio_files


def transcribe_with_word_alignment(audio_path: Path, model):
    """Transcribe audio with segment-level timestamps using faster-whisper."""
    print(f"\n📝 Transcribing: {audio_path.name}")
    print("   This may take a while for large files...")
    
    # Transcribe without word timestamps (faster, we only use segments)
    segments, info = model.transcribe(
        str(audio_path),
        language="en",
        word_timestamps=False,
        beam_size=5,
        vad_filter=True,  # Voice activity detection for better accuracy
    )
    
    print(f"   Detected language: {info.language} (probability: {info.language_probability:.2f})")
    print(f"   Audio duration: {info.duration:.1f}s")
    
    # Convert generator to list with progress
    segment_list = []
    for segment in segments:
        segment_list.append(segment)
        # Print progress every 10 segments
        if len(segment_list) % 10 == 0:
            progress = segment.end / info.duration * 100
            print(f"   Progress: {progress:.1f}%", end="\r")
    
    print(f"   Progress: 100.0%")
    
    return segment_list, info


def format_transcript_data(segments, info):
    """Format faster-whisper result into structured data for the app."""
    formatted_segments = []
    
    for seg_idx, segment in enumerate(segments):
        seg_data = {
            "id": seg_idx,
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
        print(f"   Compute type: {compute_type} (optimized for speed)")
    else:
        print("   ⚠️  CUDA not available, using CPU (will be slower)")
    
    # Find audio files
    audio_files = get_audio_files()
    if not audio_files:
        print(f"\n❌ No audio files found in {SOURCE_AUDIO_DIR}")
        sys.exit(1)
    
    print(f"\n📂 Found {len(audio_files)} audio file(s):")
    for f in audio_files:
        print(f"   - {f.name}")
    
    # Load faster-whisper model
    print("\n🔄 Loading faster-whisper large-v3 model...")
    print("   (First run will download the model)")
    
    model = WhisperModel(
        "large-v3",
        device=device,
        compute_type=compute_type,
        num_workers=4,  # Parallel processing
    )
    print("   ✅ Model loaded!")
    
    # Process each audio file
    for audio_file in audio_files:
        segments, info = transcribe_with_word_alignment(audio_file, model)
        
        # Format the data
        transcript_data = format_transcript_data(segments, info)
        
        # Save outputs
        base_name = audio_file.stem
        
        # Save full transcript JSON (main file used by the app)
        transcript_path = OUTPUT_DIR / "transcript.json"
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump(transcript_data, f, indent=2, ensure_ascii=False)
        print(f"\n   ✅ Saved transcript: {transcript_path}")
        
        # Clean up old unused files if they exist
        old_files = ["words.json", "segments.json", "transcript.txt", "audio.wav"]
        for old_file in old_files:
            old_path = OUTPUT_DIR / old_file
            if old_path.exists():
                old_path.unlink()
                print(f"   🧹 Removed unused file: {old_file}")
    
    print("\n" + "=" * 60)
    print("✅ TRANSCRIPTION COMPLETE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
