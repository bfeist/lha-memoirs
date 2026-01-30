#!/bin/bash
# Helper script to restart the RAG server

echo "Stopping RAG server..."
pkill -f "uvicorn rag_server_simple:app" || echo "No server running"

sleep 2

echo "Starting RAG server..."
cd /f/_repos/lha-memoirs/scripts/rag
./start.sh
