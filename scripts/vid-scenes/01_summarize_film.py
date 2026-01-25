#!/usr/bin/env python3
"""
Video Scene Detection and Description Pipeline

Uses PySceneDetect for scene/shot detection and Ollama vision models
to generate structured descriptions of each scene.

Usage:
    python summarize_film.py /path/to/video.mp4
    python summarize_film.py /path/to/folder  # Process all .mp4 files
"""

import argparse
import base64
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
from scenedetect import open_video, SceneManager, ContentDetector

# Configuration
OLLAMA_BASE_URL = "http://localhost:11434"
VISION_MODEL = "gemma3:12b"  # Vision-language model (gemma3:12b has better detail than llava:7b)
OUTPUT_DIR = Path(__file__).parent / "output"

# Scene detection threshold (lower = more sensitive, default ~27)
SCENE_THRESHOLD = 27.0


def unload_all_models() -> None:
    """
    Unload all currently loaded Ollama models to free VRAM.
    This helps when running close to GPU memory limits.
    """
    print("Unloading existing Ollama models to free VRAM...")
    try:
        # Get list of running models
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/ps", timeout=10.0)
        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            for model_info in models:
                model_name = model_info.get("name", "")
                if model_name:
                    print(f"  Unloading {model_name}...")
                    # Send a request with keep_alive=0 to unload
                    httpx.post(
                        f"{OLLAMA_BASE_URL}/api/generate",
                        json={"model": model_name, "keep_alive": 0},
                        timeout=30.0,
                    )
            if models:
                print(f"  Unloaded {len(models)} model(s)")
                time.sleep(2)  # Give GPU time to release memory
            else:
                print("  No models currently loaded")
    except Exception as e:
        print(f"  Warning: Could not unload models: {e}")


def detect_scenes(video_path: Path) -> list[tuple[float, float]]:
    """
    Detect scenes in a video using PySceneDetect.
    Returns list of (start_seconds, end_seconds) tuples.
    """
    print(f"  Detecting scenes in {video_path.name}...")
    
    video = open_video(str(video_path))
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=SCENE_THRESHOLD))
    
    scene_manager.detect_scenes(video)
    scene_list = scene_manager.get_scene_list()
    
    # Convert to seconds
    scenes = []
    for start, end in scene_list:
        scenes.append((start.get_seconds(), end.get_seconds()))
    
    print(f"  Found {len(scenes)} scenes")
    return scenes


def extract_frames(video_path: Path, start_sec: float, end_sec: float, num_frames: int = 3) -> list[bytes]:
    """
    Extract frames from a scene using ffmpeg.
    Returns list of JPEG bytes for start/middle/end frames.
    """
    frames = []
    duration = end_sec - start_sec
    
    # Calculate timestamps for start, middle, end
    if num_frames == 3:
        timestamps = [
            start_sec + 0.1,  # Just after start
            start_sec + duration / 2,  # Middle
            end_sec - 0.1,  # Just before end
        ]
    else:
        timestamps = [start_sec + duration / 2]  # Just middle
    
    for ts in timestamps:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Extract single frame at timestamp
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(ts),
                "-i", str(video_path),
                "-vframes", "1",
                "-q:v", "2",  # High quality JPEG
                tmp_path
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            
            with open(tmp_path, "rb") as f:
                frames.append(f.read())
        except subprocess.CalledProcessError:
            pass  # Frame extraction failed, skip
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    
    return frames


