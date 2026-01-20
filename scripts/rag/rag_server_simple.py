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
import logging
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_chroma import Chroma
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi
import httpx

# Setup logging with consistent timestamped format for all libraries
LOG_FORMAT = "%(asctime)s %(levelname)s: %(name)s: %(message)s"
DATE_FMT = "%Y-%m-%d %H:%M:%S"

# Try to enable color support on Windows if colorama is available
try:
    import colorama
    colorama.init()
    _COLORAMA_AVAILABLE = True
except Exception:
    _COLORAMA_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=DATE_FMT)

# Color map for level names (ANSI)
RESET = "\x1b[0m"
LEVEL_COLORS = {
    "DEBUG": "\x1b[36m",     # cyan
    "INFO": "\x1b[32m",      # green
    "WARNING": "\x1b[33m",   # yellow
    "ERROR": "\x1b[31m",     # red
    "CRITICAL": "\x1b[41m\x1b[1m",  # red background + bold
}

class ColorFormatter(logging.Formatter):
    """Logging formatter that colors the levelname portion of the message."""
    def format(self, record: logging.LogRecord) -> str:
        original_level = record.levelname
        color = LEVEL_COLORS.get(original_level, "")
        if color:
            try:
                record.levelname = f"{color}{original_level}{RESET}"
                return super().format(record)
            finally:
                record.levelname = original_level
        return super().format(record)

# Apply the color formatter to existing root handlers
root_logger = logging.getLogger()
color_formatter = ColorFormatter(LOG_FORMAT, DATE_FMT)
for handler in list(root_logger.handlers):
    handler.setFormatter(color_formatter)

# Propagate the root logger handlers to common third-party loggers (uvicorn, httpx, asyncio)
# This ensures their messages use the same timestamped format and coloring as our module logs.
for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "httpx", "asyncio"):
    lib_logger = logging.getLogger(name)
    # Replace any custom handlers with the root handlers so format is consistent
    lib_logger.handlers = root_logger.handlers
    lib_logger.setLevel(root_logger.level)
    lib_logger.propagate = False

logger = logging.getLogger(__name__)

# Configuration
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-oss:20b")
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_db")
PUBLIC_DIR = Path(__file__).parent.parent.parent / "public" / "recordings"

# Security Configuration
MAX_QUERY_LENGTH = 500
REQUEST_SIZE_LIMIT = 1024 * 10  # 10KB max request body
CORS_ORIGINS = os.getenv("CORS_ORIGINS").split(",")

# Rate limiting (30 req/min prevents DoS)
RATE_LIMIT_QUERIES = "30/minute"
RATE_LIMIT_STREAM = "20/minute"

# Chunking: 3 minutes with 30 second overlap
# With 128K context window, we can use larger chunks for better story context
CHUNK_DURATION_SECONDS = 180
CHUNK_OVERLAP_SECONDS = 30

# Mapping from file system path to logical ID
RECORDING_ID_MAP = {
    "christmas1986": "christmas1986",
    "glynn_interview": "glynn_interview",
    "LHA_Sr.Hilary": "lha_sr_hilary",
    "memoirs/Norm_red": "memoirs_main",
    "memoirs/TDK_D60_edited_through_air": "memoirs_draft_telling",
}


import asyncio

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup: Wiping and re-ingesting transcripts...")
    
    # Always start fresh to avoid stale embeddings
    if os.path.exists(CHROMA_PERSIST_DIR):
        try:
            shutil.rmtree(CHROMA_PERSIST_DIR)
        except OSError:
            logger.warning(f"Warning: Could not delete {CHROMA_PERSIST_DIR}. Continuing...")
    
    await run_ingestion()
    yield


app = FastAPI(
    title="LHA Memoirs RAG API",
    description="Local RAG backend for chatting with family audio transcripts", 
    version="2.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS: Primary security for frontend-facing APIs
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    max_age=3600,
)

# Security middleware to add headers 
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    
    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"
    
    # Prevent MIME sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # Enable XSS protection
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    # Content Security Policy
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'"
    
    # Referrer Policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    return response


# Middleware to check request body size
@app.middleware("http")
async def enforce_request_size(request: Request, call_next):
    """Prevent oversized request bodies that could cause DoS."""
    # Skip size check for CORS preflight and other safe methods
    if request.method in ["POST", "PUT"]:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > REQUEST_SIZE_LIMIT:
            raise HTTPException(
                status_code=413,
                detail=f"Request body too large. Max {REQUEST_SIZE_LIMIT} bytes"
            )
    
    return await call_next(request)


