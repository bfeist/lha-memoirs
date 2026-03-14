#!/usr/bin/env python3
"""
Side-by-side benchmark comparing N Ollama models for the LHA Memoirs RAG application.

Reads transcript CSVs directly – no server required.
All models are queried concurrently per test case.
Raw results are saved as JSON alongside the markdown so models can be added later.

Usage:
    python benchmark_models.py                          # full run with default models
    python benchmark_models.py --models gemma3:12b qwen3.5:4b gpt-oss:20b
    python benchmark_models.py --add-model qwen3.5:9b  # insert into existing results
    python benchmark_models.py --queries "What was Lindy's childhood like?"
    python benchmark_models.py --output my_report.md
"""

import asyncio
import json
import time
import csv
import argparse
import re
from pathlib import Path
from datetime import datetime

import httpx
from dotenv import load_dotenv
import os

# Load .env from same directory as this script
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# ── Configuration ─────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODELS = ["gemma3:12b", "qwen3.5:4b", "gpt-oss:20b"]
TEMPERATURE = 0.3

# Paths
PUBLIC_DIR = Path(__file__).parent.parent.parent / "public" / "recordings"

# Recording ID mapping (matches rag_server.py)
RECORDING_ID_MAP = {
    "memoirs/Norm_red": "memoirs_main",
    "memoirs/TDK_D60_edited_through_air": "memoirs_second_telling",
    "christmas1986": "christmas1986",
    "glynn_interview": "glynn_interview",
    "LHA_Sr.Hilary": "lha_sr_hilary",
}

# ── System prompt (keep in sync with rag_server.py) ──────────────────────────
SYSTEM_PROMPT = """You are a family historian assistant with access to audio transcripts from Linden Hilary Achen (1902-1994). These voice memoirs were recorded by Lindy Achen in the 1980s. Lindy is a male.

USE LOW REASONING EFFORT - answer quickly and directly.

CRITICAL CITATION RULES:
1. ALWAYS cite your sources using this EXACT format: [Source: recording_id, Time: MM:SS] or [Source: recording_id, Time: MM:SS, Segments: N]
2. Include citations at the END of each fact or sentence that comes from the context.
3. Use the EXACT recording_id and timestamp from the context headers.
4. OPTIONAL: Add 'Segments: N' to specify how many transcript segments (sentences) to play.
   - Use Segments: 1-2 for single facts or quotes
   - Use Segments: 3-5 for short anecdotes (this is the default)
   - Use Segments: 6-10 for complete stories or extended narratives
   - Omit 'Segments' to use the default of 3

Example: "Lindy bought his Model T Ford for about $350. [Source: memoirs_main, Time: 45:23, Segments: 2] The car was a coupe and he referred to it as a 'four-grocer'. [Source: memoirs_main, Time: 46:10] Later, he tells the full story about falling asleep at the wheel. [Source: memoirs_main, Time: 47:00, Segments: 8]"

OTHER RULES:
- Answer ONLY from the provided context. If info isn't there, say so.
- Look through ALL provided context before answering.
- Include specific details like names, places, dates, vehicle models when mentioned.
- Refer to Lindy by name when appropriate - use "Lindy" not "the narrator."
- Write in natural prose, not lists or tables.
"""

# ── Default test cases ────────────────────────────────────────────────────────
# Each entry: query + one or more (rec_rel_path, start_sec, end_sec) context specs.
# Time ranges are pre-selected to hit relevant portions of the transcript.
DEFAULT_TEST_CASES = [
    {
        "query": "Where was Lindy born and what were the circumstances of his early life?",
        "context_spec": [("memoirs/Norm_red", 37, 250)],
    },
    {
        "query": "Why did Lindy's family move to Canada and what was that experience like?",
        "context_spec": [("memoirs/Norm_red", 80, 400)],
    },
    {
        "query": "What kind of farm work did the family do?",
        "context_spec": [("memoirs/Norm_red", 300, 600)],
    },
    {
        "query": "Tell me about Lindy's education and school years.",
        "context_spec": [("memoirs/Norm_red", 500, 900)],
    },
    {
        "query": "What cars or vehicles did Lindy own or talk about?",
        "context_spec": [("memoirs/Norm_red", 2400, 3500)],
    },
]

