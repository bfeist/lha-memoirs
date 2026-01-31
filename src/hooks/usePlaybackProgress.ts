import { useCallback, useEffect, useRef, useState } from "react";

const STORAGE_KEY_PREFIX = "lha-memoirs-progress-";
const SAVE_INTERVAL_MS = 5000; // Save every 5 seconds during playback
const MIN_PROGRESS_SECONDS = 10; // Don't save if less than 10 seconds in

export interface PlaybackProgress {
  time: number;
  savedAt: number; // Unix timestamp
  duration?: number;
}

/**
 * Hook to manage saving and restoring playback progress for a recording.
 * Progress is saved to localStorage and persists across sessions.
 */
export function usePlaybackProgress(recordingId: string | undefined): {
  savedProgress: PlaybackProgress | null;
  saveProgress: (time: number, duration?: number) => void;
  clearProgress: () => void;
  hasSavedProgress: boolean;
  progressPercentage: number | null;
} {
  const storageKey = recordingId ? `${STORAGE_KEY_PREFIX}${recordingId}` : null;
  const lastSavedTimeRef = useRef<number>(0);

  // Load saved progress synchronously during render (safe for localStorage)
  const loadProgress = (): PlaybackProgress | null => {
    if (!storageKey) return null;
    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        const progress: PlaybackProgress = JSON.parse(stored);
        const thirtyDaysAgo = Date.now() - 30 * 24 * 60 * 60 * 1000;
        if (progress.savedAt > thirtyDaysAgo && progress.time > MIN_PROGRESS_SECONDS) {
          return progress;
        }
        // Clear stale progress
        localStorage.removeItem(storageKey);
      }
    } catch {
      // Ignore parse errors
    }
    return null;
  };

  const [savedProgress, setSavedProgress] = useState<PlaybackProgress | null>(loadProgress);

  // Reload progress when storageKey changes
  useEffect(() => {
    setSavedProgress(loadProgress());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  // Save progress to localStorage (without triggering re-renders)
  const saveProgress = useCallback(
    (time: number, duration?: number) => {
      if (!storageKey) return;

      // Don't save if too early in the recording
      if (time < MIN_PROGRESS_SECONDS) return;

      // Don't save if we're near the end (within 30 seconds or 95% done)
      if (duration) {
        const nearEnd = time > duration - 30 || time / duration > 0.95;
        if (nearEnd) {
          // Clear progress when finished
          localStorage.removeItem(storageKey);
          setSavedProgress(null);
          return;
        }
      }

      // Throttle saves - only save if we've moved at least 2 seconds
      if (Math.abs(time - lastSavedTimeRef.current) < 2) return;
      lastSavedTimeRef.current = time;

      const progress: PlaybackProgress = {
        time,
        savedAt: Date.now(),
        duration,
      };

      try {
        localStorage.setItem(storageKey, JSON.stringify(progress));
        // Don't call setSavedProgress here - it causes unnecessary re-renders
        // The savedProgress state is only used for showing the resume banner,
        // which is displayed once at load time, not during playback
      } catch {
        // localStorage might be full or disabled
        console.warn("Failed to save playback progress");
      }
    },
    [storageKey]
  );

  // Clear progress (e.g., when user explicitly restarts)
  const clearProgress = useCallback(() => {
    if (!storageKey) return;
    localStorage.removeItem(storageKey);
    setSavedProgress(null);
    lastSavedTimeRef.current = 0;
  }, [storageKey]);

  const hasSavedProgress = savedProgress !== null && savedProgress.time > MIN_PROGRESS_SECONDS;

  const progressPercentage =
    savedProgress?.duration && savedProgress.duration > 0
      ? Math.round((savedProgress.time / savedProgress.duration) * 100)
      : null;

  return {
    savedProgress,
    saveProgress,
    clearProgress,
    hasSavedProgress,
    progressPercentage,
  };
}

/**
 * Hook to auto-save progress periodically during playback.
 * Call this in the component that has access to the current time.
 */
export function useAutoSaveProgress(
  recordingId: string | undefined,
  currentTime: number,
  duration: number,
  isPlaying: boolean
): {
  savedProgress: PlaybackProgress | null;
  clearProgress: () => void;
  hasSavedProgress: boolean;
  progressPercentage: number | null;
} {
  const { savedProgress, saveProgress, clearProgress, hasSavedProgress, progressPercentage } =
    usePlaybackProgress(recordingId);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Save progress periodically while playing
  useEffect(() => {
    if (isPlaying && duration > 0) {
      // Save immediately when starting playback
      saveProgress(currentTime, duration);

      // Set up interval for periodic saves
      intervalRef.current = setInterval(() => {
        saveProgress(currentTime, duration);
      }, SAVE_INTERVAL_MS);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [isPlaying, currentTime, duration, saveProgress]);

  // Save on page unload
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (currentTime > MIN_PROGRESS_SECONDS && duration > 0) {
        saveProgress(currentTime, duration);
      }
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [currentTime, duration, saveProgress]);

  return { savedProgress, clearProgress, hasSavedProgress, progressPercentage };
}

/**
 * Format time for display (e.g., "1:23:45" or "23:45")
 */
export function formatProgressTime(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hours > 0) {
    return `${hours}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

/**
 * Format how long ago progress was saved
 */
export function formatTimeSince(timestamp: number): string {
  const seconds = Math.floor((Date.now() - timestamp) / 1000);

  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
  if (seconds < 604800) return `${Math.floor(seconds / 86400)} days ago`;
  return `${Math.floor(seconds / 604800)} weeks ago`;
}