class ChatRequest(BaseModel):
    query: str
    
    @field_validator("query")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate and sanitize query input."""
        # Remove leading/trailing whitespace
        v = v.strip()
        
        # Check length
        if not v:
            raise ValueError("Query cannot be empty")
        if len(v) > MAX_QUERY_LENGTH:
            raise ValueError(f"Query too long. Maximum {MAX_QUERY_LENGTH} characters")
        
        # Prevent common injection patterns
        # (While queries are low-risk in RAG context, defense in depth is good)
        dangerous_patterns = [
            r"<script",
            r"javascript:",
            r"on\w+\s*=",
            r"__import__",
            r"eval\(",
            r"exec\(",
        ]
        
        query_lower = v.lower()
        for pattern in dangerous_patterns:
            if re.search(pattern, query_lower):
                raise ValueError("Query contains suspicious content")
        
        return v


class Citation(BaseModel):
    recording_id: str
    timestamp: float
    quote_snippet: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]


# Initialize embeddings - NO custom prefixes, just use the model directly
embeddings: OllamaEmbeddings | None = None

def get_embeddings() -> OllamaEmbeddings:
    global embeddings
    if embeddings is None:
        embeddings = OllamaEmbeddings(
            model=EMBED_MODEL,
            base_url=OLLAMA_BASE_URL,
        )
    return embeddings

vectorstore: Chroma | None = None
bm25_index: BM25Okapi | None = None
all_documents: list[Document] = []


def get_vectorstore() -> Chroma:
    global vectorstore
    if vectorstore is None:
        vectorstore = Chroma(
            collection_name="lha_memoirs_v2",
            embedding_function=get_embeddings(),
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
            logger.info(f"Skipping {rec_id}: no transcript")
            continue
        
        with open(transcript_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        segments = data.get("segments", [])
        if not segments:
            continue
        
        docs = chunk_transcript(segments, rec_id)
        if docs:
            all_docs.extend(docs)
            logger.info(f"Ingested {rec_id}: {len(docs)} chunks")
    
    # Add to vector store
    if all_docs:
        vs.add_documents(all_docs)
    
    # Build BM25 index for hybrid search
    build_bm25_index(all_docs)
    
    logger.info(f"Total: {len(all_docs)} chunks ingested")


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


def hybrid_search(query: str, k: int = 60) -> list[Document]:
    """
    Hybrid search combining vector similarity and BM25 keyword matching.
    This ensures we find both semantically similar content AND exact keyword matches.
    Increased k to 60 to take advantage of gpt-oss:20b's 128K context window.
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


SYSTEM_PROMPT = """You are a family historian assistant with access to audio transcripts from Linden Hilary Achen (1902-1994). These are voice memoirs recorded by Linden "Lindy" Achen in the 1980s. Lindy is a male.

USE LOW REASONING EFFORT - answer quickly and directly.

CRITICAL CITATION RULES:
1. ALWAYS cite your sources using this EXACT format: [Source: recording_id, Time: MM:SS]
2. Include citations at the END of each fact or sentence that comes from the context.
3. Use the EXACT recording_id and timestamp from the context headers.

Example: "Lindy bought his Model T Ford for about $350. [Source: memoirs_main, Time: 45:23] The car was a coupe and he referred to it as a 'four-grocer'. [Source: memoirs_main, Time: 46:10]"

OTHER RULES:
- Answer ONLY from the provided context. If info isn't there, say so.
- Look through ALL provided context before answering.
- Include specific details like names, places, dates, vehicle models when mentioned.
- Write in natural prose, not lists or tables.
"""


@app.get("/", include_in_schema=False)
async def root():
    """Return generic error to hide server identity."""
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("Bad Request", status_code=400)


@app.get("/health/stream") 
async def health_stream():
    """
    SSE endpoint for persistent health monitoring.
    Sends a heartbeat every 30 seconds.
    """
    import asyncio
    
    async def event_generator():
        try:
            # Send initial connection event
            yield f"data: {json.dumps({'status': 'connected', 'timestamp': asyncio.get_event_loop().time()})}\n\n"
            
            # Send periodic heartbeats every 30 seconds
            while True:
                await asyncio.sleep(30)
                yield f"data: {json.dumps({'status': 'alive', 'timestamp': asyncio.get_event_loop().time()})}\n\n"
        except asyncio.CancelledError:
            # Client disconnected or server shutting down
            pass
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable buffering in nginx
        }
    )


@app.post("/chat", response_model=ChatResponse)
@limiter.limit(RATE_LIMIT_QUERIES)
async def chat(request: Request, chat_request: ChatRequest):
    """Chat endpoint with rate limiting."""
    query = chat_request.query
    logger.info(f"Chat from {request.client.host}: {query[:50]}...")
    
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
        logger.info(f"Chat response generated: {len(answer)} chars")
    except Exception as e:
        logger.error(f"LLM error: {e}")
        raise HTTPException(status_code=500, detail=f"LLM failed: {str(e)[:100]}")
    
    citations = extract_citations(answer, docs)
    return ChatResponse(answer=answer, citations=citations)


@app.post("/chat/stream")
@limiter.limit(RATE_LIMIT_STREAM)
async def chat_stream(request: Request, chat_request: ChatRequest):
    """Streaming chat endpoint with rate limiting."""
    query = chat_request.query
    logger.info(f"Stream from {request.client.host}: {query[:50]}...")
    
    # Use hybrid search (vector + BM25)
    # Reduced context to avoid overwhelming the model with too much to process
    docs = hybrid_search(query, k=25)
    docs_for_llm = docs[:12]
    
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

        accumulated_text = ""
        accumulated_thinking = ""
        
        # Use raw Ollama API for proper thinking stream support
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": CHAT_MODEL, 
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_message},
                        ],
                        "stream": True,
                    },
                ) as response:
                    async for line in response.aiter_lines():
                        if line.strip():
                            try:
                                data = json.loads(line)
                                message = data.get("message", {})
                                
                                # Stream thinking if present
                                thinking_chunk = message.get("thinking", "") 
                                if thinking_chunk:
                                    accumulated_thinking += thinking_chunk
                                    yield f"data: {json.dumps({'type': 'thinking', 'content': thinking_chunk})}\n\n"
                                
                                # Stream content if present
                                content_chunk = message.get("content", "")
                                if content_chunk:
                                    accumulated_text += content_chunk
                                    yield f"data: {json.dumps({'type': 'text', 'content': content_chunk})}\n\n"
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)[:100]})}\n\n"
        
        citations = extract_citations(accumulated_text, docs_for_llm)
        citations_data = [c.model_dump() for c in citations]
        yield f"data: {json.dumps({'type': 'citations', 'citations': citations_data})}\n\n"
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")



