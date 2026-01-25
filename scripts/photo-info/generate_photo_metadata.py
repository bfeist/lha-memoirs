#!/usr/bin/env python3
"""
Photo Metadata Generator

Scans a directory of images, uses Ollama (Vision) to analyze them,
and generates a JSON file with metadata (caption, date, location, people).

Usage:
    python generate_photo_metadata.py
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
import re

import httpx

# Configuration
OLLAMA_BASE_URL = "http://localhost:11434"
VISION_MODEL = "gemma3:12b"  # or llava:7b, etc.
DEFAULT_INPUT_DIR = Path(__file__).parent.parent.parent / "public" / "photos" / "historical"
DEFAULT_OUTPUT_FILE = Path(__file__).parent.parent.parent / "public" / "photos.json"

# Common locations from the memoir context
COMMON_LOCATIONS = [
    "Iowa", "Remsen", "Sioux City",
    "Saskatchewan", "Halbrite", "Crow Lake", "DeVille", "Midale", "Estevan", "Regina", "Griffin", "Frobisher",
    "North Dakota", "Dawson", "Kenmare",
    "Manitoba", "Winnipegosis",
    "Minnesota", "Minneapolis",
    "Oakville"
]

def unload_all_models() -> None:
    """
    Unload all currently loaded Ollama models to free VRAM.
    """
    print("Unloading existing Ollama models to free VRAM...")
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/ps", timeout=10.0)
        if response.status_code == 200:
            data = response.json()
            models = data.get("models", [])
            for model_info in models:
                model_name = model_info.get("name", "")
                if model_name:
                    print(f"  Unloading {model_name}...")
                    httpx.post(
                        f"{OLLAMA_BASE_URL}/api/generate",
                        json={"model": model_name, "keep_alive": 0},
                        timeout=30.0,
                    )
            if models:
                print(f"  Unloaded {len(models)} model(s)")
                time.sleep(2)
            else:
                print("  No models currently loaded")
    except Exception as e:
        print(f"  Warning: Could not unload models: {e}")

def encode_image(image_path: Path) -> str:
    """Read image and convert to base64 string."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")

def analyze_image(image_path: Path, filename: str) -> dict:
    """
    Send image to Ollama for analysis.
    """
    print(f"  Analyzing: {filename}...")
    
    # Extract year and circa indicator if present
    # Patterns: "1928_", "1928c_", "1920s_"
    year_match = re.match(r"^(\d{4})(c)?", filename)
    if year_match:
        year = year_match.group(1)
        is_circa = year_match.group(2) == "c"
        if is_circa:
            date_str = f"circa {year}"
        else:
            date_str = year
    else:
        # Check for decade pattern
        decade_match = re.match(r"^(\d{4})s", filename)
        if decade_match:
            date_str = f"{decade_match.group(1)}s"
        else:
            date_str = "Unknown"
    
    # Check if LHA is mentioned in filename
    has_lha = "LHA" in filename or "lha" in filename.lower()
    lha_context = "This photo includes Linden 'Lindy' Hilary Achen (LHA)." if has_lha else ""
    
    prompt = f"""Analyze this historical photograph from a family memoir collection.
    
    FILENAME: "{filename}"
    DATE: {date_str}
    {lha_context}

    CONTEXT:
    This is from the memoir collection of Linden "Lindy" Hilary Achen (LHA), a power line construction foreman.
    Timeline: Born 1902 in Iowa, moved to Saskatchewan (Halbrite) as a child, worked across Saskatchewan and North Dakota.
    Wife: Phyllis. Sister: Hilary.
    
    Common locations: {', '.join(COMMON_LOCATIONS)}.

    TASK:
    Since date and location are separate fields, the caption should ONLY include important additional details.
    
    Caption guidelines:
    - Leave EMPTY ("") if there's no important additional context
    - If notable, include WHO (e.g., "Lindy and Phyllis", "Lindy's mother")
    - If relevant, include WHAT (e.g., "Model A Ford", "Power line crew", "Family reunion")
    - Keep it VERY short - 2-5 words maximum
    - Do NOT repeat date or location info
    
    Also determine:
    - "location": Extract from filename or describe visible setting (e.g., "Midale, Saskatchewan" or "Unknown")

    Return ONLY valid JSON with fields: caption, location

    Example captions:
    - "Lindy and Phyllis"
    - "Model A Ford"
    - "Power line crew"
    - "Family reunion"
    - "" (empty if nothing important to add)
    """

    try:
        b64_image = encode_image(image_path)
        
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": VISION_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                        "images": [b64_image],
                    }
                ],
                "stream": False,
                "options": {
                    "temperature": 0.2, # Low temperature for more deterministic/factual output
                }
            },
            timeout=60.0,
        )
        response.raise_for_status()
        
        result = response.json()
        content = result.get("message", {}).get("content", "")
        
        # Clean markdown
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            print(f"    Failed to parse JSON response. Raw: {content[:50]}...")
            data = {
                "caption": "",
                "location": "Unknown"
            }
        
        # Add date field separately
        data["date"] = date_str
            
        return data

    except Exception as e:
        print(f"    Error analyzing image: {e}")
        return {
            "caption": "",
            "date": date_str,
            "location": "Unknown"
        }

