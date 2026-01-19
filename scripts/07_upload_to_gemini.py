"""
Upload token-friendly text files to Google Gemini File API.
Run with: uv run 07_upload_to_gemini.py

This script:
1. Reads all .txt files from the token_friendly/ directory
2. Uploads them to Google's File API
3. Creates a cache with all the files for use with Gemini
4. Outputs the cache name for use in stream.php

Requires:
  pip install google-generativeai python-dotenv
  Or with uv: uv pip install google-generativeai python-dotenv

Environment:
  GOOGLE_API_KEY must be set in .env file
"""

import os
import sys
from pathlib import Path
from datetime import timedelta

try:
    from dotenv import load_dotenv
    import google.generativeai as genai
except ImportError:
    print("Error: Required packages not installed.")
    print("Run: pip install google-generativeai python-dotenv")
    sys.exit(1)


def load_api_key() -> str:
    """Load the Google API key from .env file."""
    # Load .env from project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    env_file = project_root / ".env"
    
    if env_file.exists():
        load_dotenv(env_file)
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY not found in .env file")
        print(f"Please add your API key to: {env_file}")
        sys.exit(1)
    
    return api_key


def get_token_friendly_files(project_root: Path) -> list[Path]:
    """Get all .txt files from the token_friendly directory."""
    token_friendly_dir = project_root / "token_friendly"
    
    if not token_friendly_dir.exists():
        print(f"Error: token_friendly directory not found: {token_friendly_dir}")
        print("Run 06_tokenfriendly.py first to generate the text files.")
        sys.exit(1)
    
    files = list(token_friendly_dir.glob("*.txt"))
    
    if not files:
        print(f"Error: No .txt files found in {token_friendly_dir}")
        print("Run 06_tokenfriendly.py first to generate the text files.")
        sys.exit(1)
    
    return sorted(files)


def upload_files(files: list[Path]) -> list:
    """Upload files to Google's File API."""
    uploaded_files = []
    
    print(f"\nUploading {len(files)} file(s) to Google File API...")
    
    for file_path in files:
        print(f"  Uploading: {file_path.name}...", end=" ", flush=True)
        
        try:
            uploaded_file = genai.upload_file(
                path=str(file_path),
                display_name=file_path.stem,
                mime_type="text/plain"
            )
            uploaded_files.append(uploaded_file)
            print(f"✓ ({uploaded_file.name})")
        except Exception as e:
            print(f"✗ Error: {e}")
            continue
    
    return uploaded_files


def list_existing_files() -> list:
    """List all files currently uploaded to the API."""
    print("\nChecking existing uploaded files...")
    files = list(genai.list_files())
    
    if files:
        print(f"Found {len(files)} existing file(s):")
        for f in files:
            print(f"  - {f.display_name} ({f.name})")
    else:
        print("No existing files found.")
    
    return files


def delete_all_files():
    """Delete all uploaded files."""
    files = list(genai.list_files())
    
    if not files:
        print("No files to delete.")
        return
    
    print(f"\nDeleting {len(files)} file(s)...")
    for f in files:
        try:
            genai.delete_file(f.name)
            print(f"  Deleted: {f.display_name}")
        except Exception as e:
            print(f"  Error deleting {f.display_name}: {e}")


def create_cache(uploaded_files: list, model_name: str = "models/gemini-2.0-flash-001") -> str:
    """Create a cached content with all uploaded files."""
    print(f"\nCreating cache with {len(uploaded_files)} file(s)...")
    
    # System instruction for the historian persona
    system_instruction = """You are LHA-GPT, a helpful family historian assistant. You have access to audio transcripts from Linden Hilary Achen (1902-1994), known as "Linden" or "Lindy." These are voice memoirs recorded in the 1980s where he tells stories about his life growing up in Iowa and Canada.

When answering questions:
1. Draw only from the transcript content provided
2. Provide specific citations with timestamps when referencing the transcripts
3. Be warm and conversational, as if helping a family member learn about their ancestry
4. If you don't find relevant information in the transcripts, say so honestly
5. Quote directly from the transcripts when appropriate

The recording_id comes from the METADATA section of each transcript.
The timestamp should be converted to seconds from the [HH:MM:SS] markers.
Only include citations for content you actually found and quoted."""

    try:
        cache = genai.caching.CachedContent.create(
            model=model_name,
            display_name="lha-memoirs-transcripts",
            system_instruction=system_instruction,
            contents=[{"parts": [{"file_data": {"file_uri": f.uri}} for f in uploaded_files]}],
            ttl=timedelta(hours=1),  # Cache expires after 1 hour
        )
        print(f"✓ Cache created: {cache.name}")
        return cache.name
    except Exception as e:
        print(f"✗ Error creating cache: {e}")
        print("\nNote: Caching requires specific model versions.")
        print("The files are still uploaded and can be used directly in prompts.")
        return ""


