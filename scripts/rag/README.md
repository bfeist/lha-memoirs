# LHA Memoirs RAG Backend

A local Retrieval Augmented Generation (RAG) backend for chatting with family audio transcripts using Ollama + ChromaDB.

## Quick Start

### 1. Install Prerequisites

- **Ollama** - Download from https://ollama.ai
- **Python 3.11+** with `uv` package manager

### 2. Pull Required Models

```bash
ollama pull nomic-embed-text
ollama pull gpt-oss:20b
```

### 3. Start the Server

```bash
cd scripts/rag
chmod +x start.sh
./start.sh
```

The server will start on `http://localhost:9292` and automatically ingest all transcripts on first run.

## API Usage

### Health Check

```bash
curl http://localhost:9292/
```

### Chat (Streaming)

```bash
curl -X POST http://localhost:9292/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "When was Lindy born?"}'
```

## Configuration

Edit the variables at the top of `rag_server_simple.py`:

| Variable             | Default                  | Purpose                   |
| -------------------- | ------------------------ | ------------------------- |
| `OLLAMA_BASE_URL`    | `http://localhost:11434` | Where Ollama is running   |
| `CHAT_MODEL`         | `gpt-oss:20b`            | Which model to use        |
| `CHROMA_PERSIST_DIR` | `./chroma_db`            | Where to store embeddings |

## How It Works

**Hybrid Search**: Combines semantic vector search with keyword matching to find the most relevant transcript excerpts.

**Time-Aware Citations**: Each answer includes clickable links to the exact moment in the audio where Lindy discusses that topic.
