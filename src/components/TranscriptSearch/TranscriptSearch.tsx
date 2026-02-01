import { useState, useMemo, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faSearch, faSpinner, faTimes } from "@fortawesome/free-solid-svg-icons";
import { formatTime } from "../../hooks/useRecordingData";
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

// Type for a search result
interface SearchResult {
  recordingPath: string;
  recordingTitle: string;
  startTime: number;
  endTime: number;
  text: string;
  highlightedText: React.ReactNode;
}

// Maximum results to display
const MAX_RESULTS = 100;

// Minimum query length to trigger search
const MIN_QUERY_LENGTH = 2;

/**
 * Hook to load the search index
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
    staleTime: Infinity, // Index never changes during a session
    gcTime: Infinity, // Keep cached forever
  });
}

/**
 * Highlight matching text in a string
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
 * Search the index for matches
 */
function searchIndex(index: SearchIndexEntry[], query: string): SearchResult[] {
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

      // Stop at max results for performance
      if (results.length >= MAX_RESULTS) {
        break;
      }
    }
  }

  return results;
}

/**
 * TranscriptSearch Component
 */
export default function TranscriptSearch(): React.ReactElement {
  const [query, setQuery] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const navigate = useNavigate();
  const { data: searchIndexData, isLoading, error } = useSearchIndex();

  // Search results
  const results = useMemo(() => {
    if (!searchIndexData?.index || query.trim().length < MIN_QUERY_LENGTH) {
      return [];
    }
    return searchIndex(searchIndexData.index, query);
  }, [searchIndexData, query]);

  // Handle result click
  const handleResultClick = useCallback(
    (result: SearchResult) => {
      // Navigate to recording with timestamp
      navigate(`/recording/${result.recordingPath}?t=${Math.floor(result.startTime)}`);
      // Clear search and close dropdown
      setQuery("");
      setIsFocused(false);
    },
    [navigate]
  );

  // Handle clear
  const handleClear = useCallback(() => {
    setQuery("");
  }, []);

  // Show dropdown when focused and has query
  const showDropdown = isFocused && query.trim().length >= MIN_QUERY_LENGTH;

  return (
    <div className={styles.searchContainer}>
      <div className={styles.searchBox}>
        <div className={styles.searchInputWrapper}>
          <FontAwesomeIcon icon={faSearch} className={styles.searchIcon} />
          <input
            type="text"
            className={styles.searchInput}
            placeholder="Search all transcripts..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setIsFocused(true)}
            onBlur={() => {
              // Delay to allow click events on results
              setTimeout(() => setIsFocused(false), 200);
            }}
            disabled={isLoading}
          />
          {query && (
            <button className={styles.clearButton} onClick={handleClear} aria-label="Clear search">
              <FontAwesomeIcon icon={faTimes} />
            </button>
          )}
        </div>

        {/* Loading state */}
        {isLoading && (
          <div className={styles.loadingMessage}>
            <FontAwesomeIcon icon={faSpinner} spin />
            <span>Loading search index...</span>
          </div>
        )}

        {/* Error state */}
        {error && (
          <div className={styles.errorMessage}>
            Failed to load search index. Please refresh the page.
          </div>
        )}

        {/* Results dropdown */}
        {showDropdown && !isLoading && !error && (
          <div className={styles.resultsDropdown}>
            {results.length === 0 ? (
              <div className={styles.noResults}>No results found</div>
            ) : (
              <>
                <div className={styles.resultsHeader}>
                  {results.length >= MAX_RESULTS
                    ? `Showing first ${MAX_RESULTS} results`
                    : `${results.length} result${results.length === 1 ? "" : "s"}`}
                </div>
                <div className={styles.resultsList}>
                  {results.map((result, index) => (
                    <button
                      key={`${result.recordingPath}-${result.startTime}-${index}`}
                      className={styles.resultItem}
                      onClick={() => handleResultClick(result)}
                    >
                      <div className={styles.resultTitle}>{result.recordingTitle}</div>
                      <div className={styles.resultTimestamp}>{formatTime(result.startTime)}</div>
                      <div className={styles.resultText}>{result.highlightedText}</div>
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