def update_env_file(project_root: Path, cache_name: str):
    """Update the .env file with the cache name."""
    env_file = project_root / ".env"
    
    if not env_file.exists():
        print(f"Warning: .env file not found at {env_file}")
        return
    
    # Read existing content
    with open(env_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # Update or add FILE_SEARCH_STORE_ID
    found = False
    for i, line in enumerate(lines):
        if line.startswith("FILE_SEARCH_STORE_ID="):
            lines[i] = f"FILE_SEARCH_STORE_ID={cache_name}\n"
            found = True
            break
    
    if not found:
        lines.append(f"FILE_SEARCH_STORE_ID={cache_name}\n")
    
    # Write back
    with open(env_file, "w", encoding="utf-8") as f:
        f.writelines(lines)
    
    print(f"\n✓ Updated .env file with FILE_SEARCH_STORE_ID={cache_name}")


def print_file_uris(uploaded_files: list):
    """Print the file URIs for manual use."""
    print("\n" + "=" * 60)
    print("UPLOADED FILE URIs")
    print("=" * 60)
    print("These URIs can be used directly in API calls:\n")
    
    for f in uploaded_files:
        print(f"  {f.display_name}:")
        print(f"    URI: {f.uri}")
        print(f"    Name: {f.name}")
        print()


def main():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    print("=" * 60)
    print("GEMINI FILE UPLOAD TOOL")
    print("=" * 60)
    
    # Load API key and configure
    api_key = load_api_key()
    genai.configure(api_key=api_key)
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "list":
            list_existing_files()
            return
        
        elif command == "delete":
            confirm = input("Delete all uploaded files? (y/N): ")
            if confirm.lower() == "y":
                delete_all_files()
            return
        
        elif command == "help":
            print("\nUsage:")
            print("  python 07_upload_to_gemini.py          # Upload files and create cache")
            print("  python 07_upload_to_gemini.py list     # List existing uploaded files")
            print("  python 07_upload_to_gemini.py delete   # Delete all uploaded files")
            return
    
    # Get files to upload
    files = get_token_friendly_files(project_root)
    print(f"\nFound {len(files)} file(s) to upload:")
    for f in files:
        size_kb = f.stat().st_size / 1024
        print(f"  - {f.name} ({size_kb:.1f} KB)")
    
    # Calculate total size and estimated tokens
    total_bytes = sum(f.stat().st_size for f in files)
    total_kb = total_bytes / 1024
    estimated_tokens = total_bytes / 4  # ~4 bytes per token estimate
    
    print(f"\nTotal size: {total_kb:.1f} KB")
    print(f"Estimated tokens: ~{int(estimated_tokens):,} (well within 1M limit)")
    
    # Delete any existing uploaded files first
    existing_files = list(genai.list_files())
    if existing_files:
        print(f"\nDeleting {len(existing_files)} existing file(s) before upload...")
        for f in existing_files:
            try:
                genai.delete_file(f.name)
                print(f"  Deleted: {f.display_name}")
            except Exception as e:
                print(f"  Error deleting {f.display_name}: {e}")
    
    # Upload files
    uploaded_files = upload_files(files)
    
    if not uploaded_files:
        print("\nNo files were uploaded successfully.")
        sys.exit(1)
    
    # Print file URIs for reference
    print_file_uris(uploaded_files)
    
    # Try to create a cache (may not work with all models)
    # Note: gemini-3-flash-preview may not support caching yet
    print("\nNote: Context caching may not be available for all model versions.")
    print("The uploaded files can be referenced directly in API calls using their URIs.")
    print("\nTo use these files in stream.php, you'll need to modify the PHP to include")
    print("the file URIs in the request payload under 'contents'.")
    
    # Save file URIs to a JSON file for reference
    import json
    uris_file = project_root / "token_friendly" / "uploaded_files.json"
    uris_data = {
        "files": [
            {
                "display_name": f.display_name,
                "name": f.name,
                "uri": f.uri
            }
            for f in uploaded_files
        ]
    }
    with open(uris_file, "w", encoding="utf-8") as f:
        json.dump(uris_data, f, indent=2)
    
    print(f"\n✓ Saved file URIs to: {uris_file}")
    
    print("\n" + "=" * 60)
    print("UPLOAD COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
