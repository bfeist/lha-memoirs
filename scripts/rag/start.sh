#!/bin/bash
# Start the LHA Memoirs RAG server on port 9292

echo "Starting LHA Memoirs RAG Server..."

# Trap SIGINT (Ctrl+C) to ensure clean shutdown
trap 'echo "Shutting down..."; kill $PID 2>/dev/null; exit 0' INT

# Start server without reload to avoid Windows multiprocessing issues
uv run uvicorn rag_server:app --port 9292 --host 0.0.0.0 --use-colors &
PID=$!

# Wait for the background process
wait $PID