def main():
    parser = argparse.ArgumentParser(description="Generate metadata for photos")
    parser.add_argument("--input", "-i", type=Path, default=DEFAULT_INPUT_DIR, help="Input directory containing photos")
    parser.add_argument("--output", "-o", type=Path, default=DEFAULT_OUTPUT_FILE, help="Output JSON file")
    
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"Error: Input directory {args.input} does not exist.")
        sys.exit(1)

    print(f"Scanning {args.input}...")
    
    # Load existing photo metadata if it exists
    existing_photos = {}
    if args.output.exists():
        try:
            with open(args.output, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
                for photo in existing_data.get("photos", []):
                    existing_photos[photo["filename"]] = photo
            print(f"Loaded {len(existing_photos)} existing photo entries")
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Could not load existing metadata: {e}")
    
    # Attempt to unload other models to ensure vision model fits
    unload_all_models()

    photos = []
    
    # Sort files to ensure deterministic order (and group similar dates)
    files = sorted([f for f in args.input.iterdir() if f.is_file()])
    
    for file_path in files:
        if file_path.name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            # Skip if already processed
            if file_path.name in existing_photos:
                print(f"  Skipping {file_path.name} (already processed)")
                photos.append(existing_photos[file_path.name])
                continue
            
            # Determine public relative path
            # Assuming standard structure: .../public/photos/historical/image.jpg -> /photos/historical/image.jpg
            try:
                # Find 'public' component and slice from there
                parts = file_path.parts
                if "public" in parts:
                    idx = parts.index("public")
                    # Construct path starting with /
                    rel_parts = parts[idx+1:]
                    web_path = "/" + "/".join(rel_parts)
                else:
                    web_path = f"/photos/historical/{file_path.name}" # Fallback
            except ValueError:
                 web_path = f"/photos/historical/{file_path.name}"

            metadata = analyze_image(file_path, file_path.name)
            
            # Add file info
            photo_entry = {
                "filename": file_path.stem,  # Just the stub, no extension
                **metadata
            }
            
            photos.append(photo_entry)
            
            # Create a backup/intermediate save
            with open(args.output.with_suffix(".tmp.json"), "w", encoding="utf-8") as f:
                json.dump({"photos": photos}, f, indent=2)

    # Final write
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump({"photos": photos}, f, indent=2)
    
    print(f"Done! Processed {len(photos)} photos. Saved to {args.output}")
    # Remove tmp file
    if args.output.with_suffix(".tmp.json").exists():
        os.remove(args.output.with_suffix(".tmp.json"))

if __name__ == "__main__":
    main()
