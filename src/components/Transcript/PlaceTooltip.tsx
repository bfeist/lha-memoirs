import { useState, useRef, useCallback, memo, useLayoutEffect } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { RECORDINGS } from "../../config/recordings";
import styles from "./PlaceTooltip.module.css";

interface PlaceTooltipProps {
  place: Place;
  currentTranscript?: string;
  children: React.ReactNode;
}

/**
 * Get a human-readable recording title from a transcript path
 */
function getRecordingTitle(transcriptPath: string): string {
  // Try to match the path to a recording config
  // transcriptPath might be "memoirs/Norm_red" or just "glynn_interview"
  const recording = RECORDINGS.find((r) => {
    // Check if the path matches directly
    if (r.path === transcriptPath) return true;
    // Check if it's a partial match (e.g., transcriptPath ends with the recording path)
    if (transcriptPath.endsWith(r.path.split("/").pop() || "")) return true;
    return false;
  });

  return recording?.title || transcriptPath;
}

/**
 * Get the recording ID from a transcript path for navigation
 */
function getRecordingIdFromPath(transcriptPath: string): string | null {
  const recording = RECORDINGS.find((r) => {
    if (r.path === transcriptPath) return true;
    if (transcriptPath.endsWith(r.path.split("/").pop() || "")) return true;
    return false;
  });
  return recording?.id || null;
}

/**
 * Format seconds to MM:SS or HH:MM:SS
 */
function formatTimestamp(seconds: number): string {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);

  if (hrs > 0) {
    return `${hrs}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export const PlaceTooltip = memo(function PlaceTooltip({
  place,
  currentTranscript,
  children,
}: PlaceTooltipProps) {
  const navigate = useNavigate();
  const [isVisible, setIsVisible] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLSpanElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const hideTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Calculate position when tooltip becomes visible
  useLayoutEffect(() => {
    if (isVisible && triggerRef.current && tooltipRef.current) {
      const triggerRect = triggerRef.current.getBoundingClientRect();
      const tooltipRect = tooltipRef.current.getBoundingClientRect();
      const viewportHeight = window.innerHeight;
      const viewportWidth = window.innerWidth;

      // Check if there's enough space below
      const spaceBelow = viewportHeight - triggerRect.bottom;
      const spaceAbove = triggerRect.top;

      let top: number;
      if (spaceBelow < tooltipRect.height + 20 && spaceAbove > spaceBelow) {
        // Position above
        top = triggerRect.top - tooltipRect.height - 8;
      } else {
        // Position below
        top = triggerRect.bottom + 8;
      }

      // Center horizontally on the trigger, but keep within viewport
      let left = triggerRect.left + triggerRect.width / 2 - tooltipRect.width / 2;
      left = Math.max(10, Math.min(left, viewportWidth - tooltipRect.width - 10));

      setTooltipPosition({ top, left });
    }
  }, [isVisible]);

  const showTooltip = useCallback(() => {
    if (hideTimeoutRef.current) {
      clearTimeout(hideTimeoutRef.current);
    }
    setIsVisible(true);
  }, []);

  const hideTooltip = useCallback(() => {
    hideTimeoutRef.current = setTimeout(() => {
      setIsVisible(false);
    }, 150);
  }, []);

  const handleMentionClick = useCallback(
    (mention: PlaceMention, e: React.MouseEvent) => {
      e.stopPropagation();
      const recordingId = getRecordingIdFromPath(mention.transcript);
      if (recordingId) {
        navigate(`/recording/${recordingId}?t=${Math.floor(mention.timestamp)}`);
      }
    },
    [navigate]
  );

  // Cleanup timeout on unmount
  useLayoutEffect(() => {
    return () => {
      if (hideTimeoutRef.current) {
        clearTimeout(hideTimeoutRef.current);
      }
    };
  }, []);

  // Separate current transcript mentions from other mentions
  const currentMentions = place.mentions.filter((m) =>
    currentTranscript ? m.transcript.includes(currentTranscript) : false
  );
  const otherMentions = place.mentions.filter(
    (m) => !currentTranscript || !m.transcript.includes(currentTranscript)
  );

  // Create OpenStreetMap embed URL
  const mapUrl = `https://www.openstreetmap.org/export/embed.html?bbox=${place.longitude - 0.1}%2C${place.latitude - 0.1}%2C${place.longitude + 0.1}%2C${place.latitude + 0.1}&layer=mapnik&marker=${place.latitude}%2C${place.longitude}`;

  return (
    <span
      ref={triggerRef}
      className={styles.placeName}
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
      tabIndex={0}
      role="button"
      aria-describedby={isVisible ? `place-tooltip-${place.geonameid}` : undefined}
    >
      {children}
      {isVisible &&
        createPortal(
          <div
            ref={tooltipRef}
            id={`place-tooltip-${place.geonameid}`}
            className={styles.tooltip}
            style={{ top: tooltipPosition.top, left: tooltipPosition.left }}
            onMouseEnter={showTooltip}
            onMouseLeave={hideTooltip}
            role="tooltip"
          >
            <div className={styles.tooltipHeader}>
              <h4 className={styles.placeTitleText}>{place.name}</h4>
              <span className={styles.placeLocation}>
                {place.admin1_name}, {place.country_code}
              </span>
            </div>

            <div className={styles.mapContainer}>
              <iframe
                src={mapUrl}
                className={styles.map}
                title={`Map of ${place.name}`}
                loading="lazy"
              />
            </div>

            {(currentMentions.length > 0 || otherMentions.length > 0) && (
              <div className={styles.mentions}>
                {currentMentions.length > 0 && (
                  <div className={styles.mentionGroup}>
                    <h5 className={styles.mentionGroupTitle}>In This Recording</h5>
                    {currentMentions.map((mention, idx) => (
                      <button
                        key={idx}
                        className={styles.mentionItem}
                        onClick={(e) => handleMentionClick(mention, e)}
                        type="button"
                      >
                        <span className={styles.mentionTime}>
                          {formatTimestamp(mention.timestamp)}
                        </span>
                        <span className={styles.mentionContext}>
                          &ldquo;{mention.context}&rdquo;
                        </span>
                      </button>
                    ))}
                  </div>
                )}

                {otherMentions.length > 0 && (
                  <div className={styles.mentionGroup}>
                    <h5 className={styles.mentionGroupTitle}>Other Occurrences</h5>
                    {otherMentions.map((mention, idx) => (
                      <button
                        key={idx}
                        className={styles.mentionItem}
                        onClick={(e) => handleMentionClick(mention, e)}
                        type="button"
                      >
                        <span className={styles.mentionRecording}>
                          {getRecordingTitle(mention.transcript)}
                        </span>
                        <span className={styles.mentionTime}>
                          {formatTimestamp(mention.timestamp)}
                        </span>
                        <span className={styles.mentionContext}>
                          &ldquo;{mention.context}&rdquo;
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>,
          document.body
        )}
    </span>
  );
});
