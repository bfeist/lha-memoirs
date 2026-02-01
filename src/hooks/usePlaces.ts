import { useState, useEffect, useMemo, useRef } from "react";

// Cache for places data to avoid refetching
let placesCache: PlacesData | null = null;
let placesFetchPromise: Promise<PlacesData> | null = null;

/**
 * Hook to fetch and use places data from places.json
 */
export function usePlaces(): {
  places: Place[];
  placesByName: Map<string, Place>;
  isLoading: boolean;
  error: Error | null;
} {
  const [placesData, setPlacesData] = useState<PlacesData | null>(placesCache);
  const [isLoading, setIsLoading] = useState(!placesCache);
  const [error, setError] = useState<Error | null>(null);
  const isMounted = useRef(true);

  useEffect(() => {
    isMounted.current = true;

    // If already cached, no need to fetch
    if (placesCache) {
      return;
    }

    if (!placesFetchPromise) {
      placesFetchPromise = fetch("/places.json")
        .then((res) => {
          if (!res.ok) throw new Error("Failed to fetch places.json");
          return res.json() as Promise<PlacesData>;
        })
        .then((data) => {
          placesCache = data;
          return data;
        });
    }

    placesFetchPromise
      .then((data) => {
        if (isMounted.current) {
          setPlacesData(data);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted.current) {
          setError(err);
          setIsLoading(false);
        }
      });

    return () => {
      isMounted.current = false;
    };
  }, []);

  // Create a lookup map by name (case-insensitive)
  const placesByName = useMemo(() => {
    const map = new Map<string, Place>();
    if (placesData?.places) {
      for (const place of placesData.places) {
        // Store by lowercase name for case-insensitive lookup
        map.set(place.name.toLowerCase(), place);
      }
    }
    return map;
  }, [placesData]);

  return {
    places: placesData?.places || [],
    placesByName,
    isLoading,
    error,
  };
}

/**
 * Build a regex pattern that matches any of the place names
 * Sorts by length (longest first) to match longer names before shorter ones
 */
export function buildPlaceNamePattern(placeNames: string[]): RegExp | null {
  if (placeNames.length === 0) return null;

  // Sort by length descending so "Sioux Falls" matches before "Sioux"
  const sortedNames = [...placeNames].sort((a, b) => b.length - a.length);

  // Escape special regex characters in place names
  const escapedNames = sortedNames.map((name) => name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));

  // Create pattern that matches whole words only (with word boundaries)
  const pattern = escapedNames.join("|");
  return new RegExp(`\\b(${pattern})\\b`, "gi");
}

/**
 * Parse text and find place name matches
 * Returns an array of segments, each being either plain text or a place match
 */
export interface TextSegment {
  type: "text" | "place";
  content: string;
  place?: Place;
}

export function parseTextWithPlaces(
  text: string,
  placesByName: Map<string, Place>,
  placePattern: RegExp | null
): TextSegment[] {
  if (!placePattern || placesByName.size === 0) {
    return [{ type: "text", content: text }];
  }

  const segments: TextSegment[] = [];
  let lastIndex = 0;

  // Reset regex lastIndex before matching
  placePattern.lastIndex = 0;

  let match: RegExpExecArray | null;
  while ((match = placePattern.exec(text)) !== null) {
    const matchedText = match[0];
    const matchIndex = match.index;

    // Add text before the match
    if (matchIndex > lastIndex) {
      segments.push({
        type: "text",
        content: text.slice(lastIndex, matchIndex),
      });
    }

    // Look up the place (case-insensitive)
    const place = placesByName.get(matchedText.toLowerCase());
    if (place) {
      segments.push({
        type: "place",
        content: matchedText,
        place,
      });
    } else {
      // Fallback to text if place not found
      segments.push({
        type: "text",
        content: matchedText,
      });
    }

    lastIndex = matchIndex + matchedText.length;
  }

  // Add remaining text after last match
  if (lastIndex < text.length) {
    segments.push({
      type: "text",
      content: text.slice(lastIndex),
    });
  }

  return segments;
}
