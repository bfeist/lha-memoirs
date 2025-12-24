import { useEffect, useRef, useCallback, useState } from "react";
import Peaks, { type PeaksInstance, type PeaksOptions } from "peaks.js";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faPlay,
  faPause,
  faArrowRotateLeft,
  faArrowRotateRight,
} from "@fortawesome/free-solid-svg-icons";
import styles from "./AudioPlayer.module.css";

interface AudioPlayerProps {
  audioUrl: string;
  waveformDataUrl: string;
  regions?: PeaksRegion[];
  onTimeUpdate?: (currentTime: number) => void;
  onRegionClick?: (regionId: string) => void;
  onReady?: (peaksInstance: PeaksInstance) => void;
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

export function AudioPlayer({
  audioUrl,
  waveformDataUrl,
  regions = [],
  onTimeUpdate,
  onRegionClick,
  onReady,
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
        waveformColor: "rgba(180, 150, 100, 0.6)",
        playedWaveformColor: "rgba(212, 175, 55, 0.9)",
        playheadColor: "#d4af37",
        playheadTextColor: "#ffffff",
        axisLabelColor: "#888888",
        axisGridlineColor: "#333333",
      },
      overview: {
        container: overviewContainerRef.current,
        waveformColor: "rgba(180, 150, 100, 0.4)",
        playedWaveformColor: "rgba(212, 175, 55, 0.7)",
        playheadColor: "#d4af37",
        highlightColor: "rgba(212, 175, 55, 0.1)",
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
                  labelText: region.labelText,
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

        // Set up play/pause handlers
        peaks.on("player.playing", () => setIsPlaying(true));
        peaks.on("player.pause", () => setIsPlaying(false));

        // Segment click handler
        peaks.on("segments.click", (event) => {
          if (event.segment) {
            onRegionClickRef.current?.(event.segment.id ?? "");
          }
        });

        onReadyRef.current?.(peaks);
      }
    });

    return () => {
      if (peaksInstanceRef.current) {
        peaksInstanceRef.current.destroy();
        peaksInstanceRef.current = null;
      }
    };
  }, [audioUrl, waveformDataUrl]);

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
          labelText: region.labelText,
          color: region.color,
        });
      } else {
        console.warn(
          `Skipping invalid region ${region.id}: endTime (${region.endTime}) <= startTime (${region.startTime})`
        );
      }
    });
  }, [regions, isReady]);

  // Play/pause toggle
  const togglePlayPause = useCallback(() => {
    const peaks = peaksInstanceRef.current;
    if (!peaks) return;

    const player = peaks.player;
    if (isPlaying) {
      player.pause();
    } else {
      player.play();
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
      {/* Hidden audio element */}
      <audio
        ref={audioElementRef}
        preload="auto"
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
      >
        <track kind="captions" src="" label="Captions" default />
        <source src={audioUrl} type="audio/mpeg" />
        Your browser does not support the audio element.
      </audio>

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
