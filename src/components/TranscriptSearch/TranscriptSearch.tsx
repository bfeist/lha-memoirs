import { useState, useMemo, useCallback, useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faSearch, faSpinner, faTimes, faBrain, faFont } from "@fortawesome/free-solid-svg-icons";
import { formatTime } from "../../hooks/useRecordingData";
import {
  init as initSemantic,
  search as semanticSearch,
  isIndexLoaded,
  isModelLoaded,
  getSegmentCount,
  type SemanticSearchResult,
  type InitProgress,
} from "../../lib/semanticSearch";
import styles from "./TranscriptSearch.module.css";

// Type for a search index entry
interface SearchIndexEntry {
  r: string; // recording path
  t: string; // recording title
  s: number; // start time
  e: number; // end time
  x: string; // original text
  n: string; // normalized text
  i: number; // segment index
}

// Type for the search index
interface SearchIndex {
  index: SearchIndexEntry[];
}

// Type for a unified search result
interface SearchResult {
  recordingPath: string;
  recordingTitle: string;
  startTime: number;
  endTime: number;
  text: string;
  highlightedText: React.ReactNode;
  /** Semantic similarity score (0-1), only present in semantic mode */
  score?: number;
}

type SearchMode = "text" | "semantic";

// Maximum results to display
const MAX_RESULTS = 50;

// Minimum query length to trigger search
const MIN_QUERY_LENGTH = 2;

// Debounce delay for semantic search (ms)
const SEMANTIC_DEBOUNCE_MS = 300;

/**
 * Hook to load the text search index
 */