def describe_scene_with_ollama(frames: list[bytes], scene_index: int, start_sec: float, end_sec: float, video_name: str = "") -> dict:
    """
    Send frames to Ollama vision model and get structured description.
    """
    # Convert frames to base64
    images_b64 = [base64.b64encode(f).decode("utf-8") for f in frames]
    
    # Check if this is the Grama/Grampa personal footage vs power line footage
    is_personal = "grama" in video_name.lower() or "grampa" in video_name.lower() or "flowers" in video_name.lower()
    
    if is_personal:
        prompt = """Analyze these frames extracted from a video scene of personal family footage.

IMPORTANT: These are frames from VIDEO FOOTAGE, not still photographs. Describe the scene as video/motion content.

This footage shows Linden "Lindy" Hilary Achen (1902-1994) and his wife Phyllis Achen. Lindy was a power lineman and line construction foreman in Saskatchewan and the US Midwest from the 1920s-1960s.

Return a JSON object with these fields:
{
    "title": "5-10 word descriptive title",
    "summary": "1-3 sentence description of what's happening",
    "details": ["bullet point 1", "bullet point 2", ...],
    "tags": ["keyword1", "keyword2", ...],
    "people_visible": ["Lindy Achen", "Phyllis Achen", or "unknown"],
    "era_estimate": "rough time period (e.g., '1950s', '1960s-1970s')"
}

Return ONLY valid JSON, no other text."""
    else:
        prompt = """Analyze these frames extracted from a video scene of archival power line construction footage.

IMPORTANT: These are frames from VIDEO FOOTAGE shot with a movie camera, not still photographs. Describe the scene as video/motion content showing workers in action.

CONTEXT: This footage was shot by Linden "Lindy" Achen, a power lineman and line construction foreman who worked in Saskatchewan, Canada and the US Midwest from the 1920s-1960s. The workers' names are unknown.

This is POWER LINE CONSTRUCTION footage. Look specifically for:
- Pole setting: workers using pike poles, cant hooks, or trucks to raise wooden utility poles
- Hole digging: hand-dug holes or boring machines/augers for pole placement  
- Cross arm framing: attaching wooden cross arms to poles with bolts
- Climbing: linemen with climbing spurs/gaffs and safety belts ascending poles
- Stringing wire: pulling conductors between poles, using tensioners
- Insulators: glass or porcelain insulators on cross arms
- Guy wires and anchors: stabilizing poles with wire and ground anchors
- Transformers: installing or working on pole-mounted transformers
- Substations: electrical switching equipment
- Vehicles: line trucks, boom trucks, auger trucks from the era
- Restubbing: replacing rotted pole bases by splicing new wood

Return a JSON object with these fields:
{
    "title": "5-10 word descriptive title for this scene",
    "summary": "1-3 sentence description of the power line work being performed",
    "activity_type": "one of: pole_setting, hole_digging, climbing, stringing, cross_arms, transformer, substation, vehicles, restubbing, general_construction, unknown",
    "details": ["specific observations about equipment, techniques, or setting"],
    "equipment_visible": ["list specific equipment: pike poles, boring machine, line truck, climbing gear, etc."],
    "tags": ["searchable keywords for later matching with audio transcripts"],
    "worker_count": "number of workers visible or 'unclear'",
    "era_estimate": "rough time period based on vehicles, equipment, clothing (1920s-1960s range)"
}

Return ONLY valid JSON, no other text."""

    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": VISION_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": images_b64,
                    }
                ],
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "num_ctx": 2048,  # Reduce context window to save VRAM
                }
            },
            timeout=180.0,
        )
        response.raise_for_status()
        
        result = response.json()
        content = result.get("message", {}).get("content", "")
        
        # Try to parse JSON from response
        # Sometimes the model wraps it in markdown code blocks
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        try:
            scene_data = json.loads(content)
        except json.JSONDecodeError:
            scene_data = {
                "title": "Scene analysis failed",
                "summary": content[:500] if content else "No response",
                "details": [],
                "tags": [],
                "uncertainties": ["JSON parsing failed"],
                "era_estimate": "unknown"
            }
        
        # Add timing metadata
        scene_data["scene_index"] = scene_index
        scene_data["start_seconds"] = round(start_sec, 2)
        scene_data["end_seconds"] = round(end_sec, 2)
        scene_data["duration_seconds"] = round(end_sec - start_sec, 2)
        
        return scene_data
        
    except Exception as e:
        return {
            "scene_index": scene_index,
            "start_seconds": round(start_sec, 2),
            "end_seconds": round(end_sec, 2),
            "duration_seconds": round(end_sec - start_sec, 2),
            "title": "Error analyzing scene",
            "summary": str(e),
            "details": [],
            "tags": [],
            "uncertainties": ["Analysis failed"],
            "era_estimate": "unknown"
        }


def format_timestamp(seconds: float) -> str:
    """Convert seconds to MM:SS or HH:MM:SS format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def process_video(video_path: Path, output_dir: Path) -> dict:
    """
    Process a single video: detect scenes, extract frames, describe each scene.
    Returns the video's scene data dict (no per-video file output).
    """
    print(f"\nProcessing: {video_path.name}")
    
    # Detect scenes
    scenes = detect_scenes(video_path)
    
    if not scenes:
        print("  No scenes detected, treating entire video as one scene")
        # Get video duration
        cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "json",
            str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            duration = float(json.loads(result.stdout)["format"]["duration"])
        except (json.JSONDecodeError, KeyError):
            duration = 60.0  # Fallback
        scenes = [(0.0, duration)]
    
    # Initialize result structure
    result = {
        "video_file": video_path.name,
        "video_path": str(video_path),
        "total_scenes": len(scenes),
        "scenes": []
    }
    
    # Process each scene
    for i, (start, end) in enumerate(scenes):
        print(f"  Scene {i+1}/{len(scenes)}: {format_timestamp(start)} - {format_timestamp(end)}")
        
        # Extract frames
        frames = extract_frames(video_path, start, end, num_frames=3)
        
        if not frames:
            print(f"    Warning: Could not extract frames, skipping")
            continue
        
        # Describe with vision model
        print(f"    Analyzing with {VISION_MODEL}...")
        scene_data = describe_scene_with_ollama(frames, i, start, end, video_path.name)
        result["scenes"].append(scene_data)
        
        print(f"    Title: {scene_data.get('title', 'N/A')}")
    
    return result


def main():
    global VISION_MODEL
    
    parser = argparse.ArgumentParser(description="Detect and describe video scenes")
    parser.add_argument("input_path", help="Path to video file or folder containing .mp4 files")
    parser.add_argument("--output", "-o", help="Output directory (default: ./output)")
    parser.add_argument("--model", "-m", default=VISION_MODEL, help=f"Ollama vision model (default: {VISION_MODEL})")
    parser.add_argument("--no-unload", action="store_true", help="Skip unloading other models (use if VRAM is not an issue)")
    args = parser.parse_args()
    
    VISION_MODEL = args.model
    
    # Free up VRAM by unloading other models
    if not args.no_unload:
        unload_all_models()
    
    input_path = Path(args.input_path)
    output_dir = Path(args.output) if args.output else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Collect video files
    if input_path.is_file():
        video_files = [input_path]
    elif input_path.is_dir():
        video_files = list(input_path.glob("*.mp4"))
    else:
        print(f"Error: {input_path} not found")
        sys.exit(1)
    
    if not video_files:
        print(f"No .mp4 files found in {input_path}")
        sys.exit(1)
    
    print(f"Found {len(video_files)} video(s) to process")
    print(f"Output directory: {output_dir}")
    print(f"Vision model: {VISION_MODEL}")
    
    # Process each video (JSON is written incrementally inside process_video)
    all_results = []
    for video_path in video_files:
        result = process_video(video_path, output_dir)
        all_results.append(result)
    
    # Save combined results
    combined_file = output_dir / "video_scene_cards.json"
    with open(combined_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nCombined results saved to: {combined_file}")


if __name__ == "__main__":
    main()
