import { memo, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faClock, faXmark } from "@fortawesome/free-solid-svg-icons";
import type { TimelineEntry, TimelineExcerpt } from "../../types/timeline";
import { RECORDINGS } from "../../config/recordings";
import { getAudioUrl } from "../../hooks/useRecordingData";
import { AudioExcerptPlayer } from "../AudioExcerptPlayer/AudioExcerptPlayer";
import styles from "./TimelineDetail.module.css";

interface TimelineDetailProps {
  entry: TimelineEntry | null;
  onClose: () => void;
  onCloseModal?: () => void;
}

/**
 * Get recording config from recording ID
 */
function getRecordingConfig(recordingId: string) {
  return RECORDINGS.find((r) => r.id === recordingId) ?? null;
}

/**
 * Group excerpts by recording for better organization
 */
function groupExcerptsByRecording(
  excerpts: TimelineExcerpt[]
): Map<string, { title: string; recordingId: string; excerpts: TimelineExcerpt[] }> {
  const grouped = new Map<
    string,
    { title: string; recordingId: string; excerpts: TimelineExcerpt[] }
  >();

  // Sort excerpts by startTime within their groups
  const sortedExcerpts = [...excerpts].sort((a, b) => a.startTime - b.startTime);

  for (const excerpt of sortedExcerpts) {
    const key = excerpt.recordingId;
    if (!grouped.has(key)) {
      grouped.set(key, {
        title: excerpt.recordingTitle,
        recordingId: excerpt.recordingId,
        excerpts: [],
      });
    }
    grouped.get(key)!.excerpts.push(excerpt);
  }

  return grouped;
}

export const TimelineDetail = memo(function TimelineDetail({
  entry,
  onClose,
  onCloseModal,
}: TimelineDetailProps) {
  const navigate = useNavigate();
  const [playingExcerptKey, setPlayingExcerptKey] = useState<string | null>(null);

  const handleJumpToRecording = useCallback(
    (recordingId: string, timestamp: number) => {
      // Close the modal first
      onCloseModal?.();
      // Navigate to the recording at the specific timestamp
      navigate(`/recording/${recordingId}?t=${Math.floor(timestamp)}`);
    },
    [navigate, onCloseModal]
  );

  const handleExcerptPlay = useCallback((excerptKey: string) => {
    setPlayingExcerptKey(excerptKey);
  }, []);

  if (!entry) {
    return (
      <div className={styles.panel}>
        <div className={styles.emptyState}>
          <FontAwesomeIcon icon={faClock} className={styles.emptyIcon} />
          <h3>Select a Year</h3>
          <p>Hover or tap the timeline above to explore Lindy&apos;s life story.</p>
        </div>
      </div>
    );
  }

  const yearLabel =
    entry.year_start === entry.year_end
      ? String(entry.year_start)
      : `${entry.year_start}–${entry.year_end}`;

  const ageLabel =
    entry.age_start === entry.age_end
      ? `${entry.age_start} years old`
      : `${entry.age_start}–${entry.age_end} years old`;

  const groupedExcerpts = groupExcerptsByRecording(entry.excerpts);

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div className={styles.titleArea}>
          <span className={styles.yearBadge}>{yearLabel}</span>
          <h2 className={styles.title}>{entry.title}</h2>
          <span className={styles.age}>{ageLabel}</span>
        </div>
        <button
          className={styles.closeButton}
          onClick={onClose}
          aria-label="Close detail"
          title="Close"
        >
          <FontAwesomeIcon icon={faXmark} />
        </button>
      </div>

      <p className={styles.description}>{entry.description}</p>

      <div className={styles.excerptsContainer}>
        <h3 className={styles.excerptsTitle}>
          From the Recordings ({entry.excerpts.length} excerpt
          {entry.excerpts.length !== 1 ? "s" : ""})
        </h3>

        {Array.from(groupedExcerpts.entries()).map(([recordingId, group]) => {
          const config = getRecordingConfig(recordingId);
          const audioUrl = config ? getAudioUrl(config.path, config.hasEnhancedAudio) : null;

          return (
            <div key={recordingId} className={styles.recordingGroup}>
              <h4 className={styles.recordingTitle}>{group.title}</h4>
              <ul className={styles.excerptsList}>
                {group.excerpts.map((excerpt, idx) => {
                  const excerptKey = `${recordingId}-${excerpt.startTime}`;
                  const shouldStop = playingExcerptKey !== null && playingExcerptKey !== excerptKey;

                  return (
                    <li key={idx} className={styles.excerptItem}>
                      <AudioExcerptPlayer
                        text={excerpt.text}
                        audioUrl={audioUrl}
                        startTime={excerpt.startTime}
                        endTime={excerpt.endTime}
                        onNavigate={() => handleJumpToRecording(recordingId, excerpt.startTime)}
                        navigateLabel="In Transcript"
                        onPlay={() => handleExcerptPlay(excerptKey)}
                        shouldStop={shouldStop}
                      />
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </div>
    </div>
  );
});
