import { useState, useEffect, useRef } from "react";
import type { TimelineData } from "../types/timeline";

// Cache for timeline data to avoid refetching
let timelineCache: TimelineData | null = null;
let timelineFetchPromise: Promise<TimelineData> | null = null;

/**
 * Hook to fetch and use timeline data from timeline.json
 */
export function useTimeline(): {
  data: TimelineData | null;
  isLoading: boolean;
  error: Error | null;
} {
  const [timelineData, setTimelineData] = useState<TimelineData | null>(timelineCache);
  const [isLoading, setIsLoading] = useState(!timelineCache);
  const [error, setError] = useState<Error | null>(null);
  const isMounted = useRef(true);

  useEffect(() => {
    isMounted.current = true;

    // If already cached, no need to fetch
    if (timelineCache) {
      return;
    }

    if (!timelineFetchPromise) {
      timelineFetchPromise = fetch("/timeline.json")
        .then((res) => {
          if (!res.ok) throw new Error("Failed to fetch timeline.json");
          return res.json() as Promise<TimelineData>;
        })
        .then((data) => {
          timelineCache = data;
          return data;
        });
    }

    timelineFetchPromise
      .then((data) => {
        if (isMounted.current) {
          setTimelineData(data);
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

  return {
    data: timelineData,
    isLoading,
    error,
  };
}
