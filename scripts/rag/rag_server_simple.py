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
import csv
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

# Chunking: 90 seconds with 15 second overlap
# Smaller chunks provide more precise citation timestamps
# With 128K context window, we can still send plenty of context
CHUNK_DURATION_SECONDS = 90
CHUNK_OVERLAP_SECONDS = 15

# Mapping from file system path to logical ID
RECORDING_ID_MAP = {
    "christmas1986": "christmas1986",
    "glynn_interview": "glynn_interview",
    "LHA_Sr.Hilary": "lha_sr_hilary",
    "memoirs/Norm_red": "memoirs_main",
    "memoirs/TDK_D60_edited_through_air": "memoirs_earlier_telling",
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
    start_seconds: float  # Start time in seconds - unique key to look up transcript segment
    segment_count: int = 3  # Number of transcript segments to play (defaults to 3)


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
        transcript_file = PUBLIC_DIR / path / "transcript.csv"
        if not transcript_file.exists():
            logger.info(f"Skipping {rec_id}: no transcript")
            continue
        
        # Read CSV file with pipe delimiter
        segments = []
        with open(transcript_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="|")
            for row in reader:
                try:
                    segments.append({
                        "start": float(row["start"]),
                        "end": float(row["end"]),
                        "text": row["text"]
                    })
                except (ValueError, KeyError) as e:
                    logger.warning(f"Skipping invalid row in {rec_id}: {e}")
                    continue
        
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


def extract_citations(answer: str, docs: list[Document]) -> tuple[str, list[Citation]]:
    """
    Extract citations from the LLM's answer.
    
    SIMPLE APPROACH: The LLM was given context with specific timestamps like 
    [Source: memoirs_main, Time: 28:22]. We extract these citations and look up
    the corresponding chunk's start_seconds from the provided docs.
    
    We do NOT try to "refine" or "validate" - if the LLM cited incorrectly,
    that's a prompt/context issue, not something we can fix post-hoc.
    """
    # Find all [Source: X, Time: Y] or [Source: X, Time: Y, Segments: N] patterns
    # Support both standard brackets [] and Japanese brackets 【】
    pattern = r"[\[【]Source:\s*([^,\]】]+),\s*Time:\s*([^,\]】]+)(?:,\s*Segments:\s*(\d+))?[\]】]"
    matches = re.findall(pattern, answer)
    
    logger.info(f"Found {len(matches)} citation patterns in answer")
    
    citations = []
    seen = set()
    
    # Build lookup of docs by (recording_id, timestamp) for exact matching
    doc_lookup: dict[tuple[str, str], Document] = {}
    for doc in docs:
        rec_id = doc.metadata.get("recording_id", "")
        ts = doc.metadata.get("timestamp", "")
        doc_lookup[(rec_id, ts)] = doc
    
    for match in matches:
        rec_id = match[0].strip()
        timestamp = match[1].strip()
        segments_str = match[2].strip() if match[2] else "3"
        
        try:
            segment_count = int(segments_str)
            segment_count = max(1, min(15, segment_count))
        except ValueError:
            segment_count = 3
        
        # Look up the exact document that matches this citation
        doc = doc_lookup.get((rec_id, timestamp))
        
        if doc:
            # Use the chunk's actual start_seconds
            start_seconds = doc.metadata.get("start_seconds", 0.0)
        else:
            # Document not found - LLM cited a timestamp that wasn't in the context
            # Parse the timestamp and use it directly
            try:
                parts = timestamp.split(":")
                if len(parts) == 2:
                    start_seconds = int(parts[0]) * 60 + int(parts[1])
                else:
                    start_seconds = float(parts[0])
            except (ValueError, IndexError):
                logger.warning(f"Could not parse timestamp: {timestamp}")
                continue
            logger.warning(f"Citation {rec_id} @ {timestamp} not found in provided context")
        
        key = (rec_id, start_seconds, segment_count)
        if key in seen:
            continue
        seen.add(key)
        
        citations.append(Citation(
            recording_id=rec_id,
            start_seconds=start_seconds,
            segment_count=segment_count,
        ))
    
    logger.info(f"Extracted {len(citations)} citations")
    return answer, citations  # Return original answer unchanged


def expand_query_with_year_abbreviations(query: str) -> str:
    """
    Expand queries containing 4-digit years (1900-1999) to include abbreviated forms.
    Example: "1917" -> "1917 '17"
    This helps match Lindy's year abbreviations like '38 for 1938.
    """
    # Find all 4-digit years in the 1900s (the relevant century for these memoirs)
    year_pattern = r'\b(19\d{2})\b'
    matches = re.findall(year_pattern, query)
    
    expanded_query = query
    for year in matches:
        # Extract last 2 digits and add abbreviated form
        abbrev = "'" + year[-2:]
        # Add the abbreviation to the query if not already present
        if abbrev not in expanded_query:
            expanded_query += f" {abbrev}"
    
    return expanded_query


def calculate_bm25_relevance(text: str, query_tokens: list[str]) -> float:
    """
    Calculate BM25-style relevance score between document text and query tokens.
    Returns normalized score 0-1.
    """
    text_tokens = text.lower().split()
    if not text_tokens:
        return 0.0
    
    # Count matching tokens (simple TF approach)
    matches = sum(1 for token in query_tokens if token in text_tokens)
    return matches / len(query_tokens) if query_tokens else 0.0


def filter_documents_by_relevance(docs: list[Document], query: str, min_score: float = 0.15) -> list[Document]:
    """
    Filter documents to only include those with minimum keyword relevance to query.
    This prevents completely irrelevant chunks from being passed to the LLM.
    """
    query_tokens = set(query.lower().split())
    # Remove stop words
    stop_words = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
                  "of", "with", "by", "from", "as", "is", "was", "are", "were", "be",
                  "been", "have", "has", "had", "do", "does", "did", "will", "would",
                  "could", "should", "may", "might", "can", "about", "what", "when",
                  "where", "who", "how", "tell", "me", "his", "her", "their"}
    query_tokens = query_tokens - stop_words
    
    if not query_tokens:
        return docs  # Can't filter without meaningful query words
    
    filtered = []
    for doc in docs:
        score = calculate_bm25_relevance(doc.page_content, list(query_tokens))
        if score >= min_score:
            filtered.append(doc)
            logger.debug(f"Doc relevance {score:.2f}: {doc.metadata.get('recording_id')} @ {doc.metadata.get('timestamp')}")
        else:
            logger.debug(f"Filtered out (score {score:.2f}): {doc.metadata.get('recording_id')} @ {doc.metadata.get('timestamp')}")
    
    if not filtered:
        # If filter is too aggressive, return top 3 from original set
        logger.warning(f"Relevance filter too aggressive, keeping top 3 docs")
        return docs[:3]
    
    logger.info(f"Filtered from {len(docs)} to {len(filtered)} documents (min_score={min_score})")
    return filtered


