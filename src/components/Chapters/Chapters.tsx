import { useMemo, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCommentDots } from "@fortawesome/free-regular-svg-icons";
import { formatTime } from "../../hooks/useRecordingData";
import { getRecordingByPath } from "../../config/recordings";
import styles from "./Chapters.module.css";

// Extract recording folder name from a path like "memoirs/Norm_red" -> "Norm_red"
function getRecordingFolderName(recordingPath: string): string {
  const parts = recordingPath.split("/");
  return parts[parts.length - 1];
}

// Find alternate telling for a segment (chapter) by matching id
function findAlternateTellingForSegment(
  alternateTellings: AlternateTelling[] | undefined,
  currentRecordingFolder: string,
  segmentId: string
): { otherRecordingPath: string; otherStartTime: number; topic: string } | null {
  if (!alternateTellings) return null;

  for (const telling of alternateTellings) {
    const currentRef = telling[currentRecordingFolder] as
      | AlternateSegmentRef
      | AlternateStoryRef
      | undefined;
    if (!currentRef) continue;

    // Handle new format (id field) or legacy format (storyId field)
    const currentId =
      "id" in currentRef ? currentRef.id : "storyId" in currentRef ? currentRef.storyId : null;

    if (currentId === segmentId) {
      // Find the other recording in this telling
      for (const key of Object.keys(telling)) {
        if (key !== "topic" && key !== "confidence" && key !== currentRecordingFolder) {
          const otherRef = telling[key] as AlternateSegmentRef | AlternateStoryRef;
          const otherPath = `memoirs/${key}`;
          return {
            otherRecordingPath: otherPath,
            otherStartTime: otherRef.startTime,
            topic: telling.topic,
          };
        }
      }
    }
  }
  return null;
}

/** Represents a major chapter with its associated minor chapters */
interface ChapterGroup {
  majorChapter: Chapter;
  majorIndex: number;
  minorChapters: { chapter: Chapter; globalIndex: number }[];
}

/**
 * Group chapters into major chapters with their minor sub-chapters.
 * Minor chapters are assigned to the most recent major chapter before them.
 */
function groupChaptersByMajor(chapters: Chapter[]): ChapterGroup[] {
  const groups: ChapterGroup[] = [];

  chapters.forEach((chapter, globalIndex) => {
    if (!chapter.minor) {
      // Major chapter - start a new group
      groups.push({
        majorChapter: chapter,
        majorIndex: groups.length,
        minorChapters: [],
      });
    } else {
      // Minor chapter - add to the most recent major chapter group
      if (groups.length > 0) {
        groups[groups.length - 1].minorChapters.push({ chapter, globalIndex });
      }
    }
  });

  return groups;
}

