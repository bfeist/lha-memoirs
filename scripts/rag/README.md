# LHA Memoirs RAG Backend

A local Retrieval Augmented Generation (RAG) backend for chatting with family audio transcripts using Ollama + ChromaDB.

## Requirements

- **NVIDIA RTX 4090** (or compatible GPU with 24GB VRAM)
- **Ollama** installed and running locally
- **Python 3.11+**
- **uv** (Python package manager) - install with `pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Quick Start

### 1. Install Ollama Models

```bash
# Pull the required models
ollama pull gemma3:12b
ollama pull nomic-embed-text
```

### 2. Set Up Python Environment

```bash
cd scripts/rag

# Sync dependencies with uv (creates .venv automatically)
uv sync
```

### 3. Start the RAG Server

```bash
uv run uvicorn rag_server_simple:app --port 8000 --reload
```

The API will be available at `http://localhost:8000`

### 4. Ingest Transcripts

Ingest all transcripts into the vector database:

```bash
curl -X POST http://localhost:8000/ingest-all
```

Or ingest a single recording:

```bash
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"recording_path": "memoirs/Norm_red"}'
```

### 5. Chat with the Transcripts

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "When was Lindy born?"}'
```

## API Endpoints

| Endpoint       | Method | Description                   |
| -------------- | ------ | ----------------------------- |
| `/`            | GET    | Health check                  |
| `/chat`        | POST   | Non-streaming chat endpoint   |
| `/chat/stream` | POST   | Streaming chat endpoint (SSE) |

## Configuration

Environment variables:

| Variable             | Default                  | Description           |
| -------------------- | ------------------------ | --------------------- |
| `OLLAMA_BASE_URL`    | `http://localhost:11434` | Ollama API URL        |
| `EMBED_MODEL`        | `nomic-embed-text`       | Embedding model name  |
| `CHAT_MODEL`         | `gemma3:12b`             | Chat model name       |
| `CHROMA_PERSIST_DIR` | `./chroma_db`            | ChromaDB storage path |

## Retrieval Strategy: Hybrid Search

The system uses **hybrid search** combining two retrieval methods:

### Vector Similarity Search

- Uses `nomic-embed-text` embeddings for semantic understanding
- Finds contextually similar content

### BM25 Keyword Search

- Uses exact keyword matching for named entities and specific terms
- Ensures queries like "V8 Ford" and "Model T" find the correct stories

### Score Combination

- BM25-only results: weighted at 1.2x (keyword matches are prioritized)
- Results found by BOTH methods: get 1.5x boost (confidence signal)
- Top 20 results retrieved from hybrid search, top 10 sent to LLM to avoid context bloat

## Time-Aware Chunking

The ingestion process creates meaningful chunks:

1. Transcript segments are grouped until total duration >= 120 seconds
2. 60-second overlap between chunks preserves continuity
3. Each chunk includes metadata: `recording_id`, `timestamp`, `start_seconds`
4. Timestamps enable frontend to jump to specific playback points

## Frontend Integration

The React frontend connects to this backend. Set the `VITE_RAG_API_URL` environment variable if not running on localhost:8000.

```bash
# .env.local
VITE_RAG_API_URL=http://localhost:8000
```

## Cloudflare Tunnel (Production)

To expose the local API to the web:

```bash
cloudflared tunnel --url http://localhost:8000
```

Then update the frontend to use the generated Cloudflare URL.
