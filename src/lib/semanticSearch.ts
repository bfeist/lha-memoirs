/**
 * Semantic search engine that runs entirely in the browser.
 *
 * Loads a pre-built search index (segments.json + embeddings.bin) and
 * runs a sentence-transformer model (all-MiniLM-L6-v2) via ONNX /
 * @huggingface/transformers to embed queries and compute cosine similarity.
 *
 * The text index (search-index.json) is loaded in parallel and used as a
 * fallback / complement while the model downloads.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Metadata for the semantic search index. */
export interface IndexMeta {
  version: number;
  model: string;
  embedding_dim: number;
  embedding_dtype: string;
  num_segments: number;
  built_at: string;
  files: {
    segments: string;
    embeddings: string;
  };
}

/** A single segment from the semantic index. */
export interface IndexSegment {
  id: number;
  /** Recording path (e.g. "memoirs/Norm_red") */
  r: string;
  /** Recording title */
  t: string;
  /** Start time in seconds */
  s: number;
  /** End time in seconds */
  e: number;
  /** Original transcript text */
  x: string;
  /** Segment index within the recording */
  i: number;
}

/** A search result returned by the semantic engine. */
export interface SemanticSearchResult {
  segment: IndexSegment;
  score: number;
}

/** Progress event emitted during search-engine initialisation. */
export interface InitProgress {
  stage: "index" | "model" | "text-index";
  message: string;
  done?: boolean;
}

/**
 * Thin callable type for the transformers.js feature-extraction pipeline.
 */
type Extractor = (
  text: string,
  options?: Record<string, unknown>
) => Promise<{ data: ArrayLike<number> }>;

// ---------------------------------------------------------------------------
// Paths (relative to Vite dev-server / build root)
// ---------------------------------------------------------------------------
const INDEX_META_URL = "/semantic-search/index_meta.json";
const SEGMENTS_URL = "/semantic-search/segments.json";
const EMBEDDINGS_URL = "/semantic-search/embeddings.bin";

// ---------------------------------------------------------------------------
// Singleton state
// ---------------------------------------------------------------------------
let _meta: IndexMeta | null = null;
let _segments: IndexSegment[] | null = null;
let _embeddings: Float32Array | null = null;
let _extractor: Extractor | null = null;

let _initPromise: Promise<void> | null = null;
let _modelPromise: Promise<void> | null = null;

// ---------------------------------------------------------------------------
// IEEE 754 float16 -> float32 conversion
// ---------------------------------------------------------------------------
function float16ToFloat32(h: number): number {
  const buf = new ArrayBuffer(4);
  const view = new DataView(buf);

  const sign = Math.floor(h / 32768);
  const exponent = Math.floor(h / 1024) % 32;
  const mantissa = h % 1024;

  let f32Bits: number;

  if (exponent === 0) {
    if (mantissa === 0) {
      f32Bits = sign * 2147483648;
    } else {
      let m = mantissa;
      let e = -14 + 127;
      while (m < 1024) {
        m *= 2;
        e -= 1;
      }
      m -= 1024;
      f32Bits = sign * 2147483648 + e * 8388608 + Math.floor(m * 8192);
    }
  } else if (exponent === 31) {
    f32Bits = sign * 2147483648 + 255 * 8388608 + (mantissa !== 0 ? 1 : 0);
  } else {
    const f32Exp = exponent - 15 + 127;
    f32Bits = sign * 2147483648 + f32Exp * 8388608 + Math.floor(mantissa * 8192);
  }

  view.setUint32(0, f32Bits, false);
  return view.getFloat32(0, false);
}

// ---------------------------------------------------------------------------
// Initialisation
// ---------------------------------------------------------------------------

/**
 * Load the semantic search index (metadata + segments + embeddings).
 * Typically fast — a few MB of JSON + ~5 MB binary.
 */
