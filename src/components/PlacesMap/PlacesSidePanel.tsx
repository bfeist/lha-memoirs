import { memo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faMapMarkerAlt, faXmark } from "@fortawesome/free-solid-svg-icons";
import { RECORDINGS, type RecordingConfig } from "../../config/recordings";
import { getAudioUrl } from "../../hooks/useRecordingData";
import { AudioExcerptPlayer } from "../AudioExcerptPlayer/AudioExcerptPlayer";
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
  const recording = getRecordingConfigFromPath(transcriptPath);
  return recording?.title || transcriptPath;
}

/**
 * Get the recording ID from a transcript path for navigation
 */
function getRecordingIdFromPath(transcriptPath: string): string | null {
  const recording = getRecordingConfigFromPath(transcriptPath);
  return recording?.id || null;
}

/**
 * Get the recording config from a transcript path
 */
function getRecordingConfigFromPath(transcriptPath: string): RecordingConfig | null {
  const exactMatch = RECORDINGS.find((r) => r.path === transcriptPath);
  if (exactMatch) return exactMatch;

  const transcriptTail = transcriptPath.split("/").pop() || "";
  return RECORDINGS.find((r) => (r.path.split("/").pop() || "") === transcriptTail) || null;
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
  const sortedMentions = [...mentions].sort((a, b) => a.startSecs - b.startSecs);

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

  const handleJumpToRecording = useCallback(
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
              {group.mentions.map((mention, idx) => {
                const config = getRecordingConfigFromPath(mention.transcript);
                const audioUrl = config ? getAudioUrl(config.path, config.hasEnhancedAudio) : null;

                return (
                  <li key={idx} className={styles.mentionItem}>
                    <AudioExcerptPlayer
                      text={mention.context}
                      audioUrl={audioUrl}
                      startTime={mention.startSecs}
                      endTime={mention.endSecs}
                      onNavigate={() => handleJumpToRecording(group.recordingId, mention.startSecs)}
                      navigateLabel="In Transcript"
                    />
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
});
