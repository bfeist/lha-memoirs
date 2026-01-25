import { useRef, useEffect, useCallback, useState } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faPlay, faPause, faExpand } from "@fortawesome/free-solid-svg-icons";
import styles from "./VideoInlinePlayer.module.css";

// Build video URL from filename
export function getVideoUrl(filename: string): string {
  return `/static_assets/videos/${filename}.mp4`;
}

// Format caption with date, location, and credit
export function formatVideoCaption(video: Video): string {
  const parts: string[] = [];

  if (video.caption) {
    parts.push(video.caption);
  }

  const metadata: string[] = [];
  if (video.date) {
    metadata.push(video.date);
  }
  if (video.location && video.location !== "Unknown") {
    metadata.push(video.location);
  }
  if (video.credit) {
    metadata.push(`Film courtesy ${video.credit}`);
  }

  if (metadata.length > 0) {
    if (parts.length > 0) {
      parts.push(`(${metadata.join(", ")})`);
    } else {
      parts.push(metadata.join(", "));
    }
  }

  return parts.join(" ");
}

export const VideoInlinePlayer: React.FC<{
  video: Video;
  startTime?: number;
  endTime?: number;
  float?: "left" | "right";
  onOpenModal?: () => void;
}> = ({ video, startTime, endTime, float = "right", onOpenModal }) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isPaused, setIsPaused] = useState(false);
  const [isInViewport, setIsInViewport] = useState(false);

  // Lazy load video when in viewport using Intersection Observer
  useEffect(() => {
    const container = containerRef.current;
    const videoEl = videoRef.current;
    if (!container || !videoEl) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            // Video entered viewport - load and play
            setIsInViewport(true);
            if (!videoEl.src) {
              videoEl.src = getVideoUrl(video.filename);

              // Wait for metadata to load before setting time and playing
              const handleLoadedMetadata = () => {
                // Set start time if specified
                if (startTime !== undefined && startTime > 0) {
                  videoEl.currentTime = startTime;
                }
                // Autoplay when loaded
                videoEl.play().catch(() => {
                  // Autoplay may fail, that's okay
                });
              };

              videoEl.addEventListener("loadedmetadata", handleLoadedMetadata, { once: true });
            }
          } else {
            // Video left viewport - pause and unload
            setIsInViewport(false);
            videoEl.pause();
            videoEl.removeAttribute("src");
            videoEl.load(); // Clear the video buffer
          }
        });
      },
      {
        rootMargin: "50px", // Start loading slightly before entering viewport
        threshold: 0.1,
      }
    );

    observer.observe(container);

    return () => {
      observer.disconnect();
    };
  }, [video.filename, startTime]);

  // Handle looping between start and end times
  useEffect(() => {
    const videoEl = videoRef.current;
    if (!videoEl || !isInViewport) return;

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
  }, [startTime, endTime, isInViewport]);

  // Handle play state changes
  useEffect(() => {
    const videoEl = videoRef.current;
    if (!videoEl) return;

    const handlePlay = () => setIsPaused(false);
    const handlePause = () => setIsPaused(true);

    videoEl.addEventListener("play", handlePlay);
    videoEl.addEventListener("pause", handlePause);

    return () => {
      videoEl.removeEventListener("play", handlePlay);
      videoEl.removeEventListener("pause", handlePause);
    };
  }, []);

  const handleClick = useCallback(() => {
    const videoEl = videoRef.current;
    if (!videoEl) return;

    if (videoEl.paused) {
      videoEl.play();
    } else {
      videoEl.pause();
    }
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        handleClick();
      }
    },
    [handleClick]
  );

  const handleFullscreen = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      onOpenModal?.();
    },
    [onOpenModal]
  );

  const handlePlayPauseClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      handleClick();
    },
    [handleClick]
  );

  const caption = formatVideoCaption(video);

  return (
    <figure
      className={`${styles.videoPlayer} ${float === "left" ? styles.floatLeft : styles.floatRight}`}
    >
      <div
        ref={containerRef}
        className={styles.videoContainer}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        role="button"
        tabIndex={0}
        aria-label={isPaused ? "Play video" : "Pause video"}
      >
        <video
          ref={videoRef}
          className={styles.video}
          muted
          loop={endTime === undefined}
          playsInline
        />

        {/* Controls bar - appears on hover/touch */}
        <div className={styles.controlsBar}>
          <button
            type="button"
            className={styles.controlButton}
            onClick={handlePlayPauseClick}
            aria-label={isPaused ? "Play" : "Pause"}
          >
            <FontAwesomeIcon icon={isPaused ? faPlay : faPause} />
          </button>
          <button
            type="button"
            className={styles.controlButton}
            onClick={handleFullscreen}
            aria-label="Open fullscreen"
          >
            <FontAwesomeIcon icon={faExpand} />
          </button>
        </div>
      </div>

      {caption && <figcaption className={styles.caption}>{caption}</figcaption>}
    </figure>
  );
};
