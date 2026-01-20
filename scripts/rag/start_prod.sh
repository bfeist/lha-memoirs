#!/bin/bash
# Start the LHA Memoirs RAG server on port 9292 (production mode - no reload)

echo "Starting LHA Memoirs RAG Server (production mode)..."
uv run uvicorn rag_server_simple:app --port 9292 --host 0.0.0.0
