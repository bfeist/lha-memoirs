import { useEffect, useRef, useCallback, useState } from "react";
import Peaks, { type PeaksInstance, type PeaksOptions } from "peaks.js";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faPlay,
  faPause,
  faArrowRotateLeft,
  faArrowRotateRight,
  faRotate,
} from "@fortawesome/free-solid-svg-icons";
import styles from "./AudioPlayer.module.css";

interface AudioPlayerProps {
  audioUrl: string;
  originalAudioUrl?: string;
  waveformDataUrl: string;
  regions?: PeaksRegion[];
  currentChapterId?: string | null;
  onTimeUpdate?: (currentTime: number) => void;
  onRegionClick?: (regionId: string) => void;
  onReady?: (peaksInstance: PeaksInstance) => void;
  onReload?: () => void;
}

// Throttle function for time updates to prevent excessive re-renders
function throttle<T extends (...args: Parameters<T>) => void>(
  func: T,
  limit: number
): (...args: Parameters<T>) => void {
  let inThrottle = false;
  return (...args: Parameters<T>) => {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => {
        inThrottle = false;
      }, limit);
    }
  };
}

// Segment color constants
const SEGMENT_COLOR_DEFAULT = "rgba(100, 149, 237, 0.3)";
const SEGMENT_COLOR_ACTIVE = "rgba(212, 175, 55, 0.5)";

