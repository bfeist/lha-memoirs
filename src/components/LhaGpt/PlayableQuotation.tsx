import React, { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  getRecordingById,
  getRecordingByPath,
  type RecordingConfig,
} from "../../config/recordings";
import { useTranscript, useChapters } from "../../hooks/useRecordingData";
import { AudioExcerptPlayer } from "../AudioExcerptPlayer/AudioExcerptPlayer";
import styles from "../AudioExcerptPlayer/AudioExcerptPlayer.module.css";

interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

interface PlayableQuotationProps {
  /** Recording ID (e.g., "memoirs_main") */
  recordingId: string;
  /** Start time in seconds - used to look up the transcript segment */
  startSeconds: number;
  /** Optional: number of segments to play (defaults to 3) */
  segmentCount?: number;
  /** Callback when the quotation starts playing (to pause others) */
  onPlay?: () => void;
  /** Whether this quotation should be stopped (controlled by parent) */
  shouldStop?: boolean;
  /** Callback when navigating away (to close chat panel) */
  onNavigate?: () => void;
}

/**
 * Find multiple consecutive transcript segments starting at or near the given timestamp.
 * Returns the matched segment plus the specified number of following segments.
 * Uses a small tolerance to handle floating point differences.
 * If nextChapterStartTime is provided, filters out segments that start at or after it.
 */
function findSegmentsByStartTime(
  segments: TranscriptSegment[],
  startSeconds: number,
  count: number = 3,
  nextChapterStartTime?: number
): TranscriptSegment[] {
  if (segments.length === 0) return [];

  const tolerance = 0.5; // Allow 0.5 second tolerance for matching

  // First try exact match
  let startIndex = segments.findIndex((s) => Math.abs(s.start - startSeconds) < tolerance);

  // If no exact match, find the segment that contains this timestamp
  if (startIndex === -1) {
    startIndex = segments.findIndex((s) => startSeconds >= s.start && startSeconds < s.end);
  }

  // If still no match, find the closest segment by start time
  if (startIndex === -1) {
    let closestIndex = 0;
    let minDistance = Math.abs(segments[0].start - startSeconds);

    for (let i = 1; i < segments.length; i++) {
      const distance = Math.abs(segments[i].start - startSeconds);
      if (distance < minDistance) {
        minDistance = distance;
        closestIndex = i;
      }
    }
    startIndex = closestIndex;
  }

  // Return the matched segment plus the next (count - 1) segments
  const endIndex = Math.min(startIndex + count, segments.length);
  const selectedSegments = segments.slice(startIndex, endIndex);

  // Filter out segments that cross into the next chapter
  if (nextChapterStartTime !== undefined) {
    return selectedSegments.filter((seg) => seg.start < nextChapterStartTime);
  }

  return selectedSegments;
}

/**
 * Get the audio URL for a recording (uses static_assets path).
 */
function getAudioUrl(recording: RecordingConfig): string {
  return `/static_assets/audio/${recording.path}/audio_original.mp3`;
}

/**
 * A playable quotation component that displays a quoted excerpt from the transcript
 * with an inline play button that plays that section of the recording.
 */
export function PlayableQuotation({
  recordingId,
  startSeconds,
  segmentCount = 3,
  onPlay,
  shouldStop,
  onNavigate,
}: PlayableQuotationProps): React.ReactElement {
  const navigate = useNavigate();

  // Look up the recording configuration
  const recording = getRecordingById(recordingId) || getRecordingByPath(recordingId);

  // Fetch transcript using the shared hook (with React Query caching)
  const transcriptQuery = useTranscript(recording?.path || "");

  // Fetch chapters data to respect chapter boundaries
  const chaptersQuery = useChapters(recording?.path || "");

  // Find the next chapter start time to prevent crossing chapter boundaries
  const nextChapterStartTime = useMemo(() => {
    if (!chaptersQuery.data?.chapters) return undefined;

    const chapters = chaptersQuery.data.chapters;
    // Find the chapter that starts after our startSeconds
    const nextChapter = chapters.find((chapter) => chapter.startTime > startSeconds);

    return nextChapter?.startTime;
  }, [chaptersQuery.data?.chapters, startSeconds]);

  // Find the segments matching startSeconds (multiple consecutive segments)
  // Filter out any that would cross into the next chapter
  const segments = useMemo(() => {
    if (!transcriptQuery.data?.segments) return [];
    return findSegmentsByStartTime(
      transcriptQuery.data.segments,
      startSeconds,
      segmentCount,
      nextChapterStartTime
    );
  }, [transcriptQuery.data, startSeconds, segmentCount, nextChapterStartTime]);

  // Build audio URL using static_assets path
  const audioUrl = recording ? getAudioUrl(recording) : null;

  // Get the combined text from all segments
  const combinedText = segments.map((s) => s.text).join(" ");

  // Get start and end times
  const startTime = segments[0]?.start ?? startSeconds;
  const endTime = segments[segments.length - 1]?.end ?? startSeconds + 30;

  // Format time as MM:SS helper for error display
  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  // Navigate to the full recording at this timestamp
  const handleNavigateToRecording = () => {
    if (!recording) return;
    onNavigate?.();
    navigate(`/recording/${recording.id}?t=${Math.floor(startSeconds)}`);
  };

  // Loading state while fetching transcript
  if (transcriptQuery.isLoading) {
    return (
      <div className={styles.playerCard}>
        <div className={styles.loadingContent}>
          <span className={styles.loader} />
          <p className={styles.quoteText}>Loading transcript...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (transcriptQuery.isError || !recording || !audioUrl || segments.length === 0) {
    const errorMsg = transcriptQuery.isError
      ? `Failed to load transcript: ${transcriptQuery.error?.message}`
      : segments.length === 0
        ? `No segments found at ${formatTime(startSeconds)}`
        : `Unknown recording: ${recordingId}`;

    return (
      <div className={styles.playerCard}>
        <div className={styles.playerHeader}>
          <span className={styles.timestamp}>{formatTime(startSeconds)}</span>
        </div>
        <p className={styles.quoteText}>{errorMsg}</p>
      </div>
    );
  }

  return (
    <AudioExcerptPlayer
      recordingTitle={recording.title}
      text={combinedText}
      audioUrl={audioUrl}
      startTime={startTime}
      endTime={endTime}
      onNavigate={handleNavigateToRecording}
      onPlay={onPlay}
      shouldStop={shouldStop}
    />
  );
}

export default PlayableQuotation;
