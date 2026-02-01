import { memo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faMapMarkerAlt, faPlay, faXmark } from "@fortawesome/free-solid-svg-icons";
import { RECORDINGS } from "../../config/recordings";
import styles from "./PlacesSidePanel.module.css";

interface PlacesSidePanelProps {
  place: Place | null;
  onClose: () => void;
  onCloseModal?: () => void;
}

/**
 * Get a human-readable recording title from a transcript path
 */
function getRecordingTitle(transcriptPath: string): string {
  const recording = RECORDINGS.find((r) => {
    if (r.path === transcriptPath) return true;
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

/**
 * Group mentions by recording for better organization
 */
function groupMentionsByRecording(
  mentions: PlaceMention[]
): Map<string, { title: string; recordingId: string | null; mentions: PlaceMention[] }> {
  const grouped = new Map<
    string,
    { title: string; recordingId: string | null; mentions: PlaceMention[] }
  >();

  // Sort mentions by timestamp within their groups
  const sortedMentions = [...mentions].sort((a, b) => a.timestamp - b.timestamp);

  for (const mention of sortedMentions) {
    const title = getRecordingTitle(mention.transcript);
    const recordingId = getRecordingIdFromPath(mention.transcript);
    const key = mention.transcript;

    if (!grouped.has(key)) {
      grouped.set(key, { title, recordingId, mentions: [] });
    }
    grouped.get(key)!.mentions.push(mention);
  }

  return grouped;
}

export const PlacesSidePanel = memo(function PlacesSidePanel({
  place,
  onClose,
  onCloseModal,
}: PlacesSidePanelProps) {
  const navigate = useNavigate();

  const handleMentionClick = useCallback(
    (recordingId: string | null, timestamp: number) => {
      if (recordingId) {
        // Close the modal first if callback provided
        onCloseModal?.();
        // Navigate to the recording at the specific timestamp
        navigate(`/recording/${recordingId}?t=${Math.floor(timestamp)}`);
      }
    },
    [navigate, onCloseModal]
  );

  if (!place) {
    return (
      <div className={styles.panel}>
        <div className={styles.emptyState}>
          <FontAwesomeIcon icon={faMapMarkerAlt} className={styles.emptyIcon} />
          <h3>Select a Place</h3>
          <p>Click on a location on the map to see all mentions from the memoirs.</p>
        </div>
      </div>
    );
  }

  const groupedMentions = groupMentionsByRecording(place.mentions);
  const totalMentions = place.mentions.length;

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div className={styles.titleArea}>
          <h2 className={styles.placeName}>{place.name}</h2>
          <span className={styles.placeLocation}>
            {place.admin1_name}, {place.country_code}
          </span>
        </div>
        <button
          className={styles.closeButton}
          onClick={onClose}
          aria-label="Deselect place"
          title="Deselect place"
        >
          <FontAwesomeIcon icon={faXmark} />
        </button>
      </div>

      <div className={styles.stats}>
        <div className={styles.statItem}>
          <span className={styles.statValue}>{totalMentions}</span>
          <span className={styles.statLabel}>{totalMentions === 1 ? "mention" : "mentions"}</span>
        </div>
        <div className={styles.statItem}>
          <span className={styles.statValue}>{groupedMentions.size}</span>
          <span className={styles.statLabel}>
            {groupedMentions.size === 1 ? "recording" : "recordings"}
          </span>
        </div>
      </div>

      <div className={styles.mentionsContainer}>
        {Array.from(groupedMentions.entries()).map(([key, group]) => (
          <div key={key} className={styles.recordingGroup}>
            <h4 className={styles.recordingTitle}>{group.title}</h4>
            <ul className={styles.mentionsList}>
              {group.mentions.map((mention, idx) => (
                <li key={idx} className={styles.mentionItem}>
                  <button
                    className={styles.mentionButton}
                    onClick={() => handleMentionClick(group.recordingId, mention.timestamp)}
                    disabled={!group.recordingId}
                    title={group.recordingId ? "Jump to this moment in the recording" : ""}
                  >
                    <span className={styles.timestamp}>
                      <FontAwesomeIcon icon={faPlay} className={styles.playIcon} />
                      {formatTimestamp(mention.timestamp)}
                    </span>
                    <span className={styles.context}>&ldquo;{mention.context}&rdquo;</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
});