export function Chapters({
  chapters,
  currentTime,
  onChapterClick,
  alternateTellings,
  recordingPath,
}: {
  chapters: Chapter[];
  currentTime: number;
  onChapterClick: (chapter: Chapter) => void;
  alternateTellings?: AlternateTelling[];
  recordingPath?: string;
}): React.ReactElement {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLElement>(null);
  const activeChapterRef = useRef<HTMLDivElement>(null);
  const lastScrolledChapterIndex = useRef<number | null>(null);

  // Get current recording folder name for matching
  const currentRecordingFolder = useMemo(
    () => (recordingPath ? getRecordingFolderName(recordingPath) : ""),
    [recordingPath]
  );

  // Group chapters into major chapters with their minor sub-chapters
  const chapterGroups = useMemo(() => groupChaptersByMajor(chapters), [chapters]);

  // Determine which chapter (major or minor) is currently active by global index
  const currentChapterIndex = useMemo((): number | null => {
    for (let i = chapters.length - 1; i >= 0; i--) {
      if (currentTime >= chapters[i].startTime) {
        return i;
      }
    }
    return chapters.length > 0 ? 0 : null;
  }, [chapters, currentTime]);

  // Determine which major chapter group contains the current chapter
  const currentMajorGroupIndex = useMemo((): number | null => {
    if (currentChapterIndex === null) return null;
    // Find which group contains this chapter index
    for (let i = chapterGroups.length - 1; i >= 0; i--) {
      const group = chapterGroups[i];
      // Check if current chapter is this major chapter or one of its minors
      const majorChapterGlobalIndex = chapters.findIndex((c) => c === group.majorChapter);
      if (currentChapterIndex >= majorChapterGlobalIndex) {
        // Check if it's within this group's range
        const nextGroup = chapterGroups[i + 1];
        if (!nextGroup) return i;
        const nextMajorGlobalIndex = chapters.findIndex((c) => c === nextGroup.majorChapter);
        if (currentChapterIndex < nextMajorGlobalIndex) return i;
      }
    }
    return chapterGroups.length > 0 ? 0 : null;
  }, [chapters, chapterGroups, currentChapterIndex]);

  // Auto-scroll to keep current chapter in view
  useEffect(() => {
    if (
      activeChapterRef.current &&
      containerRef.current &&
      currentChapterIndex !== null &&
      currentChapterIndex !== lastScrolledChapterIndex.current
    ) {
      lastScrolledChapterIndex.current = currentChapterIndex;
      const container = containerRef.current;
      const activeChapter = activeChapterRef.current;

      const containerRect = container.getBoundingClientRect();
      const chapterRect = activeChapter.getBoundingClientRect();

      // Check if chapter is outside visible area (with some padding)
      const isAbove = chapterRect.top < containerRect.top + 40;
      const isBelow = chapterRect.bottom > containerRect.bottom - 40;

      if (isAbove || isBelow) {
        activeChapter.scrollIntoView({
          behavior: "smooth",
          block: "nearest",
        });
      }
    }
  }, [currentChapterIndex]);

  // Handle alternate telling click - navigate to other recording
  const handleAlternateClick = (
    e: React.MouseEvent,
    otherRecordingPath: string,
    otherStartTime: number
  ) => {
    e.stopPropagation();
    const otherRecording = getRecordingByPath(otherRecordingPath);
    if (otherRecording) {
      navigate(`/recording/${otherRecording.id}?t=${Math.floor(otherStartTime)}`);
    }
  };

  // Handle minor chapter click
  const handleMinorChapterClick = (chapter: Chapter, e: React.MouseEvent) => {
    e.stopPropagation();
    onChapterClick(chapter);
  };

  return (
    <div className={styles.container}>
      <h2 className={styles.heading}>Chapters</h2>

      <p className={styles.hint}>Click a chapter to jump to that section</p>

      <nav ref={containerRef} className={styles.tocList} aria-label="Table of Contents">
        {chapterGroups.map((group, groupIndex) => {
          const { majorChapter, minorChapters } = group;
          const majorChapterGlobalIndex = chapters.findIndex((c) => c === majorChapter);
          const hasMinorChapters = minorChapters.length > 0;

          // Check if a minor chapter in this group is active
          const activeMinorInGroup = minorChapters.find(
            ({ globalIndex }) => globalIndex === currentChapterIndex
          );
          const isMinorActiveInThisGroup = !!activeMinorInGroup;

          // Major chapter is active only if it's the current chapter and no minor is active
          const isMajorActive =
            currentChapterIndex === majorChapterGlobalIndex && !isMinorActiveInThisGroup;
          const isMajorPast =
            majorChapter.startTime < currentTime && !isMajorActive && !isMinorActiveInThisGroup;

          // Check if this major chapter has an alternate telling
          const chapterId = `chapter-${majorChapterGlobalIndex}`;
          const chapterAlternate = findAlternateTellingForSegment(
            alternateTellings,
            currentRecordingFolder,
            chapterId
          );

          return (
            <div
              key={groupIndex}
              ref={groupIndex === currentMajorGroupIndex ? activeChapterRef : null}
              className={styles.chapterGroup}
            >
              <button
                onClick={() => onChapterClick(majorChapter)}
                className={`${styles.tocItem} ${isMajorActive ? styles.active : ""} ${isMajorPast ? styles.past : ""}`}
                aria-current={isMajorActive ? "true" : undefined}
              >
                <span className={styles.chapterNumber}>{groupIndex + 1}</span>

                <div className={styles.chapterInfo}>
                  <span className={styles.chapterTitle}>{majorChapter.title}</span>
                  {majorChapter.description && (
                    <span className={styles.chapterDescription}>{majorChapter.description}</span>
                  )}
                </div>

                <span className={styles.timestamp}>{formatTime(majorChapter.startTime)}</span>

                {chapterAlternate && (
                  <span
                    className={styles.alternateTelling}
                    onClick={(e) =>
                      handleAlternateClick(
                        e,
                        chapterAlternate.otherRecordingPath,
                        chapterAlternate.otherStartTime
                      )
                    }
                    title={`Alternate telling: ${chapterAlternate.topic}`}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        handleAlternateClick(
                          e as unknown as React.MouseEvent,
                          chapterAlternate.otherRecordingPath,
                          chapterAlternate.otherStartTime
                        );
                      }
                    }}
                  >
                    <FontAwesomeIcon icon={faCommentDots} />
                  </span>
                )}
              </button>

              {/* Nested minor chapters */}
              {hasMinorChapters && (
                <div className={styles.minorChaptersList}>
                  {minorChapters.map(({ chapter: minorChapter, globalIndex }) => {
                    const isMinorActive = globalIndex === currentChapterIndex;
                    const isMinorPast = minorChapter.startTime < currentTime && !isMinorActive;

                    // Check if this minor chapter has an alternate telling
                    const minorChapterId = `chapter-${globalIndex}`;
                    const minorAlternate = findAlternateTellingForSegment(
                      alternateTellings,
                      currentRecordingFolder,
                      minorChapterId
                    );

                    return (
                      <button
                        key={globalIndex}
                        onClick={(e) => handleMinorChapterClick(minorChapter, e)}
                        className={`${styles.minorChapterItem} ${isMinorActive ? styles.active : ""} ${isMinorPast ? styles.past : ""}`}
                        aria-current={isMinorActive ? "true" : undefined}
                      >
                        <span className={styles.minorChapterBullet}>•</span>

                        <div className={styles.minorChapterInfo}>
                          <span className={styles.minorChapterTitle}>{minorChapter.title}</span>
                        </div>

                        <span className={styles.timestamp}>
                          {formatTime(minorChapter.startTime)}
                        </span>

                        {minorAlternate && (
                          <span
                            className={styles.alternateTelling}
                            onClick={(e) =>
                              handleAlternateClick(
                                e,
                                minorAlternate.otherRecordingPath,
                                minorAlternate.otherStartTime
                              )
                            }
                            title={`Alternate telling: ${minorAlternate.topic}`}
                            role="button"
                            tabIndex={0}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                handleAlternateClick(
                                  e as unknown as React.MouseEvent,
                                  minorAlternate.otherRecordingPath,
                                  minorAlternate.otherStartTime
                                );
                              }
                            }}
                          >
                            <FontAwesomeIcon icon={faCommentDots} />
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </nav>
    </div>
  );
}