export function AudioPlayer({
  audioUrl,
  originalAudioUrl,
  waveformDataUrl,
  regions = [],
  currentChapterId,
  onTimeUpdate,
  onRegionClick,
  onReady,
  onReload,
}: AudioPlayerProps): React.ReactElement {
  const zoomviewContainerRef = useRef<HTMLDivElement>(null);
  const overviewContainerRef = useRef<HTMLDivElement>(null);
  const audioElementRef = useRef<HTMLAudioElement>(null);
  const peaksInstanceRef = useRef<PeaksInstance | null>(null);

  // Store callbacks in refs to avoid dependency issues
  const onTimeUpdateRef = useRef(onTimeUpdate);
  const onRegionClickRef = useRef(onRegionClick);
  const onReadyRef = useRef(onReady);
  const regionsRef = useRef(regions);
  const previousChapterIdRef = useRef<string | null | undefined>(null);

  // Keep refs updated
  useEffect(() => {
    onTimeUpdateRef.current = onTimeUpdate;
    onRegionClickRef.current = onRegionClick;
    onReadyRef.current = onReady;
    regionsRef.current = regions;
  });

  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isReady, setIsReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Toggle between original and enhanced audio
  // Default to original (false) so the unprocessed audio plays by default
  const [useEnhanced, setUseEnhanced] = useState(false);

  // Format time as MM:SS
  const formatTime = useCallback((seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }, []);

  // Initialize Peaks.js
  useEffect(() => {
    if (
      !zoomviewContainerRef.current ||
      !overviewContainerRef.current ||
      !audioElementRef.current
    ) {
      console.log("AudioPlayer: Waiting for DOM refs to be ready");
      return;
    }

    console.log("AudioPlayer: Initializing Peaks.js with:", {
      audioUrl,
      waveformDataUrl,
      regionsCount: regionsRef.current.length,
    });

    // Try JSON format first as it's more reliable, fall back to binary
    const useJsonWaveform = waveformDataUrl.endsWith(".json");

    const options: PeaksOptions = {
      zoomview: {
        container: zoomviewContainerRef.current,
        waveformColor: "rgba(200, 170, 120, 0.7)",
        playedWaveformColor: "rgba(222, 185, 65, 0.95)",
        playheadColor: "#e4bf47",
        playheadTextColor: "#ffffff",
        axisLabelColor: "#bbbbbb",
        axisGridlineColor: "#444444",
      },
      overview: {
        container: overviewContainerRef.current,
        waveformColor: "rgba(200, 170, 120, 0.5)",
        playedWaveformColor: "rgba(222, 185, 65, 0.8)",
        playheadColor: "#e4bf47",
        highlightColor: "rgba(212, 175, 55, 0.15)",
        axisLabelColor: "#bbbbbb",
        axisGridlineColor: "#444444",
      },
      mediaElement: audioElementRef.current,
      dataUri: useJsonWaveform
        ? {
            json: waveformDataUrl,
          }
        : {
            arraybuffer: waveformDataUrl,
          },
      keyboard: true,
      showPlayheadTime: true,
      zoomLevels: [2400, 3200, 4096, 8192],
      segmentOptions: {
        overlay: true,
        markers: false,
        overlayColor: SEGMENT_COLOR_DEFAULT,
        overlayOpacity: 0.3,
        overlayBorderColor: "rgba(100, 149, 237, 0.5)",
        overlayBorderWidth: 1,
        overlayCornerRadius: 2,
        overlayOffset: 6,
      },
      // Disable segment labels to avoid cluttering the waveform
      createSegmentLabel: () => null,
    };

    Peaks.init(options, (err, peaks) => {
      if (err) {
        console.error("Peaks.js initialization error:", err);
        setError(`Failed to initialize audio player: ${err.message}`);
        return;
      }

      console.log("AudioPlayer: Peaks.js initialized successfully");

      if (peaks) {
        peaksInstanceRef.current = peaks;
        setIsReady(true);

        // Set duration when audio is loaded
        const audio = audioElementRef.current;
        if (audio) {
          const handleLoadedMetadata = (): void => {
            setDuration(audio.duration);
          };
          audio.addEventListener("loadedmetadata", handleLoadedMetadata);

          if (audio.duration) {
            setDuration(audio.duration);
          }
        }

        // Add regions if provided
        const currentRegions = regionsRef.current;
        if (currentRegions.length > 0) {
          const view = peaks.views.getView("zoomview");
          if (view) {
            currentRegions.forEach((region) => {
              // Validate region times before adding
              if (region.endTime > region.startTime) {
                peaks.segments.add({
                  id: region.id,
                  startTime: region.startTime,
                  endTime: region.endTime,
                  // Don't set labelText - we only want color overlays, not labels
                  color: region.color,
                });
              } else {
                console.warn(
                  `Skipping invalid region ${region.id}: endTime (${region.endTime}) <= startTime (${region.startTime})`
                );
              }
            });
          }
        }

        // Set up time update handler with throttling to prevent UI jank
        // Peaks.js fires timeupdate very frequently; we only update React state every 250ms
        const throttledTimeUpdate = throttle((time: number) => {
          setCurrentTime(time);
          onTimeUpdateRef.current?.(time);
        }, 250);

        peaks.on("player.timeupdate", throttledTimeUpdate);

        // Set up play/pause handlers via Peaks.js events
        peaks.on("player.playing", () => setIsPlaying(true));
        peaks.on("player.pause", () => setIsPlaying(false));

        // Also listen directly on audio element for cases where we change src directly
        // (Peaks.js events may not fire when we swap audio sources)
        const audioEl = audioElementRef.current;
        if (audioEl) {
          audioEl.addEventListener("pause", () => setIsPlaying(false));
          audioEl.addEventListener("play", () => setIsPlaying(true));
        }

        // Segment click handler
        peaks.on("segments.click", (event) => {
          if (event.segment) {
            onRegionClickRef.current?.(event.segment.id ?? "");
          }
        });

        onReadyRef.current?.(peaks);
      }
    });

    // Handle container resize using ResizeObserver
    const resizeObserver = new ResizeObserver(() => {
      if (peaksInstanceRef.current) {
        const zoomView = peaksInstanceRef.current.views.getView("zoomview");
        const overviewView = peaksInstanceRef.current.views.getView("overview");

        if (zoomView) {
          zoomView.fitToContainer();
        }
        if (overviewView) {
          overviewView.fitToContainer();
        }
      }
    });

    if (zoomviewContainerRef.current) {
      resizeObserver.observe(zoomviewContainerRef.current);
    }
    if (overviewContainerRef.current) {
      resizeObserver.observe(overviewContainerRef.current);
    }

    return () => {
      resizeObserver.disconnect();
      if (peaksInstanceRef.current) {
        peaksInstanceRef.current.destroy();
        peaksInstanceRef.current = null;
      }
      // Reset playing state when audio source changes
      setIsPlaying(false);
      setIsReady(false);
    };
  }, [audioUrl, waveformDataUrl]);

  // Switch audio source when toggling between original and enhanced
  // This approach swaps the src on the single audio element that Peaks.js controls,
  // which is more reliable on iOS than trying to sync two separate audio elements.
  useEffect(() => {
    const audio = audioElementRef.current;
    if (!audio || !originalAudioUrl) return;

    const targetSrc = useEnhanced ? audioUrl : originalAudioUrl;
    const currentSrc = audio.currentSrc;

    // Only swap if the source is actually different
    if (currentSrc && !currentSrc.endsWith(targetSrc.replace(/^\.?\//, ""))) {
      const wasPlaying = !audio.paused;
      const savedTime = audio.currentTime;

      // Change the source - this will pause the audio
      audio.src = targetSrc;
      audio.load();

      // Use queueMicrotask to update state asynchronously (satisfies lint rule)
      // This ensures the button shows "Play" while loading
      queueMicrotask(() => setIsPlaying(false));

      // Restore playback position and state once loaded
      const handleCanPlay = (): void => {
        audio.currentTime = savedTime;
        if (wasPlaying) {
          audio
            .play()
            .then(() => setIsPlaying(true))
            .catch(() => {
              // Ignore autoplay errors
            });
        }
        audio.removeEventListener("canplay", handleCanPlay);
      };
      audio.addEventListener("canplay", handleCanPlay);
    }
  }, [useEnhanced, audioUrl, originalAudioUrl]);

  // Update regions when they change
  useEffect(() => {
    const peaks = peaksInstanceRef.current;
    if (!peaks || !isReady) return;

    // Clear existing segments
    peaks.segments.removeAll();

    // Add new regions
    regions.forEach((region) => {
      // Validate region times before adding
      if (region.endTime > region.startTime) {
        peaks.segments.add({
          id: region.id,
          startTime: region.startTime,
          endTime: region.endTime,
          // Don't set labelText - we only want color overlays, not labels
          color: region.color,
        });
      } else {
        console.warn(
          `Skipping invalid region ${region.id}: endTime (${region.endTime}) <= startTime (${region.startTime})`
        );
      }
    });
  }, [regions, isReady]);

  // Highlight the current chapter's segment
  useEffect(() => {
    const peaks = peaksInstanceRef.current;
    if (!peaks || !isReady) return;

    // Only update if the chapter has actually changed
    if (previousChapterIdRef.current === currentChapterId) return;
    previousChapterIdRef.current = currentChapterId;

    // Update all segment colors - highlight the active one, reset others
    const segments = peaks.segments.getSegments();
    segments.forEach((segment) => {
      const isActive = segment.id === currentChapterId;
      segment.update({
        color: isActive ? SEGMENT_COLOR_ACTIVE : SEGMENT_COLOR_DEFAULT,
      });
    });
  }, [currentChapterId, isReady]);

  // Play/pause toggle
  const togglePlayPause = useCallback(() => {
    const peaks = peaksInstanceRef.current;
    const audioElement = audioElementRef.current;
    if (!peaks || !audioElement) return;

    if (isPlaying) {
      peaks.player.pause();
    } else {
      // For iOS compatibility: call play() on audio element first to satisfy
      // user interaction requirement.
      const playPromise = audioElement.play();

      if (playPromise !== undefined) {
        playPromise
          .then(() => {
            // Audio play started successfully
            // Peaks event listeners will handle state updates
          })
          .catch((error) => {
            console.error("Failed to play audio:", error);
            setError("Failed to play audio. Please try again.");
          });
      }
    }
  }, [isPlaying]);

  // Seek to specific time
  const seekTo = useCallback((time: number) => {
    const peaks = peaksInstanceRef.current;
    if (peaks) {
      peaks.player.seek(time);
    }
  }, []);

  // Expose seekTo via ref for parent components
  useEffect(() => {
    // Make seekTo available globally for this instance
    (window as unknown as Record<string, unknown>).__peaksSeekTo = seekTo;
    return () => {
      delete (window as unknown as Record<string, unknown>).__peaksSeekTo;
    };
  }, [seekTo]);

  // Skip forward/backward
  const skip = useCallback(
    (seconds: number) => {
      seekTo(Math.max(0, Math.min(duration, currentTime + seconds)));
    },
    [currentTime, duration, seekTo]
  );

  if (error) {
    return (
      <div className={styles.error}>
        <p>⚠️ {error}</p>
        <p>Make sure the audio and waveform files are available.</p>
      </div>
    );
  }

  return (
    <div className={styles.playerContainer}>
      {/* Hidden audio element for enhanced audio - no captions needed for hidden player */}
      {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
      <audio
        ref={audioElementRef}
        preload="auto"
        src={originalAudioUrl && !useEnhanced ? originalAudioUrl : audioUrl}
        onError={(e) => {
          console.error("Audio element error:", e);
          const audioError = (e.target as HTMLAudioElement).error;
          if (audioError) {
            console.error("Audio error details:", {
              code: audioError.code,
              message: audioError.message,
            });
            setError(`Failed to load audio: ${audioError.message}`);
          }
        }}
        onLoadStart={() => console.log("Audio: Load started")}
        onLoadedMetadata={() => console.log("Audio: Metadata loaded")}
        onCanPlay={() => console.log("Audio: Can play")}
      />

      {/* Zoomview waveform */}
      <div className={styles.waveformSection}>
        <div ref={zoomviewContainerRef} className={styles.zoomview} />
      </div>

      {/* Overview waveform */}
      <div className={styles.overviewSection}>
        <div ref={overviewContainerRef} className={styles.overview} />
      </div>

      {/* Playback controls */}
      <div className={styles.controls}>
        {/* Audio toggle - only show if original audio is available */}
        {originalAudioUrl && (
          <div className={styles.audioToggle}>
            {/* Desktop version: switch with labels */}
            <span className={`${styles.toggleLabel} ${!useEnhanced ? styles.active : ""}`}>
              Original
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={useEnhanced}
              aria-label="Toggle between original and enhanced audio"
              className={`${styles.toggleSwitch} ${useEnhanced ? styles.enhanced : ""}`}
              onClick={() => setUseEnhanced(!useEnhanced)}
            >
              <span className={styles.toggleKnob} />
            </button>
            <span className={`${styles.toggleLabel} ${useEnhanced ? styles.active : ""}`}>
              Enhanced
            </span>
            {/* Mobile version: simple button showing current state */}
            <button
              type="button"
              aria-label="Toggle between original and enhanced audio"
              className={`${styles.toggleButton} ${useEnhanced ? styles.enhanced : ""}`}
              onClick={() => setUseEnhanced(!useEnhanced)}
            >
              {useEnhanced ? "Enhanced" : "Original"}
            </button>
          </div>
        )}

        <button
          onClick={() => skip(-10)}
          className={styles.skipButton}
          disabled={!isReady}
          aria-label="Skip back 10 seconds"
        >
          <FontAwesomeIcon icon={faArrowRotateLeft} />
          <span>10s</span>
        </button>

        <button
          onClick={togglePlayPause}
          className={styles.playButton}
          disabled={!isReady}
          aria-label={isPlaying ? "Pause" : "Play"}
        >
          <FontAwesomeIcon icon={isPlaying ? faPause : faPlay} />
          <span>{isPlaying ? "Pause" : "Play"}</span>
        </button>

        <button
          onClick={() => skip(10)}
          className={styles.skipButton}
          disabled={!isReady}
          aria-label="Skip forward 10 seconds"
        >
          <span>10s</span>
          <FontAwesomeIcon icon={faArrowRotateRight} />
        </button>

        <div className={styles.timeDisplay}>
          <span>{formatTime(currentTime)}</span>
          <span className={styles.timeSeparator}>/</span>
          <span>{formatTime(duration)}</span>
        </div>

        {onReload && import.meta.env.DEV && (
          <button
            onClick={onReload}
            className={styles.reloadButton}
            disabled={!isReady}
            type="button"
            aria-label="Reload transcript and chapters"
          >
            <FontAwesomeIcon icon={faRotate} />
          </button>
        )}

        {import.meta.env.DEV && (
          <span className={styles.secondsDisplay}>{currentTime.toFixed(2)}</span>
        )}
      </div>

      {!isReady && <div className={styles.loading}>Loading audio...</div>}
    </div>
  );
}

// Export a hook to get the seek function
export function usePeaksSeek(): (time: number) => void {
  return useCallback((time: number) => {
    const seekFn = (window as unknown as Record<string, (time: number) => void>).__peaksSeekTo;
    if (seekFn) {
      seekFn(time);
    }
  }, []);
}
