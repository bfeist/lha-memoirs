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
}

export function TimelineModal({ isOpen, onClose }: TimelineModalProps): React.ReactElement | null {
  const { data, isLoading, error } = useTimeline();
  const [selectedEntryIndex, setSelectedEntryIndex] = useState<number | null>(null);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === "Escape" && isOpen) {
        if (selectedEntryIndex !== null) {
          // First escape deselects
          setSelectedEntryIndex(null);
        } else {
          // Second escape closes modal
          onClose();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, selectedEntryIndex]);

  const handleEntrySelect = useCallback((index: number | null) => {
    setSelectedEntryIndex(index);
  }, []);

  const handleDeselectEntry = useCallback(() => {
    setSelectedEntryIndex(null);
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
              Life Timeline
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
              <TimelineDetail
                entry={selectedEntry}
                onClose={handleDeselectEntry}
                onCloseModal={handleClose}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