# ── Transcript helpers ────────────────────────────────────────────────────────

def format_timestamp(seconds: float) -> str:
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins}:{secs:02d}"


def load_transcript_slice(rec_rel_path: str, start_sec: float, end_sec: float) -> list[dict]:
    """Return rows from transcript.csv whose start time falls in [start_sec, end_sec]."""
    csv_path = PUBLIC_DIR / rec_rel_path / "transcript.csv"
    if not csv_path.exists():
        return []
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="|")
        for row in reader:
            try:
                row_start = float(row["start"])
            except (ValueError, KeyError):
                continue
            if start_sec <= row_start <= end_sec:
                rows.append({"start": row_start, "text": row["text"].strip()})
    return rows


def build_context(context_spec: list) -> str:
    """
    Build a RAG-style context string from (rec_rel_path, start_sec, end_sec) tuples.
    Splits the sliced transcript into ~90-second chunks (≈ what rag_server.py does).
    Returns at most 6 chunks total to mirror the server's docs_for_llm[:6] cap.
    """
    CHUNK_SECONDS = 90
    MAX_CHUNKS = 6
    all_chunks = []

    for rec_rel_path, start_sec, end_sec in context_spec:
        rec_id = RECORDING_ID_MAP.get(rec_rel_path, rec_rel_path)
        rows = load_transcript_slice(rec_rel_path, start_sec, end_sec)
        if not rows:
            all_chunks.append(f"[Source: {rec_id}, Time: {format_timestamp(start_sec)}]\n[No transcript in this range]")
            continue

        # Group rows into CHUNK_SECONDS-wide buckets
        chunk_start = rows[0]["start"]
        current_bucket: list[str] = []
        for row in rows:
            if row["start"] - chunk_start > CHUNK_SECONDS and current_bucket:
                ts = format_timestamp(chunk_start)
                all_chunks.append(f"[Source: {rec_id}, Time: {ts}]\n{' '.join(current_bucket)}")
                chunk_start = row["start"]
                current_bucket = [row["text"]]
            else:
                current_bucket.append(row["text"])

        # Flush last bucket
        if current_bucket:
            ts = format_timestamp(chunk_start)
            all_chunks.append(f"[Source: {rec_id}, Time: {ts}]\n{' '.join(current_bucket)}")

    return "\n\n---\n\n".join(all_chunks[:MAX_CHUNKS])


def build_user_message(query: str, context: str) -> str:
    return (
        f"Context from transcripts:\n\n{context}\n\n"
        f"---\n\nQuestion: {query}\n\n"
        "Look through ALL the context above and provide a complete answer."
    )


# ── Ollama call ───────────────────────────────────────────────────────────────

async def query_model(
    client: httpx.AsyncClient,
    model: str,
    system_prompt: str,
    user_message: str,
) -> dict:
    """Stream a response from Ollama; return text, timing, and quality metrics."""
    start = time.perf_counter()
    full_text = ""
    thinking_text = ""
    first_token_time: float | None = None

    try:
        async with client.stream(
            "POST",
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                "stream": True,
                "options": {"temperature": TEMPERATURE},
            },
            timeout=180.0,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    msg = data.get("message", {})
                    thinking_chunk = msg.get("thinking", "")
                    content_chunk = msg.get("content", "")
                    if thinking_chunk:
                        thinking_text += thinking_chunk
                    if content_chunk:
                        if first_token_time is None:
                            first_token_time = time.perf_counter() - start
                        full_text += content_chunk
                except json.JSONDecodeError:
                    continue

    except httpx.HTTPError as e:
        elapsed = time.perf_counter() - start
        return {
            "model": model,
            "text": f"[ERROR: {e}]",
            "thinking": "",
            "elapsed": elapsed,
            "ttft": None,
            "word_count": 0,
            "citation_count": 0,
            "error": str(e),
        }

    elapsed = time.perf_counter() - start
    word_count = len(full_text.split())
    citation_count = len(re.findall(r"\[Source:", full_text))

    return {
        "model": model,
        "text": full_text,
        "thinking": thinking_text,
        "elapsed": elapsed,
        "ttft": first_token_time,
        "word_count": word_count,
        "citation_count": citation_count,
        "error": None,
    }


