# Audio Processing Scripts

These Python scripts process the memoir audio files for the web application.

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

### Option 1: Run All Scripts

```bash
uv run process_all.py
```

### Option 2: Run Scripts Individually

1. **Transcribe audio** (requires ~10-20 min for 45 min audio)

   ```bash
   uv run 01_transcribe.py
   ```

2. **Generate waveforms** (requires audiowaveform in PATH)

   ```bash
   uv run 02_generate_waveform.py
   ```

3. **Analyze chapters** (requires Ollama running)

   ```bash
   uv run 03_analyze_chapters.py
   ```

## Output Files

All output goes to `/public/audio/christmas1986/`:

| File              | Description                           |
| ----------------- | ------------------------------------- |
| `audio.mp3`       | MP3 audio for web playback (CBR 192k) |
| `transcript.json` | Full transcript with segments         |
| `waveform.json`   | Waveform data for peaks.js            |
| `chapters.json`   | Chapter analysis from LLM             |
| `regions.json`    | Peaks.js region data                  |
| `toc.json`        | Table of contents for UI              |

**Note:** The React app uses `audio.mp3`, `transcript.json`, `waveform.json`, `chapters.json`, `regions.json`, and `toc.json`.

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