def hybrid_search(query: str, k: int = 60) -> list[Document]:
    """
    Hybrid search combining vector similarity and BM25 keyword matching.
    This ensures we find both semantically similar content AND exact keyword matches.
    Increased k to 60 to take advantage of gpt-oss:20b's 128K context window.
    """
    global bm25_index, all_documents
    
    # Expand query to include year abbreviations
    expanded_query = expand_query_with_year_abbreviations(query)
    if expanded_query != query:
        logger.info(f"Query expanded: '{query}' -> '{expanded_query}'")
    
    results_map: dict[str, tuple[Document, float]] = {}
    
    # 1. Vector search (semantic)
    vs = get_vectorstore()
    try:
        vector_results = vs.similarity_search_with_score(expanded_query, k=k)
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
        query_tokens = expanded_query.lower().split()
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


@app.get("/", include_in_schema=False)
async def root():
    """Return generic error to hide server identity."""
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("Bad Request", status_code=400)


@app.get("/debug/search")
async def debug_search(query: str, k: int = 10):
    """Debug endpoint to see what documents are returned for a query."""
    docs = hybrid_search(query, k=k)
    return {
        "query": query,
        "document_count": len(docs),
        "documents": [
            {
                "recording_id": doc.metadata.get("recording_id"),
                "timestamp": doc.metadata.get("timestamp"),
                "start_seconds": doc.metadata.get("start_seconds"),
                "content": doc.page_content[:500]
            }
            for doc in docs
        ]
    }


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
    
    # Use hybrid search (vector + BM25) - get more, then filter
    docs = hybrid_search(query, k=25)
    
    # Filter out documents that don't have meaningful keyword overlap with query
    # This prevents irrelevant chunks from confusing the LLM
    # Increased min_score to 0.25 for stricter filtering
    docs_filtered = filter_documents_by_relevance(docs, query, min_score=0.25)
    
    # Only send top 6 most relevant to the LLM to reduce confusion
    docs_for_llm = docs_filtered[:6]
    
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
    
    # Extract and refine citations, get updated answer text
    updated_answer, citations = extract_citations(answer, docs_for_llm)
    return ChatResponse(answer=updated_answer, citations=citations)


@app.post("/chat/stream")
@limiter.limit(RATE_LIMIT_STREAM)
async def chat_stream(request: Request, chat_request: ChatRequest):
    """Streaming chat endpoint with rate limiting."""
    query = chat_request.query
    logger.info(f"Stream from {request.client.host}: {query[:50]}...")
    
    # Use hybrid search (vector + BM25)
    docs = hybrid_search(query, k=25)
    
    # Filter out documents that don't have meaningful keyword overlap
    # Increased min_score to 0.25 for stricter filtering
    docs_filtered = filter_documents_by_relevance(docs, query, min_score=0.25)
    
    # Send top 6 most relevant to avoid overwhelming the model
    docs_for_llm = docs_filtered[:6]
    
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
        
        # Extract and refine citations, get updated answer text
        updated_answer, citations = extract_citations(accumulated_text, docs_for_llm)
        citations_data = [c.model_dump() for c in citations]
        yield f"data: {json.dumps({'type': 'citations', 'citations': citations_data})}\n\n"
        yield "data: [DONE]\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")



