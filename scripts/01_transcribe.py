"""
Transcribe audio using faster-whisper (CTranslate2) with word-level alignment.
Run with: uv run 01_transcribe.py [recording_path]

Processes all recording folders in source_audio/ (including nested folders),
or a specific one if path is provided (e.g., "memoirs/HF_60").
Each recording folder can contain multiple WAV files which will be processed
in sorted order to create a continuous transcript.

Skips recordings that already have a transcript.json file.

Requires: pip install faster-whisper torch
Or with uv: uv pip install faster-whisper torch
"""

import json
import re
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
        # Also check subdirectories
        for item in sorted(folder.iterdir()):
            if item.is_dir():
                scan_folder(item)
    
    scan_folder(base_dir)
    return recordings


def get_recording_folders(specific_recording: str | None = None) -> list[Path]:
    """Get recording folders from source_audio, or a specific one by relative path."""
    if specific_recording:
        # Support nested paths like "memoirs/HF_60"
        folder = SOURCE_AUDIO_DIR / specific_recording
        if folder.exists() and folder.is_dir():
            # Check if it has audio files directly, or scan for nested recordings
            audio_files = get_audio_files_in_folder(folder)
            if audio_files:
                return [folder]
            else:
                # Maybe it's a parent folder with nested recordings
                return find_all_recordings(folder)
        else:
            print(f"❌ Recording folder not found: {folder}")
            return []
    
    # Find all recordings recursively
    return find_all_recordings(SOURCE_AUDIO_DIR)


def get_relative_recording_path(recording_folder: Path) -> str:
    """Get the path of a recording relative to source_audio."""
    return str(recording_folder.relative_to(SOURCE_AUDIO_DIR)).replace("\\", "/")


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


def format_transcript_data(all_file_results: list[dict]) -> dict:
    """Format faster-whisper results from multiple files into structured data for the app.
    
    Args:
        all_file_results: List of dicts with keys: file_name, segments, info, time_offset
    
    Returns:
        Combined transcript data with file boundaries tracked.
        Segments use fileIndex to reference the files array (avoids repetitive sourceFile strings).
    """
    formatted_segments = []
    files_info = []
    
    for file_idx, file_result in enumerate(all_file_results):
        file_name = file_result["file_name"]
        segments = file_result["segments"]
        info = file_result["info"]
        time_offset = file_result["time_offset"]
        
        # Track file timing boundaries (for multi-file recordings)
        files_info.append({
            "startTime": time_offset,
            "endTime": time_offset + info.duration,
            "duration": info.duration,
        })
        
        for segment in segments:
            seg_data = {
                "start": segment.start + time_offset,
                "end": segment.end + time_offset,
                "text": segment.text.strip(),
            }
            # Only include fileIndex if there are multiple files
            if len(all_file_results) > 1:
                seg_data["fileIndex"] = file_idx
            formatted_segments.append(seg_data)
    
    total_duration = sum(f["duration"] for f in files_info)
    
    result = {
        "segments": formatted_segments,
        "totalDuration": total_duration,
        "language": all_file_results[0]["info"].language if all_file_results else "en",
    }
    
    # Only include files array if there are multiple files
    if len(files_info) > 1:
        result["files"] = files_info
    
    return result


def process_recording(recording_folder: Path, model) -> bool:
    """Process all audio files in a recording folder."""
    relative_path = get_relative_recording_path(recording_folder)
    output_dir = OUTPUT_BASE_DIR / relative_path
    transcript_path = output_dir / "transcript.json"
    
    # Skip if already processed
    if transcript_path.exists():
        print(f"\n⏭️  Skipping {relative_path} (transcript.json exists)")
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
    
    print(f"   Found {len(audio_files)} audio file(s):")
    for f in audio_files:
        print(f"      - {f.name}")
    
    # Process each audio file, tracking cumulative time offset
    all_file_results = []
    time_offset = 0.0
    
    for audio_file in audio_files:
        segments, info = transcribe_with_word_alignment(audio_file, model)
        
        all_file_results.append({
            "file_name": audio_file.name,
            "segments": segments,
            "info": info,
            "time_offset": time_offset,
        })
        
        time_offset += info.duration
    
    # Format combined transcript data
    transcript_data = format_transcript_data(all_file_results)
    
    # Save transcript JSON
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(transcript_data, f, indent=2, ensure_ascii=False)
    print(f"\n   ✅ Saved transcript: {transcript_path}")
    file_count = len(transcript_data.get('files', [audio_files[0]]))
    print(f"      Total duration: {transcript_data['totalDuration']:.1f}s across {file_count} file(s)")
    
    # Clean up old unused files if they exist
    old_files = ["words.json", "segments.json", "transcript.txt", "audio.wav"]
    for old_file in old_files:
        old_path = output_dir / old_file
        if old_path.exists():
            old_path.unlink()
            print(f"   🧹 Removed unused file: {old_file}")
    
    return True


def main():
    # Parse command line args for specific recording
    specific_recording = None
    if len(sys.argv) > 1:
        specific_recording = sys.argv[1]
        print(f"\n🎯 Processing specific recording: {specific_recording}")
    
    # Check CUDA availability
    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    
    print(f"\n🖥️  Using device: {device}")
    if device == "cuda":
        print(f"   GPU: {torch.cuda.get_device_name(0)}")
        print(f"   Compute type: {compute_type} (optimized for speed)")
    else:
        print("   ⚠️  CUDA not available, using CPU (will be slower)")
    
    # Get recording folders to process
    recording_folders = get_recording_folders(specific_recording)
    if not recording_folders:
        print(f"\n❌ No recording folders found in {SOURCE_AUDIO_DIR}")
        sys.exit(1)
    
    print(f"\n📂 Found {len(recording_folders)} recording(s) to process:")
    for folder in recording_folders:
        rel_path = get_relative_recording_path(folder)
        audio_count = len(get_audio_files_in_folder(folder))
        print(f"   - {rel_path} ({audio_count} audio file(s))")
    
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
    
    # Process each recording folder
    success_count = 0
    for recording_folder in recording_folders:
        if process_recording(recording_folder, model):
            success_count += 1
    
    print("\n" + "=" * 60)
    print(f"✅ TRANSCRIPTION COMPLETE! ({success_count}/{len(recording_folders)} recordings)")
    print("=" * 60)


if __name__ == "__main__":
    main()