# ── Test runner ───────────────────────────────────────────────────────────────

async def run_test_case(
    client: httpx.AsyncClient,
    case: dict,
    models: list[str],
    index: int,
    total: int,
) -> dict:
    """Run one query against all models concurrently and return results."""
    query = case["query"]
    context = build_context(case["context_spec"])
    user_message = build_user_message(query, context)

    print(f"\n{'=' * 70}")
    print(f"Query {index}/{total}: {query}")
    print(f"{'=' * 70}")
    print(f"Running {len(models)} models concurrently…")

    model_results = await asyncio.gather(
        *[query_model(client, m, SYSTEM_PROMPT, user_message) for m in models]
    )

    for r in model_results:
        status = "✗ ERROR" if r["error"] else "✓"
        ttft_str = f" | TTFT: {r['ttft']:.1f}s" if r["ttft"] is not None else ""
        print(f"\n  [{status}] {r['model']}")
        print(f"       Total: {r['elapsed']:.1f}s{ttft_str} | Words: {r['word_count']} | Citations: {r['citation_count']}")
        if not r["error"]:
            preview = r["text"][:200].replace("\n", " ")
            print(f"       Preview: {preview}…")

    return {
        "query": query,
        "context": context,
        "context_spec": case["context_spec"],
        "results": {r["model"]: r for r in model_results},
    }


# ── Markdown report ───────────────────────────────────────────────────────────

