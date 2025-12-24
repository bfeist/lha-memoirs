"""
Master script to run all processing steps in order.
Run with: uv run process_all.py

This script will:
1. Transcribe audio with Whisper (word-level alignment)
2. Generate waveform data with audiowaveform
3. Analyze content and create chapters with Ollama
"""

import subprocess
import sys
from pathlib import Path

print("=" * 60)
print("LHA MEMOIRS - AUDIO PROCESSING PIPELINE")
print("=" * 60)
print("\nThis will process your grandfather's recordings.")
print("Each step may take several minutes depending on audio length.\n")

SCRIPT_DIR = Path(__file__).parent

# Scripts to run in order
SCRIPTS = [
    ("01_transcribe.py", "Transcribing audio with Whisper..."),
    ("02_generate_waveform.py", "Generating waveform data..."),
    ("03_analyze_chapters.py", "Analyzing content for chapters..."),
]


def run_script(script_name: str, description: str) -> bool:
    """Run a script and return success status."""
    print("\n" + "=" * 60)
    print(f"📌 STEP: {description}")
    print("=" * 60)
    
    script_path = SCRIPT_DIR / script_name
    
    if not script_path.exists():
        print(f"❌ Script not found: {script_path}")
        return False
    
    # Run the script with the same Python interpreter
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=SCRIPT_DIR,
    )
    
    return result.returncode == 0


def main():
    # Check prerequisites
    print("Checking prerequisites...\n")
    
    # Check for source audio
    source_audio = SCRIPT_DIR.parent / "source_audio"
    audio_files = list(source_audio.glob("*.wav")) + list(source_audio.glob("*.mp3"))
    
    if not audio_files:
        print("❌ No audio files found in /source_audio/")
        print("   Please add your audio files and try again.")
        sys.exit(1)
    
    print(f"✅ Found {len(audio_files)} audio file(s)")
    for f in audio_files:
        print(f"   - {f.name}")
    
    # Run each script
    failed = []
    for script_name, description in SCRIPTS:
        success = run_script(script_name, description)
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
    output_dir = SCRIPT_DIR.parent / "public" / "audio" / "christmas1986"
    if output_dir.exists():
        print(f"\n📂 Output files in {output_dir}:")
        for f in sorted(output_dir.iterdir()):
            size_kb = f.stat().st_size / 1024
            print(f"   - {f.name} ({size_kb:.1f} KB)")
    
    print("\n" + "=" * 60)
    print("You can now run the React app with: npm run dev")
    print("=" * 60)


if __name__ == "__main__":
    main()