export async function loadIndex(onProgress?: (p: InitProgress) => void): Promise<void> {
  if (_meta && _segments && _embeddings) return;
  if (_initPromise) return _initPromise;

  _initPromise = (async () => {
    onProgress?.({ stage: "index", message: "Loading semantic search index…" });

    const [metaRes, segmentsRes] = await Promise.all([fetch(INDEX_META_URL), fetch(SEGMENTS_URL)]);

    if (!metaRes.ok || !segmentsRes.ok) {
      throw new Error("Failed to fetch semantic search index files");
    }

    _meta = (await metaRes.json()) as IndexMeta;
    _segments = (await segmentsRes.json()) as IndexSegment[];

    onProgress?.({
      stage: "index",
      message: `Loaded ${_meta.num_segments} segments. Fetching embeddings…`,
    });

    const embRes = await fetch(EMBEDDINGS_URL);
    if (!embRes.ok) throw new Error("Failed to fetch embeddings.bin");

    const embBuf = await embRes.arrayBuffer();
    const dim = _meta.embedding_dim;
    const numSegments = _meta.num_segments;

    if (_meta.embedding_dtype === "float16") {
      const f16 = new Uint16Array(embBuf);
      const f32 = new Float32Array(f16.length);
      for (let i = 0; i < f16.length; i++) {
        f32[i] = float16ToFloat32(f16[i]);
      }
      _embeddings = f32;
    } else {
      _embeddings = new Float32Array(embBuf);
    }

    if (_embeddings.length !== numSegments * dim) {
      throw new Error(
        `Embeddings size mismatch: got ${_embeddings.length}, expected ${numSegments * dim}`
      );
    }

    onProgress?.({
      stage: "index",
      message: `Search index ready (${numSegments} segments, ${dim}d)`,
      done: true,
    });
  })();

  return _initPromise;
}

/**
 * Load the sentence-transformer model for query embedding.
 * This can take 5–15s on first load (model download + ONNX init).
 * Subsequent loads are near-instant (cached by the browser).
 */
export async function loadModel(onProgress?: (p: InitProgress) => void): Promise<void> {
  if (_extractor) return;
  if (_modelPromise) return _modelPromise;

  _modelPromise = (async () => {
    onProgress?.({
      stage: "model",
      message: "Loading semantic search model (all-MiniLM-L6-v2)…",
    });

    const { pipeline } = await import("@huggingface/transformers");
    _extractor = (await pipeline("feature-extraction", "Xenova/all-MiniLM-L6-v2", {
      dtype: "fp32",
    })) as unknown as Extractor;

    onProgress?.({
      stage: "model",
      message: "Model ready",
      done: true,
    });
  })();

  return _modelPromise;
}

/** Load both index and model (in parallel). */
export async function init(onProgress?: (p: InitProgress) => void): Promise<void> {
  await Promise.all([loadIndex(onProgress), loadModel(onProgress)]);
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

/** Embed a query string and return the normalised float32 vector. */
async function embedQuery(query: string): Promise<Float32Array> {
  if (!_extractor) throw new Error("Model not loaded");

  const output = await _extractor(query, {
    pooling: "mean",
    normalize: true,
  });

  return new Float32Array(output.data as Float32Array);
}

/**
 * Search the index with a natural-language query.
 * Returns the top `k` results above `minScore`.
 */
export async function search(
  query: string,
  { k = 25, minScore = 0.15 }: { k?: number; minScore?: number } = {}
): Promise<SemanticSearchResult[]> {
  if (!_embeddings || !_segments || !_meta) {
    throw new Error("Index not loaded");
  }
  if (!_extractor) {
    throw new Error("Model not loaded");
  }

  const queryVec = await embedQuery(query);
  const dim = _meta.embedding_dim;
  const numSeg = _meta.num_segments;

  // Cosine similarity = dot product (both vectors are unit-normalised)
  const scores = new Float32Array(numSeg);
  for (let i = 0; i < numSeg; i++) {
    let dot = 0;
    const offset = i * dim;
    for (let j = 0; j < dim; j++) {
      dot += queryVec[j] * _embeddings[offset + j];
    }
    scores[i] = dot;
  }

  // Top-k
  const indices = Array.from({ length: numSeg }, (_, i) => i);
  indices.sort((a, b) => scores[b] - scores[a]);

  const results: SemanticSearchResult[] = [];
  for (const idx of indices) {
    if (results.length >= k) break;
    if (scores[idx] < minScore) break;

    results.push({
      segment: _segments[idx],
      score: scores[idx],
    });
  }

  return results;
}

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------
export function isIndexLoaded(): boolean {
  return _meta !== null && _segments !== null && _embeddings !== null;
}

export function isModelLoaded(): boolean {
  return _extractor !== null;
}

export function isReady(): boolean {
  return isIndexLoaded() && isModelLoaded();
}

export function getSegmentCount(): number {
  return _meta?.num_segments ?? 0;
}