def generate_markdown_report(all_results: list, models: list[str]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    model_labels = " · ".join(f"`{m}`" for m in models)
    lines: list[str] = []

    lines.append(f"# Model Benchmark: {model_labels}")
    lines.append(f"_Generated: {now} | Ollama: {OLLAMA_BASE_URL}_\n")

    n = len(all_results)

    # ── Summary table ──────────────────────────────────────────────────────────
    lines.append("## Summary\n")

    header_parts = ["# ", "Query "]
    for m in models:
        header_parts.append(f"{m} time ")
    for m in models:
        header_parts.append(f"{m} words ")
    for m in models:
        header_parts.append(f"{m} cites ")
    lines.append("| " + " | ".join(header_parts) + " |")
    lines.append("|---|---|" + "---|" * (len(models) * 3))

    totals: dict[str, dict] = {
        m: {"time": 0.0, "words": 0, "cites": 0} for m in models
    }

    for i, r in enumerate(all_results, 1):
        q_short = r["query"][:55] + ("…" if len(r["query"]) > 55 else "")
        row_parts = [str(i), q_short]
        for m in models:
            res = r["results"].get(m, {})
            row_parts.append(f"{res.get('elapsed', 0):.1f}s" if not res.get("error") else "ERROR")
        for m in models:
            res = r["results"].get(m, {})
            row_parts.append(str(res.get("word_count", 0)))
        for m in models:
            res = r["results"].get(m, {})
            row_parts.append(str(res.get("citation_count", 0)))
        lines.append("| " + " | ".join(row_parts) + " |")

        for m in models:
            res = r["results"].get(m, {})
            if not res.get("error"):
                totals[m]["time"]  += res.get("elapsed", 0)
                totals[m]["words"] += res.get("word_count", 0)
                totals[m]["cites"] += res.get("citation_count", 0)

    avg_parts = ["", "**AVERAGE**"]
    for m in models:
        avg_parts.append(f"**{totals[m]['time']/n:.1f}s**")
    for m in models:
        avg_parts.append(f"**{totals[m]['words']//n}**")
    for m in models:
        avg_parts.append(f"**{totals[m]['cites']/n:.1f}**")
    lines.append("| " + " | ".join(avg_parts) + " |")
    lines.append("")

    # Speed winner callout
    avg_times = {m: totals[m]["time"] / n for m in models}
    fastest = min(avg_times, key=avg_times.get)
    slowest_time = max(avg_times.values())
    if slowest_time > 0 and avg_times[fastest] > 0 and slowest_time != avg_times[fastest]:
        speedup = slowest_time / avg_times[fastest]
        lines.append(f"> **Speed winner:** `{fastest}` was **{speedup:.1f}×** faster than the slowest model overall.\n")

    # ── Per-query details ──────────────────────────────────────────────────────
    lines.append("---\n")
    lines.append("## Detailed Responses\n")

    for i, r in enumerate(all_results, 1):
        lines.append(f"### Query {i}\n")
        lines.append(f"> {r['query']}\n")

        lines.append("<details><summary>📄 Context sent to models</summary>\n")
        lines.append("```")
        ctx_preview = r["context"][:2000] + ("…" if len(r["context"]) > 2000 else "")
        lines.append(ctx_preview)
        lines.append("```")
        lines.append("</details>\n")

        for m in models:
            res = r["results"].get(m, {})
            lines.append(f"#### `{m}`")
            ttft_str = f" | TTFT: {res['ttft']:.1f}s" if res.get("ttft") else ""
            lines.append(
                f"_⏱ {res.get('elapsed', 0):.1f}s{ttft_str} | "
                f"📝 {res.get('word_count', 0)} words | "
                f"🔖 {res.get('citation_count', 0)} citations_\n"
            )
            if res.get("error"):
                lines.append(f"**ERROR:** {res['error']}\n")
            else:
                lines.append(res.get("text", ""))
                thinking = res.get("thinking", "")
                if thinking:
                    lines.append(
                        f"\n<details><summary>💭 Thinking ({len(thinking)} chars)</summary>\n\n"
                        f"{thinking[:600]}…\n</details>"
                    )
            lines.append("")

        lines.append("---\n")

    return "\n".join(lines)


# ── Persistence helpers ──────────────────────────────────────────────────────

def json_path_for(md_path: Path) -> Path:
    """Return the sidecar JSON path for a given markdown output path."""
    return md_path.with_suffix(".json")


def save_json(all_results: list, models: list[str], json_path: Path) -> None:
    payload = {"models": models, "results": all_results}
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_json(json_path: Path) -> tuple[list[str], list[dict]]:
    """Load saved benchmark data; returns (models, all_results)."""
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    return payload["models"], payload["results"]


# ── Print summary ─────────────────────────────────────────────────────────────

def print_summary(all_results: list, models: list[str]) -> None:
    n = len(all_results)
    print(f"\n{'Model':<22} {'Avg Time':>10} {'Avg Words':>12} {'Avg Cites':>12}")
    print(f"{'-' * 58}")
    avg_times: dict[str, float] = {}
    for m in models:
        rows = [r["results"][m] for r in all_results if m in r["results"]]
        if not rows:
            continue
        avg_t = sum(r["elapsed"]        for r in rows) / n
        avg_w = sum(r["word_count"]     for r in rows) / n
        avg_c = sum(r["citation_count"] for r in rows) / n
        avg_times[m] = avg_t
        print(f"{m:<22} {avg_t:>9.1f}s {avg_w:>12.0f} {avg_c:>12.1f}")
    if len(avg_times) > 1:
        fastest = min(avg_times, key=avg_times.get)
        slowest_time = max(avg_times.values())
        if slowest_time != avg_times[fastest]:
            speedup = slowest_time / avg_times[fastest]
            print(f"\n  ⚡ {fastest} was {speedup:.1f}× faster than the slowest model")
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark N Ollama models for LHA Memoirs RAG")
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
        metavar="MODEL",
        help=f"Models to benchmark (default: {' '.join(DEFAULT_MODELS)})",
    )
    parser.add_argument(
        "--add-model",
        metavar="MODEL",
        help="Add a single model to an existing benchmark (loads saved JSON, runs only this model, updates report)",
    )
    parser.add_argument("--queries", nargs="+", metavar="QUERY", help="Custom queries (overrides built-in test set)")
    parser.add_argument(
        "--context-range",
        nargs=2,
        type=float,
        metavar=("START_SEC", "END_SEC"),
        default=(37, 1500),
        help="Transcript time range used for custom --queries (default: 37 1500)",
    )
    parser.add_argument("--output", default="benchmark_results.md", help="Output markdown file (default: benchmark_results.md)")
    args = parser.parse_args()

    output_path = Path(__file__).parent / args.output
    data_path   = json_path_for(output_path)

    # ── ADD-MODEL mode ────────────────────────────────────────────────────────
    if args.add_model:
        new_model = args.add_model
        if not data_path.exists():
            print(f"ERROR: No saved results found at {data_path}")
            print("Run a full benchmark first before using --add-model.")
            return

        models, all_results = load_json(data_path)

        if new_model in models:
            print(f"Model '{new_model}' is already in the benchmark. Nothing to do.")
            return

        print(f"\nLHA Memoirs — Adding model: {new_model}")
        print(f"  Existing models : {', '.join(models)}")
        print(f"  Queries         : {len(all_results)}")
        print(f"  Ollama          : {OLLAMA_BASE_URL}")

        # Check availability
        async with httpx.AsyncClient(timeout=5.0) as probe:
            try:
                resp = await probe.get(f"{OLLAMA_BASE_URL}/api/tags")
                available_names = {m["name"] for m in resp.json().get("models", [])}
            except Exception:
                available_names = set()
        found = new_model in available_names or any(n.startswith(new_model.split(":")[0]) for n in available_names)
        print(f"  {new_model}: {'✓ available' if found else '⚠ not found in Ollama tag list'}\n")

        # Run new model against every saved query using the stored context
        async with httpx.AsyncClient() as client:
            for i, r in enumerate(all_results, 1):
                query   = r["query"]
                context = r["context"]
                user_message = build_user_message(query, context)
                print(f"  [{i}/{len(all_results)}] {query[:60]}…")
                result = await query_model(client, new_model, SYSTEM_PROMPT, user_message)
                status   = "✗ ERROR" if result["error"] else "✓"
                ttft_str = f" | TTFT: {result['ttft']:.1f}s" if result["ttft"] is not None else ""
                print(f"    [{status}] {result['elapsed']:.1f}s{ttft_str} | Words: {result['word_count']} | Citations: {result['citation_count']}")
                r["results"][new_model] = result

        models.append(new_model)
        save_json(all_results, models, data_path)
        report = generate_markdown_report(all_results, models)
        output_path.write_text(report, encoding="utf-8")

        print(f"\n{'=' * 70}")
        print(f"Done!  Report → {output_path}")
        print_summary(all_results, models)
        return

    # ── FULL BENCHMARK mode ───────────────────────────────────────────────────
    models: list[str] = args.models

    if args.queries:
        start_sec, end_sec = args.context_range
        test_cases = [
            {"query": q, "context_spec": [("memoirs/Norm_red", start_sec, end_sec)]}
            for q in args.queries
        ]
    else:
        test_cases = DEFAULT_TEST_CASES

    print(f"\nLHA Memoirs — Model Benchmark")
    print(f"  Models   : {', '.join(models)}")
    print(f"  Queries  : {len(test_cases)}")
    print(f"  Ollama   : {OLLAMA_BASE_URL}")
    print(f"  Temp     : {TEMPERATURE}")

    # Availability check
    print("\nChecking model availability…")
    async with httpx.AsyncClient(timeout=5.0) as probe:
        try:
            resp = await probe.get(f"{OLLAMA_BASE_URL}/api/tags")
            available_names = {m["name"] for m in resp.json().get("models", [])}
        except Exception:
            available_names = set()

    for model in models:
        found = model in available_names or any(n.startswith(model.split(":")[0]) for n in available_names)
        print(f"  {model}: {'✓ available' if found else '⚠ not found in Ollama tag list'}")

    # Run benchmark
    all_results: list[dict] = []
    async with httpx.AsyncClient() as client:
        for i, case in enumerate(test_cases, 1):
            result = await run_test_case(client, case, models, i, len(test_cases))
            all_results.append(result)

    # Save JSON data + markdown report
    save_json(all_results, models, data_path)
    report = generate_markdown_report(all_results, models)
    output_path.write_text(report, encoding="utf-8")

    print(f"\n{'=' * 70}")
    print(f"Benchmark complete!  Report → {output_path}")
    print_summary(all_results, models)


if __name__ == "__main__":
    asyncio.run(main())
