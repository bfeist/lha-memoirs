# Audio Processing Scripts

These Python scripts process memoir audio files for the web application.

## Source Audio Structure

Place your recordings in `/source_audio/` with each recording in its own folder.
Nested folder structures are preserved in the output:

```
source_audio/
├── christmas1986/              # → public/recordings/christmas1986/
│   └── Dad_xmas-1986.wav
├── memoirs/                    # Parent folder (no audio files directly)
│   ├── HF_60/                  # → public/recordings/memoirs/HF_60/
│   │   ├── 1_2.wav
│   │   ├── 3.wav
│   │   └── ...
│   └── Supertape/              # → public/recordings/memoirs/Supertape/
│       ├── Supertape_1.wav
│       ├── Supertape_2.wav
│       └── ...
└── glynn_interview/            # → public/recordings/glynn_interview/
    └── Glynn_interview_1.wav
```

**Notes:**

- Files are processed in natural sort order (1, 2, 10 not 1, 10, 2)
- Multiple audio files in a folder are concatenated into one recording
- Scripts skip recordings that already have output files

## Prerequisites

1. **Python with uv** - Install uv from https://docs.astral.sh/uv/

2. **CUDA (optional but recommended)** - For faster Whisper transcription
   - Requires NVIDIA GPU with CUDA support
   - Install NVIDIA drivers from https://www.nvidia.com/drivers

3. **FFmpeg** - For converting audio to MP3
   - Windows: `winget install ffmpeg`
   - macOS: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`

4. **audiowaveform** - For generating waveform data
   - Download from: https://github.com/bbc/audiowaveform/releases
   - Add to your PATH

5. **Ollama** - For content analysis
   - Install from: https://ollama.ai
   - Pull a model: `ollama pull gemma3:12b`

## Setup

### Option 1: Automated Setup (Recommended)

```bash
# This will install PyTorch with CUDA and all dependencies
uv run setup_env.py
```

### Option 2: Manual Setup

```bash
# 1. Install PyTorch with CUDA support first
uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 2. Install other dependencies
uv pip install -r requirements.txt
```

## Running the Scripts

### Option 1: Process All Recordings

```bash
uv run process_all.py
```

### Option 2: Process a Specific Recording (supports nested paths)

```bash
uv run process_all.py christmas1986
uv run process_all.py memoirs/HF_60
uv run process_all.py memoirs          # processes all recordings under memoirs/
```

### Option 3: Run Scripts Individually

Each script accepts an optional recording path argument:

1. **Transcribe audio** (requires ~10-20 min for 45 min audio)

   ```bash
   uv run 01_transcribe.py [recording_path]
   ```

   Uses WhisperX for transcription with word-level alignment via wav2vec2.

   **Resume from a specific time** (preserves manual edits before that point):

   ```bash
   uv run 01_transcribe.py memoirs/Norm_red --startsecs 1200
   ```

   This is useful when you've manually corrected segments up to a certain point
   and want to re-transcribe only the remaining portion with better alignment.

2. **Correct transcript** (applies domain-specific corrections)

   ```bash
   uv run 02_correct_transcript.py [recording_path]
   ```

3. **Convert to MP3 and generate waveforms**

   ```bash
   uv run 03_generate_waveform.py [recording_path]
   ```

4. **Analyze chapters and stories** (requires Ollama running)

   ```bash
   uv run 04_analyze_chapters.py [recording_path]
   ```

   Identifies both chapters (major sections) and stories (individual anecdotes within chapters).

5. **Find story overlaps** (cross-reference memoir recordings)

   ```bash
   uv run 06_find_story_overlaps.py --save
   ```

## Output Files

Output goes to `/public/recordings/{recording_path}/`:

| File              | Description                           |
| ----------------- | ------------------------------------- |
| `audio.mp3`       | MP3 audio for web playback (CBR 192k) |
| `transcript.json` | Full transcript with segments         |
| `waveform.json`   | Waveform data for peaks.js            |
| `chapters.json`   | Chapter and story analysis from LLM   |

### transcript.json Structure

For single-file recordings:

```json
{
  "segments": [{ "start": 0.0, "end": 5.0, "text": "..." }],
  "totalDuration": 300.0,
  "language": "en"
}
```

For multi-file recordings (source files are concatenated into one MP3):

```json
{
  "segments": [
    { "start": 0.0, "end": 5.0, "text": "...", "fileIndex": 0 },
    { "start": 125.0, "end": 130.0, "text": "...", "fileIndex": 1 }
  ],
  "files": [
    { "startTime": 0.0, "endTime": 120.0, "duration": 120.0 },
    { "startTime": 120.0, "endTime": 300.0, "duration": 180.0 }
  ],
  "totalDuration": 300.0,
  "language": "en"
}
```

The `files` array tracks timing boundaries of the original source files (for UI display like "Part 1", "Part 2").

### chapters.json Structure

```json
{
  "chapters": [{ "title": "Opening", "startTime": 0.0, "description": "..." }],
  "stories": [
    { "title": "Story Title", "startTime": 0.0, "description": "...", "chapterIndex": 0 }
  ],
  "summary": "Brief summary of the recording."
}
```

## Troubleshooting

### CUDA Setup Issues

- Run `uv run diagnose_cuda.py` to check your CUDA installation
- If CUDA is not detected, follow the instructions provided by the diagnostic script
- Most common issue: PyTorch installed without CUDA support
  - Solution: Reinstall with `uv pip install torch --index-url https://download.pytorch.org/whl/cu121`

### Whisper is slow

- Ensure CUDA is properly installed for GPU acceleration (10-20x faster)
- Use a smaller model by editing `01_transcribe.py` (change `large-v3` to `medium` or `small`)
- For 45-minute audio: ~2 minutes with GPU, ~30-45 minutes with CPU

### audiowaveform not found

- Download from GitHub releases and add to PATH
- Verify with: `audiowaveform --version`

### Ollama connection failed

- Start Ollama: `ollama serve`
- Pull a model: `ollama pull gemma3:12b`
