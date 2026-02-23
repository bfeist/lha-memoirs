#!/usr/bin/env python3
"""
Build text + semantic search indexes from all transcript CSV files.
Run with: uv run python scripts/06_build_search_index.py

Processes all transcript.csv files in public/recordings/ (including nested folders)
and generates:

  1. public/search-index.json  — text search index (substring matching, short keys)
  2. public/semantic-search/
       index_meta.json          — model info, dimensions, segment count, build timestamp
       segments.json            — segment metadata with recording/timing info
       embeddings.bin           — float16 binary blob (num_segments × 384 × 2 bytes)

The semantic index enables fully client-side semantic search:
  - The browser loads a matching ONNX model via @huggingface/transformers
  - Embeds the user's query into a 384-dim vector
  - Widens stored float16 embeddings to float32
  - Computes cosine similarity — zero server traffic required

Embeddings are stored as float16 to halve file size with no measurable
impact on ranking quality.

Usage:
  uv run python scripts/06_build_search_index.py            # build both indexes
  uv run python scripts/06_build_search_index.py --force     # rebuild semantic even if exists
  uv run python scripts/06_build_search_index.py --text-only # skip semantic embeddings
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from transcript_utils import load_transcript

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
RECORDINGS_DIR = PROJECT_ROOT / "public" / "recordings"
TEXT_INDEX_PATH = PROJECT_ROOT / "public" / "search-index.json"
SEMANTIC_DIR = PROJECT_ROOT / "public" / "semantic-search"

# ---------------------------------------------------------------------------
# Semantic search constants
# ---------------------------------------------------------------------------
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
BATCH_SIZE = 64


# ---------------------------------------------------------------------------
# Recording title mapping
# ---------------------------------------------------------------------------
def get_recording_title(recording_path: str) -> str:
    """Get a display title for the recording based on its path."""
    title_map = {
        "christmas1986": "Christmas 1986",
        "glynn_interview": "Glynn Interview",
        "LHA_Sr.Hilary": "Sister Hilary Recording",
        "tibbits_cd": "Tibbits CD",
        "memoirs/Norm_red": "Memoirs",
        "memoirs/TDK_D60_edited_through_air": "Memoirs - Draft Telling",
    }
    if recording_path in title_map:
        return title_map[recording_path]
    name = recording_path.split("/")[-1]
    return name.replace("_", " ").title()


def normalize_text(text: str) -> str:
    """Normalize text for case-insensitive searching."""
    return text.lower().strip()


# ---------------------------------------------------------------------------
# Shared: discover transcript files
# ---------------------------------------------------------------------------
def discover_transcripts() -> list[tuple[str, Path]]:
    """Find all transcript.csv files and return (recording_path_str, file_path) pairs."""
    transcript_files_raw = sorted(RECORDINGS_DIR.rglob("transcript.csv"))
    result: list[tuple[str, Path]] = []

    for path in transcript_files_raw:
        recording_dir = path.parent
        rel = recording_dir.relative_to(RECORDINGS_DIR)
        recording_path_str = str(rel).replace("\\", "/")
        result.append((recording_path_str, path))

    return result


# ---------------------------------------------------------------------------
# 1. Text search index (backward-compatible)
# ---------------------------------------------------------------------------
def build_text_index(transcript_files: list[tuple[str, Path]]) -> tuple[dict, int, int]:
    """
    Build the text search index from transcript files.
    Returns (index_dict, transcript_count, segment_count).
    """
    index = []
    transcript_count = 0
    segment_count = 0

    for recording_path_str, transcript_path in transcript_files:
        recording_dir = transcript_path.parent
        transcript_data = load_transcript(recording_dir)
        if not transcript_data:
            print(f"  ⚠️  Skipping {recording_path_str}: Failed to load")
            continue

        segments = transcript_data.get("segments", [])
        if not segments:
            print(f"  ⚠️  Skipping {recording_path_str}: No segments")
            continue

        recording_title = get_recording_title(recording_path_str)
        segments_added = 0

        for i, segment in enumerate(segments):
            text = segment.get("text", "").strip()
            if not text:
                continue

            index.append({
                "r": recording_path_str,
                "t": recording_title,
                "s": segment["start"],
                "e": segment["end"],
                "x": text,
                "n": normalize_text(text),
                "i": i,
            })
            segments_added += 1

        transcript_count += 1
        segment_count += segments_added
        print(f"  ✓ {recording_path_str}: {segments_added} segments")

    return {"index": index}, transcript_count, segment_count


# ---------------------------------------------------------------------------
# 2. Semantic search index
# ---------------------------------------------------------------------------
INDEX_META_FILE = "index_meta.json"
SEGMENTS_FILE = "segments.json"
EMBEDDINGS_FILE = "embeddings.bin"


def load_model():
    """Load the sentence-transformers model (downloads on first run)."""
    from sentence_transformers import SentenceTransformer

    print(f"\n  Loading model: {MODEL_NAME}")
    t0 = time.time()
    model = SentenceTransformer(MODEL_NAME)
    print(f"  Model loaded in {time.time() - t0:.1f}s")
    return model


def encode_texts(model, texts: list[str]) -> np.ndarray:
    """Encode text strings into a 2-D numpy array of embeddings.
    Returns shape (len(texts), EMBEDDING_DIM) with float32 dtype.
    """
    print(f"\n  Encoding {len(texts)} segments (batch_size={BATCH_SIZE})…")
    t0 = time.time()
    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    elapsed = time.time() - t0
    print(f"  Encoding complete in {elapsed:.1f}s ({len(texts) / max(elapsed, 0.01):.0f} seg/s)")
    return embeddings.astype(np.float32)


def save_embeddings_bin(embeddings: np.ndarray, path: Path) -> None:
    """Write embeddings as a flat float16 binary file."""
    emb16 = embeddings.astype(np.float16)
    path.write_bytes(emb16.tobytes())
    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"  Saved embeddings: {path}  ({size_mb:.2f} MB, float16)")


def save_segments_json(segments: list[dict], path: Path) -> None:
    """Write the segment metadata array as compact JSON."""
    for i, seg in enumerate(segments):
        seg["id"] = i
    path.write_text(
        json.dumps(segments, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    size_kb = path.stat().st_size / 1024
    print(f"  Saved segments:   {path}  ({len(segments)} entries, {size_kb:.1f} KB)")


def save_index_meta(num_segments: int, path: Path) -> None:
    """Write the index metadata file."""
    meta = {
        "version": 1,
        "model": MODEL_NAME,
        "embedding_dim": EMBEDDING_DIM,
        "embedding_dtype": "float16",
        "num_segments": num_segments,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "files": {
            "segments": SEGMENTS_FILE,
            "embeddings": EMBEDDINGS_FILE,
        },
    }
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"  Saved metadata:   {path}")


def build_semantic_index(
    transcript_files: list[tuple[str, Path]], *, force: bool = False
) -> None:
    """Build the semantic search index from transcript files."""
    SEMANTIC_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = SEMANTIC_DIR / INDEX_META_FILE
    segments_path = SEMANTIC_DIR / SEGMENTS_FILE
    embeddings_path = SEMANTIC_DIR / EMBEDDINGS_FILE

    if not force and meta_path.exists():
        existing = json.loads(meta_path.read_text(encoding="utf-8"))
        print(f"\n  Existing semantic index has {existing.get('num_segments', '?')} segments")
        print(f"  Built at: {existing.get('built_at', '?')}")
        print("  Use --force to rebuild.")
        return

    # 1. Collect all segments
    all_segments: list[dict] = []
    all_texts: list[str] = []

    for recording_path_str, transcript_path in transcript_files:
        recording_dir = transcript_path.parent
        transcript_data = load_transcript(recording_dir)
        if not transcript_data:
            continue

        segments = transcript_data.get("segments", [])
        if not segments:
            continue

        recording_title = get_recording_title(recording_path_str)

        for i, segment in enumerate(segments):
            text = segment.get("text", "").strip()
            if not text:
                continue

            all_segments.append({
                "r": recording_path_str,
                "t": recording_title,
                "s": segment["start"],
                "e": segment["end"],
                "x": text,
                "i": i,
            })
            all_texts.append(text)

    if not all_segments:
        print("\n  ERROR: No segments found. Nothing to index.")
        return

    print(f"\n  Total segments to embed: {len(all_segments)}")

    # 2. Generate embeddings
    model = load_model()
    embeddings = encode_texts(model, all_texts)

    assert embeddings.shape == (len(all_segments), EMBEDDING_DIM), (
        f"Unexpected shape {embeddings.shape}"
    )

    # 3. Save outputs
    print(f"\n  Writing semantic index to: {SEMANTIC_DIR}")
    save_segments_json(all_segments, segments_path)
    save_embeddings_bin(embeddings, embeddings_path)
    save_index_meta(len(all_segments), meta_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Build text + semantic search indexes from transcript CSV files"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Rebuild the semantic index even if it already exists.",
    )
    parser.add_argument(
        "--text-only", action="store_true",
        help="Only build the text search index, skip semantic embeddings.",
    )
    parser.add_argument(
        "--semantic-only", action="store_true",
        help="Only build the semantic search index, skip text index.",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Build Search Indexes")
    print("=" * 60)
    print(f"  Recordings dir:   {RECORDINGS_DIR}")
    print(f"  Text index:       {TEXT_INDEX_PATH}")
    print(f"  Semantic dir:     {SEMANTIC_DIR}")

    # Find all transcript files
    transcript_files = discover_transcripts()
    print(f"  Transcript files: {len(transcript_files)}")
    print()

    if not transcript_files:
        print("No transcript.csv files found.")
        return

    # --- Text index ---
    if not args.semantic_only:
        print("-" * 60)
        print("Building text search index...")
        print("-" * 60)
        search_index, transcript_count, segment_count = build_text_index(transcript_files)

        with open(TEXT_INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(search_index, f, separators=(",", ":"), ensure_ascii=False)

        file_size = TEXT_INDEX_PATH.stat().st_size
        print(f"\n  Text index: {transcript_count} transcripts, {segment_count} segments")
        print(f"  File size: {file_size / 1024:.1f} KB")
        print("  ✅ Text search index complete")

    # --- Semantic index ---
    if not args.text_only:
        print()
        print("-" * 60)
        print("Building semantic search index...")
        print(f"  Model: {MODEL_NAME} ({EMBEDDING_DIM}d)")
        print("-" * 60)
        build_semantic_index(transcript_files, force=args.force)
        print("  ✅ Semantic search index complete")

    print(f"\n{'=' * 60}")
    print("Done.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