function useSearchIndex() {
  return useQuery<SearchIndex>({
    queryKey: ["searchIndex"],
    queryFn: async () => {
      const response = await fetch("/search-index.json");
      if (!response.ok) {
        throw new Error("Failed to load search index");
      }
      return response.json();
    },
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

/**
 * Highlight matching text in a string (for text search mode)
 */
function highlightMatch(text: string, query: string): React.ReactNode {
  const normalizedText = text.toLowerCase();
  const normalizedQuery = query.toLowerCase();
  const index = normalizedText.indexOf(normalizedQuery);

  if (index === -1) {
    return text;
  }

  const before = text.substring(0, index);
  const match = text.substring(index, index + query.length);
  const after = text.substring(index + query.length);

  return (
    <>
      {before}
      <mark className={styles.highlight}>{match}</mark>
      {after}
    </>
  );
}

/**
 * Text-based search: substring matching
 */
function searchText(index: SearchIndexEntry[], query: string): SearchResult[] {
  const normalizedQuery = query.toLowerCase().trim();

  if (normalizedQuery.length < MIN_QUERY_LENGTH) {
    return [];
  }

  const results: SearchResult[] = [];

  for (const entry of index) {
    if (entry.n.includes(normalizedQuery)) {
      results.push({
        recordingPath: entry.r,
        recordingTitle: entry.t,
        startTime: entry.s,
        endTime: entry.e,
        text: entry.x,
        highlightedText: highlightMatch(entry.x, query),
      });

      if (results.length >= MAX_RESULTS) {
        break;
      }
    }
  }

  return results;
}

/**
 * Convert semantic search results to unified format
 */
function semanticResultsToUnified(hits: SemanticSearchResult[]): SearchResult[] {
  return hits.map((hit) => ({
    recordingPath: hit.segment.r,
    recordingTitle: hit.segment.t,
    startTime: hit.segment.s,
    endTime: hit.segment.e,
    text: hit.segment.x,
    highlightedText: hit.segment.x,
    score: hit.score,
  }));
}

/**
 * Score bar visualization for semantic results
 */
function ScoreBar({ score }: { score: number }): React.ReactElement {
  const pct = Math.round(score * 100);
  return (
    <span className={styles.scoreBar} title={`Similarity: ${score.toFixed(3)}`}>
      <span className={styles.scoreBarFill} style={{ width: `${pct}%` }} />
      <span className={styles.scoreBarLabel}>{pct}%</span>
    </span>
  );
}

/**
 * TranscriptSearch Component — supports text and semantic search modes
 */
export default function TranscriptSearch(): React.ReactElement {
  const [query, setQuery] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [mode, setMode] = useState<SearchMode>("text");
  const navigate = useNavigate();
  const { data: searchIndexData, isLoading: textIndexLoading, error: textError } = useSearchIndex();

  // Semantic engine state
  const [semanticReady, setSemanticReady] = useState(false);
  const [semanticStatus, setSemanticStatus] = useState<string>("");
  const [semanticResults, setSemanticResults] = useState<SearchResult[]>([]);
  const [isSemanticSearching, setIsSemanticSearching] = useState(false);
  const [semanticError, setSemanticError] = useState<string | null>(null);
  const searchIdRef = useRef(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Initialize semantic engine
  useEffect(() => {
    const onProgress = (p: InitProgress) => {
      if (p.stage === "model" || p.stage === "index") {
        setSemanticStatus(p.message);
      }
      if (isIndexLoaded() && isModelLoaded()) {
        setSemanticReady(true);
        setSemanticStatus(`Ready — ${getSegmentCount()} segments`);
      }
    };

    initSemantic(onProgress).catch((err: Error) => {
      console.error("Semantic search init failed:", err);
      setSemanticError(err.message);
      setSemanticStatus(`Error: ${err.message}`);
    });
  }, []);

  // Text search results (synchronous, via useMemo)
  const textResults = useMemo(() => {
    if (mode !== "text" || !searchIndexData?.index || query.trim().length < MIN_QUERY_LENGTH) {
      return [];
    }
    return searchText(searchIndexData.index, query);
  }, [searchIndexData, query, mode]);

  // Run semantic search with debounce
  useEffect(() => {
    if (mode !== "semantic" || !semanticReady || query.trim().length < MIN_QUERY_LENGTH) {
      setSemanticResults([]);
      return;
    }

    if (debounceRef.current) clearTimeout(debounceRef.current);

    const id = ++searchIdRef.current;
    debounceRef.current = setTimeout(async () => {
      setIsSemanticSearching(true);
      try {
        const hits = await semanticSearch(query.trim(), { k: MAX_RESULTS, minScore: 0.15 });
        if (id === searchIdRef.current) {
          setSemanticResults(semanticResultsToUnified(hits));
        }
      } catch (err) {
        console.error("Semantic search error:", err);
        if (id === searchIdRef.current) {
          setSemanticResults([]);
        }
      } finally {
        if (id === searchIdRef.current) {
          setIsSemanticSearching(false);
        }
      }
    }, SEMANTIC_DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, mode, semanticReady]);

  const results = mode === "text" ? textResults : semanticResults;
  const isSearching = mode === "semantic" && isSemanticSearching;

  // Handle result click
  const handleResultClick = useCallback(
    (result: SearchResult) => {
      navigate(`/recording/${result.recordingPath}?t=${Math.floor(result.startTime)}`);
      setQuery("");
      setIsFocused(false);
    },
    [navigate]
  );

  // Handle clear
  const handleClear = useCallback(() => {
    setQuery("");
  }, []);

  // Toggle mode
  const handleToggleMode = useCallback(() => {
    setMode((prev) => (prev === "text" ? "semantic" : "text"));
  }, []);

  const showDropdown = isFocused && query.trim().length >= MIN_QUERY_LENGTH;
  const isLoading = mode === "text" ? textIndexLoading : false;
  const error = mode === "text" ? textError : semanticError ? new Error(semanticError) : null;

  return (
    <div className={styles.searchContainer}>
      <div className={styles.searchBox}>
        <div className={styles.searchInputWrapper}>
          <FontAwesomeIcon icon={faSearch} className={styles.searchIcon} />
          <input
            type="text"
            className={styles.searchInput}
            placeholder={
              mode === "text"
                ? "Search all transcripts..."
                : semanticReady
                  ? "Search by meaning across all transcripts..."
                  : "Loading semantic model..."
            }
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => {
              setTimeout(() => setIsFocused(false), 200);
            }}
            disabled={isLoading || (mode === "semantic" && !semanticReady)}
          />
          {query && (
            <button className={styles.clearButton} onClick={handleClear} aria-label="Clear search">
              <FontAwesomeIcon icon={faTimes} />
            </button>
          )}
          <button
            className={`${styles.modeToggle} ${mode === "semantic" ? styles.modeToggleActive : ""}`}
            onClick={handleToggleMode}
            aria-label={`Switch to ${mode === "text" ? "semantic" : "text"} search`}
            title={
              mode === "text"
                ? "Switch to semantic search (search by meaning)"
                : "Switch to text search (exact match)"
            }
          >
            <FontAwesomeIcon icon={mode === "text" ? faBrain : faFont} />
          </button>
        </div>

        {/* Semantic status indicator */}
        {mode === "semantic" && !semanticReady && !semanticError && (
          <div className={styles.loadingMessage}>
            <FontAwesomeIcon icon={faSpinner} spin />
            <span>{semanticStatus || "Initializing semantic search…"}</span>
          </div>
        )}

        {/* Loading state (text mode) */}
        {mode === "text" && isLoading && (
          <div className={styles.loadingMessage}>
            <FontAwesomeIcon icon={faSpinner} spin />
            <span>Loading search index...</span>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className={styles.errorMessage}>
            {mode === "semantic"
              ? "Semantic search failed to load. Try text search instead."
              : "Failed to load search index. Please refresh the page."}
          </div>
        )}

        {/* Results dropdown */}
        {showDropdown && !isLoading && !error && (
          <div className={styles.resultsDropdown}>
            {isSearching ? (
              <div className={styles.noResults}>
                <FontAwesomeIcon icon={faSpinner} spin /> Searching…
              </div>
            ) : results.length === 0 && query.length > 0 ? (
              <div className={styles.noResults}>No results found</div>
            ) : (
              <>
                <div className={styles.resultsHeader}>
                  {mode === "semantic" && (
                    <FontAwesomeIcon icon={faBrain} className={styles.headerModeIcon} />
                  )}
                  {results.length >= MAX_RESULTS
                    ? `Showing top ${MAX_RESULTS} results`
                    : `${results.length} result${results.length === 1 ? "" : "s"}`}
                </div>
                <div className={styles.resultsList}>
                  {results.map((result, index) => (
                    <button
                      key={`${result.recordingPath}-${result.startTime}-${index}`}
                      className={styles.resultItem}
                      onClick={() => handleResultClick(result)}
                    >
                      <div className={styles.resultHeader}>
                        <div className={styles.resultTitle}>{result.recordingTitle}</div>
                        <div className={styles.resultTimestamp}>{formatTime(result.startTime)}</div>
                      </div>
                      <div className={styles.resultText}>{result.highlightedText}</div>
                      {result.score !== undefined && (
                        <div className={styles.resultScoreRow}>
                          <ScoreBar score={result.score} />
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
