"""
Transcribe audio using WhisperX with word-level alignment.
Run with: uv run 01_transcribe.py [recording_path] [--startsecs N]

Processes all recording folders in source_audio/ (including nested folders),
or a specific one if path is provided (e.g., "memoirs/Norm_red").
Each recording folder can contain multiple WAV files which will be processed
in sorted order to create a continuous transcript.

The --startsecs option allows resuming transcription from a specific time,
preserving all manually corrected segments before that point.

Skips recordings that already have a transcript.json file (unless --startsecs is used).

Requires: uv pip install whisperx
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

# Add progress indication
print("=" * 60)
print("WHISPERX TRANSCRIPTION SCRIPT")
print("=" * 60)

# Check for required packages
try:
    import whisperx
    import torch
except ImportError as e:
    print(f"\nMissing required package: {e}")
    print("\nInstall with:")
    print("  uv pip install whisperx")
    print("  uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
    sys.exit(1)

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SOURCE_AUDIO_DIR = PROJECT_ROOT / "source_audio"
OUTPUT_BASE_DIR = PROJECT_ROOT / "public" / "recordings"

# Supported audio extensions
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aiff"}


def natural_sort_key(text: str):
    """Sort key for natural ordering (e.g., 1, 2, 10 instead of 1, 10, 2)."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]


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


def get_audio_duration(audio_path: Path) -> float:
    """Get duration of an audio file in seconds using whisperx's audio loading."""
    audio = whisperx.load_audio(str(audio_path))
    return len(audio) / 16000  # whisperx uses 16kHz sample rate


def transcribe_and_align(audio_path: Path, model, model_a, metadata, device: str, 
                         start_offset: float = 0.0, time_offset: float = 0.0) -> tuple[list[dict], float]:
    """
    Transcribe audio with WhisperX and align to get accurate word-level timestamps.
    
    Args:
        audio_path: Path to audio file
        model: WhisperX ASR model
        model_a: WhisperX alignment model
        metadata: Alignment model metadata
        device: cuda or cpu
        start_offset: Seconds into this file to start transcription
        time_offset: Offset to add to all timestamps (for multi-file recordings)
    
    Returns:
        Tuple of (list of segment dicts, duration of processed audio)
    """
    print(f"\n📝 Transcribing: {audio_path.name}")
    if start_offset > 0:
        print(f"   Starting from {start_offset:.1f}s into file")
    
    # Load full audio
    audio = whisperx.load_audio(str(audio_path))
    sample_rate = 16000
    
    # Trim to start_offset if needed
    if start_offset > 0:
        start_sample = int(start_offset * sample_rate)
        audio = audio[start_sample:]
    
    duration = len(audio) / sample_rate
    print(f"   Audio duration: {duration:.1f}s")
    
    # Transcribe with batched inference
    print("   Transcribing...")
    result = model.transcribe(audio, batch_size=16)
    print(f"   Found {len(result['segments'])} segments")
    
    # Align for accurate timestamps
    print("   Aligning timestamps...")
    result = whisperx.align(
        result["segments"], 
        model_a, 
        metadata, 
        audio, 
        device, 
        return_char_alignments=False
    )
    print(f"   Aligned {len(result['segments'])} segments")
    
    # Format segments with proper offsets
    segments = []
    for seg in result["segments"]:
        # Add start_offset (position within file) and time_offset (cumulative from previous files)
        # Round to 2 decimal places for cleaner output
        seg_start = round(seg["start"] + start_offset + time_offset, 2)
        seg_end = round(seg["end"] + start_offset + time_offset, 2)
        
        segments.append({
            "start": seg_start,
            "end": seg_end,
            "text": seg["text"].strip(),
        })
    
    return segments, duration


def format_transcript_data(all_segments: list[dict], files_info: list[dict], language: str = "en") -> dict:
    """Format all segments into the final transcript structure."""
    total_duration = sum(f["duration"] for f in files_info)
    
    result = {
        "segments": all_segments,
        "totalDuration": total_duration,
        "language": language,
    }
    
    # Only include files array if there are multiple files
    if len(files_info) > 1:
        result["files"] = files_info
    
    return result


