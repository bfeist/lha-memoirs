"""
RAG Server for LHA Memoirs - Simplified Version

Key design decisions:
1. NO embedding prefixes - just raw text
2. Large chunks (2 minutes) to capture full story context
3. High overlap (1 minute) to avoid missing content at boundaries
4. Pass ALL retrieved chunks to LLM - let the AI do the filtering
5. Simple, debuggable pipeline
"""

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_chroma import Chroma
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

# Configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gemma3:12b")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
PUBLIC_DIR = Path(__file__).parent.parent.parent / "public" / "recordings"

# Chunking: 2 minutes with 1 minute overlap = lots of redundancy but ensures nothing is missed
CHUNK_DURATION_SECONDS = 120
CHUNK_OVERLAP_SECONDS = 60

# Mapping from file system path to logical ID
RECORDING_ID_MAP = {
    "christmas1986": "christmas1986",
    "glynn_interview": "glynn_interview",
    "LHA_Sr.Hilary": "lha_sr_hilary",
    "memoirs/Norm_red": "memoirs_main",
    "memoirs/TDK_D60_edited_through_air": "memoirs_draft_telling",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Startup: Wiping and re-ingesting transcripts...")
    # Always start fresh to avoid stale embeddings
    if os.path.exists(CHROMA_PERSIST_DIR):
        shutil.rmtree(CHROMA_PERSIST_DIR)
    await run_ingestion()
    yield


app = FastAPI(
    title="LHA Memoirs RAG API",
    description="Local RAG backend for chatting with family audio transcripts",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    query: str


class Citation(BaseModel):
    recording_id: str
    timestamp: float
    quote_snippet: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]


# Initialize embeddings - NO custom prefixes, just use the model directly
embeddings = OllamaEmbeddings(
    model=EMBED_MODEL,
    base_url=OLLAMA_BASE_URL,
)

vectorstore: Chroma | None = None
bm25_index: BM25Okapi | None = None
all_documents: list[Document] = []


def get_vectorstore() -> Chroma:
    global vectorstore
    if vectorstore is None:
        vectorstore = Chroma(
            collection_name="lha_memoirs_v2",
            embedding_function=embeddings,
            persist_directory=CHROMA_PERSIST_DIR,
        )
    return vectorstore


def build_bm25_index(docs: list[Document]):
    """Build BM25 index for keyword search."""
    global bm25_index, all_documents
    all_documents = docs
    # Tokenize documents for BM25
    tokenized = [doc.page_content.lower().split() for doc in docs]
    bm25_index = BM25Okapi(tokenized)


def format_timestamp(seconds: float) -> str:
    mins = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{mins}:{secs:02d}"


def chunk_transcript(segments: list[dict[str, Any]], recording_id: str) -> list[Document]:
    """
    Create overlapping chunks from transcript segments.
    Each chunk is pure text - metadata stored separately.
    """
    if not segments:
        return []
    
    documents: list[Document] = []
    start_idx = 0
    
    while start_idx < len(segments):
        texts = []
        chunk_start = segments[start_idx].get("start", 0.0)
        end_idx = start_idx
        
        # Collect segments until we hit the duration limit
        while end_idx < len(segments):
            seg = segments[end_idx]
            seg_end = seg.get("end", seg.get("start", 0.0))
            text = seg.get("text", "").strip()
            
            if text:
                texts.append(text)
            
            if seg_end - chunk_start >= CHUNK_DURATION_SECONDS:
                break
            end_idx += 1
        
        if texts:
            # CRITICAL: Store ONLY the raw transcript text for embedding
            # No prefixes, no metadata in the text - just pure content
            raw_text = " ".join(texts)
            
            documents.append(Document(
                page_content=raw_text,
                metadata={
                    "recording_id": recording_id,
                    "start_seconds": chunk_start,
                    "timestamp": format_timestamp(chunk_start),
                }
            ))
        
        # Advance by overlap amount
        target_time = chunk_start + (CHUNK_DURATION_SECONDS - CHUNK_OVERLAP_SECONDS)
        next_idx = start_idx + 1
        for i in range(start_idx + 1, len(segments)):
            if segments[i].get("start", 0.0) >= target_time:
                next_idx = i
                break
        
        if next_idx == start_idx:
            next_idx = start_idx + 1
        
        if end_idx >= len(segments) - 1:
            break
        start_idx = next_idx
    
    return documents


async def run_ingestion():
    """Ingest all transcripts."""
    vs = get_vectorstore()
    all_docs = []
    
    for path, rec_id in RECORDING_ID_MAP.items():
        transcript_file = PUBLIC_DIR / path / "transcript.json"
        if not transcript_file.exists():
            print(f"  Skipping {rec_id}: no transcript")
            continue
        
        with open(transcript_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        segments = data.get("segments", [])
        if not segments:
            continue
        
        docs = chunk_transcript(segments, rec_id)
        if docs:
            all_docs.extend(docs)
            print(f"  Ingested {rec_id}: {len(docs)} chunks")
    
    # Add to vector store
    if all_docs:
        vs.add_documents(all_docs)
    
    # Build BM25 index for hybrid search
    build_bm25_index(all_docs)
    
    print(f"Total: {len(all_docs)} chunks ingested")


def extract_citations(answer: str, docs: list[Document]) -> list[Citation]:
    """Extract citations for sources that were actually referenced in the answer."""
    # Find all [Source: X, Time: Y] patterns in the answer
    pattern = r"\[Source:\s*([^,\]]+),\s*Time:\s*([^\]]+)\]"
    refs = set(re.findall(pattern, answer))
    
    citations = []
    seen = set()
    
    for doc in docs:
        rec_id = doc.metadata.get("recording_id", "")
        timestamp = doc.metadata.get("timestamp", "")
        
        if (rec_id, timestamp) in refs and (rec_id, timestamp) not in seen:
            seen.add((rec_id, timestamp))
            snippet = doc.page_content[:100] + "..." if len(doc.page_content) > 100 else doc.page_content
            citations.append(Citation(
                recording_id=rec_id,
                timestamp=doc.metadata.get("start_seconds", 0.0),
                quote_snippet=snippet,
            ))
    
    return citations


def hybrid_search(query: str, k: int = 40) -> list[Document]:
    """
    Hybrid search combining vector similarity and BM25 keyword matching.
    This ensures we find both semantically similar content AND exact keyword matches.
    """
    global bm25_index, all_documents
    
    results_map: dict[str, tuple[Document, float]] = {}
    
    # 1. Vector search (semantic)
    vs = get_vectorstore()
    try:
        vector_results = vs.similarity_search_with_score(query, k=k)
        for doc, score in vector_results:
            # Lower score is better in Chroma (distance)
            # Normalize to 0-1 where 1 is best
            norm_score = max(0, 1 - score / 2)
            key = f"{doc.metadata.get('recording_id')}_{doc.metadata.get('timestamp')}"
            results_map[key] = (doc, norm_score)
    except Exception:
        pass
    
    # 2. BM25 keyword search
    if bm25_index and all_documents:
        query_tokens = query.lower().split()
        bm25_scores = bm25_index.get_scores(query_tokens)
        
        # Get top k by BM25 score
        top_indices = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)[:k]
        
        max_bm25 = max(bm25_scores) if max(bm25_scores) > 0 else 1
        
        for idx in top_indices:
            if bm25_scores[idx] > 0:
                doc = all_documents[idx]
                # Normalize BM25 to 0-1, but give it strong weight
                norm_score = bm25_scores[idx] / max_bm25
                key = f"{doc.metadata.get('recording_id')}_{doc.metadata.get('timestamp')}"
                
                if key in results_map:
                    # Found by BOTH methods - big boost
                    existing_score = results_map[key][1]
                    combined = existing_score + norm_score * 1.5
                    results_map[key] = (doc, combined)
                else:
                    # BM25-only: Give it a strong score - keyword matches matter!
                    # If BM25 found it with high confidence, it should rank above
                    # mediocre vector matches (which often score 0.3-0.6)
                    results_map[key] = (doc, norm_score * 1.2)
    
    # Sort by combined score and return top k
    sorted_results = sorted(results_map.values(), key=lambda x: x[1], reverse=True)
    return [doc for doc, score in sorted_results[:k]]


SYSTEM_PROMPT = """You are a family historian assistant with access to audio transcripts from Linden Hilary Achen (1902-1994). These are voice memoirs recorded in the 1980s.

RULES:
1. Answer ONLY from the provided context. If info isn't there, say so.
2. When citing, use format: [Source: recording_id, Time: MM:SS]
3. Be thorough - look through ALL provided context before answering.
4. Include specific details like names, places, dates, vehicle models when mentioned."""


@app.get("/")
async def root():
    return {"status": "ok", "version": "2.0.0"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    # Use hybrid search (vector + BM25) - get more, then use top ones
    docs = hybrid_search(query, k=20)
    
    # Only send top 10 most relevant to the LLM to avoid confusion
    docs_for_llm = docs[:10]
    
    if not docs_for_llm:
        return ChatResponse(answer="No relevant transcripts found.", citations=[])
    
    # Build context with clear source attribution
    context_parts = []
    for doc in docs_for_llm:
        rec_id = doc.metadata.get("recording_id", "unknown")
        ts = doc.metadata.get("timestamp", "0:00")
        context_parts.append(f"[Source: {rec_id}, Time: {ts}]\n{doc.page_content}")
    
    context = "\n\n---\n\n".join(context_parts)
    
    user_message = f"""Context from transcripts:

{context}

---

Question: {query}

Look through ALL the context above and provide a complete answer."""

    llm = ChatOllama(model=CHAT_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.3)
    
    try:
        response = llm.invoke([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ])
        answer = response.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM failed: {e}")
    
    citations = extract_citations(answer, docs)
    return ChatResponse(answer=answer, citations=citations)


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    # Use hybrid search (vector + BM25) - get more, use top ones
    docs = hybrid_search(query, k=20)
    docs_for_llm = docs[:10]
    
    async def generate():
        if not docs_for_llm:
            yield f"data: {json.dumps({'type': 'text', 'content': 'No relevant transcripts found.'})}\n\n"
            yield f"data: {json.dumps({'type': 'citations', 'citations': []})}\n\n"
            yield "data: [DONE]\n\n"
            return
        
        context_parts = []
        for doc in docs_for_llm:
            rec_id = doc.metadata.get("recording_id", "unknown")
            ts = doc.metadata.get("timestamp", "0:00")
            context_parts.append(f"[Source: {rec_id}, Time: {ts}]\n{doc.page_content}")
        
        context = "\n\n---\n\n".join(context_parts)
        
        user_message = f"""Context from transcripts:

{context}

---

Question: {query}

Look through ALL the context above and provide a complete answer."""

        llm = ChatOllama(model=CHAT_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.3)
        
        accumulated = ""
        try:
            async for chunk in llm.astream([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ]):
                if chunk.content:
                    accumulated += chunk.content
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk.content})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        
        citations = extract_citations(accumulated, docs_for_llm)
        citations_data = [c.model_dump() for c in citations]
        yield f"data: {json.dumps({'type': 'citations', 'citations': citations_data})}\n\n"
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")



