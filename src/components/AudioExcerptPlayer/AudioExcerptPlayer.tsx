import React, { useRef, useState, useCallback, useEffect } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faPlay, faStop, faArrowsTurnRight } from "@fortawesome/free-solid-svg-icons";
import styles from "./AudioExcerptPlayer.module.css";

export interface AudioExcerptPlayerProps {
  /** Title of the recording (e.g., "Memoirs Part 1") */
  recordingTitle?: string;
  /** Displayed text content */
  text: string;
  /** URL to the audio file */
  audioUrl: string | null;
  /** Start time in seconds */
  startTime: number;
  /** End time in seconds */
  endTime: number;
  /** Callback when the user clicks the navigate button */
  onNavigate?: () => void;
  /** Label for the navigate button (default: "Full Recording") */
  navigateLabel?: string;
  /** Callback when playback starts */
  onPlay?: () => void;
  /** Whether the playback should be stopped externally */
  shouldStop?: boolean;
}

/**
 * Format time as MM:SS
 */
const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
};

/**
 * A shared component that plays a specific excerpt of audio with a progress indicator.
 * Used by PlayableQuotation and PlacesSidePanel.
 */
export function AudioExcerptPlayer({
  recordingTitle,
  text,
  audioUrl,
  startTime,
  endTime,
  onNavigate,
  navigateLabel = "Full Recording",
  onPlay,
  shouldStop,
}: AudioExcerptPlayerProps): React.ReactElement {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [progress, setProgress] = useState(0);

  // Stop playback when shouldStop is set by parent
  useEffect(() => {
    if (shouldStop && isPlaying && audioRef.current) {
      audioRef.current.pause();
      setIsPlaying(false);
    }
  }, [shouldStop, isPlaying]);

  // Handle play/pause toggle
  const togglePlayback = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio || !audioUrl) return;

    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
    } else {
      // Notify parent that we're playing
      onPlay?.();

      setIsLoading(true);

      // Set the current time to start if we are at 0 progress or completed
      if (Math.abs(audio.currentTime - startTime) > 1 || progress === 0 || progress === 100) {
        audio.currentTime = startTime;
      }

      try {
        await audio.play();
        setIsPlaying(true);
      } catch (err) {
        console.error("Failed to play audio:", err);
      } finally {
        setIsLoading(false);
      }
    }
  }, [isPlaying, audioUrl, startTime, progress, onPlay]);

  // Update progress and stop at the end
  const handleTimeUpdate = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;

    // Calculate progress based on the excerpt duration
    const current = audio.currentTime;
    // Constrain current time for progress calculation
    const effectiveCurrent = Math.max(startTime, Math.min(current, endTime));

    const duration = endTime - startTime;
    const elapsed = effectiveCurrent - startTime;

    // Avoid division by zero
    const progressPercent = duration > 0 ? Math.min(100, (elapsed / duration) * 100) : 0;

    setProgress(progressPercent);

    // Stop at the end
    if (current >= endTime) {
      audio.pause();
      setIsPlaying(false);
      setProgress(100);
      // Reset to start for next play, but keep progress at 100 momentarily for visual
      // (or maybe reset progress to 0? PlayableQuotation resets to 0)
    }
  }, [startTime, endTime]);

  // Handle audio ended (natural end of file, though we usually stop at endTime)
  const handleEnded = useCallback(() => {
    setIsPlaying(false);
    setProgress(0);
  }, []);

  // When scrubbing or seeking happens externally (not supported UI-wise yet but good to have)
  const handlePause = useCallback(() => {
    setIsPlaying(false);
  }, []);

  return (
    <div className={styles.playerCard}>
      {/* Hidden audio element */}
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio
        ref={audioRef}
        src={audioUrl || undefined}
        preload="none"
        onTimeUpdate={handleTimeUpdate}
        onEnded={handleEnded}
        onPause={handlePause}
      />

      <div className={styles.playerHeader}>
        <div className={styles.headerTitle}>
          <span className={styles.timestamp}>{formatTime(startTime)}</span>
          {recordingTitle && <span className={styles.recordingTitle}>{recordingTitle}</span>}
        </div>

        <div className={styles.playerActions}>
          <button
            className={styles.playButton}
            onClick={togglePlayback}
            disabled={isLoading || !audioUrl}
            aria-label={isPlaying ? "Stop excerpt" : "Play excerpt"}
            title={isPlaying ? "Stop" : `Play from ${formatTime(startTime)}`}
          >
            {isLoading ? (
              <span className={styles.loader} />
            ) : (
              <>
                <FontAwesomeIcon icon={isPlaying ? faStop : faPlay} className={styles.playIcon} />
                <span>{isPlaying ? "Stop" : "Play Excerpt"}</span>
              </>
            )}
          </button>

          <button
            className={styles.jumpButton}
            onClick={onNavigate}
            disabled={!onNavigate}
            title={navigateLabel}
            aria-label={`${navigateLabel} at ${formatTime(startTime)}`}
          >
            {navigateLabel}
            <FontAwesomeIcon icon={faArrowsTurnRight} className={styles.jumpIcon} />
          </button>
        </div>
      </div>

      <div className={styles.quoteWrapper}>
        <p className={styles.quoteText}>&ldquo;{text}&rdquo;</p>

        {/* Progress bar */}
        <div className={styles.progressBar} style={{ opacity: isPlaying || progress > 0 ? 1 : 0 }}>
          <div className={styles.progressFill} style={{ width: `${progress}%` }} />
        </div>
      </div>
    </div>
  );
}