def load_existing_transcript(transcript_path: Path) -> dict | None:
    """Load existing transcript if it exists."""
    if transcript_path.exists():
        with open(transcript_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def merge_transcripts(existing: dict, new_segments: list[dict], start_secs: float) -> dict:
    """
    Merge existing transcript with new segments, preserving everything before start_secs.
    
    Args:
        existing: Existing transcript data
        new_segments: New segments from transcription
        start_secs: Time in seconds where new transcription starts
    
    Returns:
        Merged transcript data
    """
    # Keep all segments that end before start_secs
    preserved_segments = [
        seg for seg in existing["segments"] 
        if seg["end"] <= start_secs
    ]
    
    print(f"   Preserved {len(preserved_segments)} segments before {start_secs}s")
    print(f"   Adding {len(new_segments)} new segments")
    
    # Combine preserved + new
    merged_segments = preserved_segments + new_segments
    
    # Sort by start time just in case
    merged_segments.sort(key=lambda s: s["start"])
    
    # Create merged result, preserving metadata from existing
    result = {
        "segments": merged_segments,
        "totalDuration": existing.get("totalDuration", 0),
        "language": existing.get("language", "en"),
    }
    
    if "files" in existing:
        result["files"] = existing["files"]
    
    return result


def process_recording(recording_folder: Path, model, model_a, metadata, device: str, 
                      start_secs: float | None = None) -> bool:
    """Process all audio files in a recording folder."""
    relative_path = get_relative_recording_path(recording_folder)
    output_dir = OUTPUT_BASE_DIR / relative_path
    transcript_path = output_dir / "transcript.json"
    
    # Check if we should skip
    if transcript_path.exists() and start_secs is None:
        print(f"\n⏭️  Skipping {relative_path} (transcript.json exists)")
        return True
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\n{'='*60}")
    print(f"📂 Processing recording: {relative_path}")
    print(f"   Output: {output_dir}")
    if start_secs is not None:
        print(f"   Starting from: {start_secs}s (preserving earlier segments)")
    print(f"{'='*60}")
    
    audio_files = get_audio_files_in_folder(recording_folder)
    if not audio_files:
        print(f"   ⚠️  No audio files found in {recording_folder}")
        return False
    
    print(f"   Found {len(audio_files)} audio file(s):")
    for f in audio_files:
        print(f"      - {f.name}")
    
    # Calculate file durations and determine which to process
    files_info = []
    cumulative_time = 0.0
    
    for audio_file in audio_files:
        duration = get_audio_duration(audio_file)
        files_info.append({
            "startTime": cumulative_time,
            "endTime": cumulative_time + duration,
            "duration": duration,
        })
        cumulative_time += duration
    
    print(f"   Total duration: {cumulative_time:.1f}s")
    
    # Determine starting point
    effective_start = start_secs if start_secs is not None else 0.0
    
    # Process each audio file
    all_new_segments = []
    
    for file_idx, audio_file in enumerate(audio_files):
        file_info = files_info[file_idx]
        file_start = file_info["startTime"]
        file_end = file_info["endTime"]
        
        # Skip files that end before our start point
        if file_end <= effective_start:
            print(f"\n⏭️  Skipping {audio_file.name} (ends at {file_end:.1f}s, before start)")
            continue
        
        # Calculate offset within this file
        offset_in_file = max(0, effective_start - file_start)
        
        segments, _ = transcribe_and_align(
            audio_file, model, model_a, metadata, device,
            start_offset=offset_in_file,
            time_offset=file_start
        )
        
        all_new_segments.extend(segments)
    
    # Merge with existing or create new
    existing = load_existing_transcript(transcript_path)
    
    if existing and start_secs is not None:
        transcript_data = merge_transcripts(existing, all_new_segments, start_secs)
    else:
        transcript_data = format_transcript_data(all_new_segments, files_info)
    
    # Backup existing transcript
    if transcript_path.exists():
        backup_path = transcript_path.with_suffix(".json.bak")
        shutil.copy(transcript_path, backup_path)
        print(f"\n   📦 Backed up existing transcript to {backup_path.name}")
    
    # Save transcript JSON
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(transcript_data, f, indent=2, ensure_ascii=False)
    print(f"\n   ✅ Saved transcript: {transcript_path}")
    print(f"      Total segments: {len(transcript_data['segments'])}")
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe audio using WhisperX with word-level alignment"
    )
    parser.add_argument(
        "recording", 
        nargs="?", 
        help="Specific recording path (e.g., memoirs/Norm_red)"
    )
    parser.add_argument(
        "--startsecs", 
        type=float, 
        default=None,
        help="Start transcription from this time (seconds), preserving earlier segments"
    )
    
    args = parser.parse_args()
    
    if args.recording:
        print(f"\n>>> Processing specific recording: {args.recording}")
    if args.startsecs is not None:
        print(f">>> Starting from {args.startsecs}s")
    
    # Check CUDA availability
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    
    print(f"\n🖥️  Using device: {device}")
    if device == "cuda":
        print(f"   GPU: {torch.cuda.get_device_name(0)}")
        print(f"   Compute type: {compute_type}")
    else:
        print("   ⚠️  CUDA not available, using CPU (will be slower)")
    
    # Get recording folders to process
    recording_folders = get_recording_folders(args.recording)
    if not recording_folders:
        print(f"\n❌ No recording folders found in {SOURCE_AUDIO_DIR}")
        sys.exit(1)
    
    print(f"\n📂 Found {len(recording_folders)} recording(s) to process:")
    for folder in recording_folders:
        rel_path = get_relative_recording_path(folder)
        audio_count = len(get_audio_files_in_folder(folder))
        print(f"   - {rel_path} ({audio_count} audio file(s))")
    
    # Load WhisperX model
    print("\n🔄 Loading WhisperX large-v3 model...")
    print("   (First run will download the model)")
    
    model = whisperx.load_model(
        "large-v3",
        device,
        compute_type=compute_type,
        language="en"
    )
    print("   ✅ ASR model loaded!")
    
    # Load alignment model
    print("\n🔄 Loading alignment model...")
    model_a, metadata = whisperx.load_align_model(language_code="en", device=device)
    print("   ✅ Alignment model loaded!")
    
    # Process each recording folder
    success_count = 0
    for recording_folder in recording_folders:
        if process_recording(recording_folder, model, model_a, metadata, device, args.startsecs):
            success_count += 1
    
    print("\n" + "=" * 60)
    print(f"✅ TRANSCRIPTION COMPLETE! ({success_count}/{len(recording_folders)} recordings)")
    print("=" * 60)


if __name__ == "__main__":
    main()
