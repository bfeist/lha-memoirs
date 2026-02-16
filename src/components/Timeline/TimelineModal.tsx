import { useState, useEffect, useCallback } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faXmark, faClock } from "@fortawesome/free-solid-svg-icons";
import { Timeline } from "./Timeline";
import { TimelineDetail } from "./TimelineDetail";
import { useTimeline } from "../../hooks/useTimeline";
import styles from "./TimelineModal.module.css";

interface TimelineModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** Optional initial year to select - will find and select the entry containing this year */
  initialYear?: number | null;
}

/**
 * Find the timeline entry index that contains a given year
 */
function findEntryIndexForYear(
  year: number,
  entries: { year_start: number; year_end: number }[]
): number | null {
  for (let i = 0; i < entries.length; i++) {
    const entry = entries[i];
    if (year >= entry.year_start && year <= entry.year_end) {
      return i;
    }
  }
  return null;
}

export function TimelineModal({
  isOpen,
  onClose,
  initialYear,
}: TimelineModalProps): React.ReactElement | null {
  const { data, isLoading, error } = useTimeline();

  // Compute initial entry index from initialYear (if provided)
  // Since parent uses key={`timeline-${selectedYear}`}, component remounts on year change
  const computeInitialEntry = (): number | null => {
    if (initialYear && data?.entries) {
      return findEntryIndexForYear(initialYear, data.entries);
    }
    return null;
  };

  const [selectedEntryIndex, setSelectedEntryIndex] = useState<number | null>(computeInitialEntry);

  // Handle escape key - closes modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  const handleEntrySelect = useCallback((index: number | null) => {
    setSelectedEntryIndex(index);
  }, []);

  // Handle close with selection reset
  const handleClose = useCallback(() => {
    setSelectedEntryIndex(null);
    onClose();
  }, [onClose]);

  if (!isOpen) return null;

  const selectedEntry =
    data && selectedEntryIndex !== null ? data.entries[selectedEntryIndex] : null;

  return (
    <div className={styles.overlay}>
      {/* Backdrop for closing */}
      <button
        type="button"
        className={styles.backdrop}
        onClick={handleClose}
        aria-label="Close timeline"
      />

      <div
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="timeline-title"
      >
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.titleContainer}>
            <FontAwesomeIcon icon={faClock} className={styles.titleIcon} />
            <h2 id="timeline-title" className={styles.title}>
              Timeline
            </h2>
            {data && (
              <span className={styles.timeRange}>
                {data.timelineStart}–{data.timelineEnd}
              </span>
            )}
          </div>
          <button className={styles.closeButton} onClick={handleClose} aria-label="Close">
            <FontAwesomeIcon icon={faXmark} />
          </button>
        </div>

        {/* Main content area */}
        <div className={styles.content}>
          {isLoading && (
            <div className={styles.loadingState}>
              <span>Loading timeline...</span>
            </div>
          )}

          {error && (
            <div className={styles.errorState}>
              <span>Failed to load timeline: {error.message}</span>
            </div>
          )}

          {!isLoading && !error && data && (
            <>
              {/* Timeline bar at top */}
              <div className={styles.timelineSection}>
                <Timeline
                  data={data}
                  selectedEntryIndex={selectedEntryIndex}
                  onEntrySelect={handleEntrySelect}
                />
              </div>

              {/* Detail panel below */}
              <TimelineDetail entry={selectedEntry} onCloseModal={handleClose} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
