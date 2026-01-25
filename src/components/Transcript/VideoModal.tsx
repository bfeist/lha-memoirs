import { useEffect, useRef, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faTimes, faPlay, faPause } from "@fortawesome/free-solid-svg-icons";
import { formatVideoCaption, getVideoUrl } from "./InlineVideoPlayer";
import styles from "./VideoModal.module.css";

export const VideoModal: React.FC<{
  video: Video | null;
  startTime?: number;
  endTime?: number;
  onClose: () => void;
}> = ({ video, startTime, endTime, onClose }) => {
  const overlayRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPaused, setIsPaused] = useState(false);
  const [showControls, setShowControls] = useState(true);
  const hideTimeoutRef = useRef<number | null>(null);

  // Handle looping between start and end times
  useEffect(() => {
    const videoEl = videoRef.current;
    if (!videoEl || !video) return;

    // Set initial start time if specified
    if (startTime !== undefined && startTime > 0) {
      videoEl.currentTime = startTime;
    }

    const handleTimeUpdate = () => {
      if (endTime !== undefined && videoEl.currentTime >= endTime) {
        videoEl.currentTime = startTime ?? 0;
      }
    };

    // Only add listener if we have an end time to loop at
    if (endTime !== undefined) {
      videoEl.addEventListener("timeupdate", handleTimeUpdate);
      return () => videoEl.removeEventListener("timeupdate", handleTimeUpdate);
    }
  }, [video, startTime, endTime]);

  // Handle play state changes
  useEffect(() => {
    const videoEl = videoRef.current;
    if (!videoEl || !video) return;

    const handlePlay = () => setIsPaused(false);
    const handlePause = () => setIsPaused(true);

    videoEl.addEventListener("play", handlePlay);
    videoEl.addEventListener("pause", handlePause);

    return () => {
      videoEl.removeEventListener("play", handlePlay);
      videoEl.removeEventListener("pause", handlePause);
    };
  }, [video]);

  // Toggle play/pause and reset controls timeout
  const togglePlayPause = useCallback(() => {
    const videoEl = videoRef.current;
    if (!videoEl) return;

    if (videoEl.paused) {
      videoEl.play();
    } else {
      videoEl.pause();
    }
  }, []);

  // Reset controls visibility and auto-hide timeout (for user interactions)
  const resetControlsTimeout = useCallback(() => {
    setShowControls(true);
    if (hideTimeoutRef.current) {
      window.clearTimeout(hideTimeoutRef.current);
    }
    // Only start auto-hide timeout if video is playing
    if (videoRef.current && !videoRef.current.paused) {
      hideTimeoutRef.current = window.setTimeout(() => {
        setShowControls(false);
      }, 100);
    }
  }, []);

  // Set up auto-hide timeout when video opens or play state changes
  useEffect(() => {
    if (!video) return;

    // Clear any existing timeout
    if (hideTimeoutRef.current) {
      window.clearTimeout(hideTimeoutRef.current);
    }

    // Set up new timeout if video is playing
    if (!isPaused) {
      hideTimeoutRef.current = window.setTimeout(() => {
        setShowControls(false);
      }, 3000);
    }

    return () => {
      if (hideTimeoutRef.current) {
        window.clearTimeout(hideTimeoutRef.current);
      }
    };
  }, [video, isPaused]);

  // Handle escape key and click outside
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === " ") {
        e.preventDefault();
        togglePlayPause();
        resetControlsTimeout();
      }
    };

    const handleClickOutside = (e: MouseEvent) => {
      if (e.target === overlayRef.current) {
        onClose();
      }
    };

    if (video) {
      document.addEventListener("keydown", handleKeyDown);
      document.addEventListener("click", handleClickOutside);
      document.body.style.overflow = "hidden";
    }

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("click", handleClickOutside);
      document.body.style.overflow = "";
    };
  }, [video, onClose, togglePlayPause, resetControlsTimeout]);

  if (!video) return null;

  const caption = formatVideoCaption(video);

  return createPortal(
    <div
      ref={overlayRef}
      className={styles.overlay}
      role="dialog"
      aria-modal="true"
      aria-label={caption || "Video player"}
      onMouseMove={resetControlsTimeout}
      onTouchStart={resetControlsTimeout}
    >
      <button
        type="button"
        className={styles.closeButton}
        onClick={onClose}
        aria-label="Close video player"
      >
        <FontAwesomeIcon icon={faTimes} />
      </button>

      <div className={styles.content}>
        <div className={styles.videoWrapper}>
          <video
            ref={videoRef}
            className={styles.video}
            src={getVideoUrl(video.filename)}
            autoPlay
            muted
            loop={endTime === undefined}
            playsInline
            onClick={togglePlayPause}
          />

          <div className={`${styles.controls} ${showControls || isPaused ? styles.visible : ""}`}>
            <button
              type="button"
              className={styles.controlButton}
              onClick={togglePlayPause}
              aria-label={isPaused ? "Play" : "Pause"}
            >
              <FontAwesomeIcon icon={isPaused ? faPlay : faPause} />
            </button>
          </div>
        </div>

        {caption && <p className={styles.caption}>{caption}</p>}
      </div>
    </div>,
    document.body
  );
};
