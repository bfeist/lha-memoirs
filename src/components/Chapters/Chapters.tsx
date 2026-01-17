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

// Find alternate telling for a segment (chapter or story) by matching id
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

// Group stories by chapter index
function groupStoriesByChapter(stories: Story[] | undefined): Map<number, Story[]> {
  const grouped = new Map<number, Story[]>();
  if (!stories) return grouped;

  for (const story of stories) {
    const chapterIdx = story.chapterIndex;
    if (!grouped.has(chapterIdx)) {
      grouped.set(chapterIdx, []);
    }
    grouped.get(chapterIdx)!.push(story);
  }

  return grouped;
}

export function Chapters({
  chapters,
  stories,
  currentTime,
  onChapterClick,
  onStoryClick,
  alternateTellings,
  recordingPath,
}: {
  chapters: Chapter[];
  stories?: Story[];
  currentTime: number;
  onChapterClick: (chapter: Chapter) => void;
  onStoryClick?: (story: Story) => void;
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

  // Group stories by chapter
  const storiesByChapter = useMemo(() => groupStoriesByChapter(stories), [stories]);

  // Determine which chapter is currently active
  const currentChapterIndex = useMemo((): number | null => {
    for (let i = chapters.length - 1; i >= 0; i--) {
      if (currentTime >= chapters[i].startTime) {
        return i;
      }
    }
    return chapters.length > 0 ? 0 : null;
  }, [chapters, currentTime]);

  // Determine which story is currently active
  const currentStoryId = useMemo((): string | null => {
    if (!stories || stories.length === 0) return null;
    for (let i = stories.length - 1; i >= 0; i--) {
      if (currentTime >= stories[i].startTime) {
        return stories[i].id;
      }
    }
    return stories.length > 0 ? stories[0].id : null;
  }, [stories, currentTime]);

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

  // Handle story click
  const handleStoryClick = (story: Story, e: React.MouseEvent) => {
    e.stopPropagation();
    if (onStoryClick) {
      onStoryClick(story);
    } else {
      // Fallback: create a chapter-like object to use onChapterClick
      onChapterClick({
        title: story.title,
        startTime: story.startTime,
        description: story.description,
      });
    }
  };

  return (
    <div className={styles.container}>
      <h2 className={styles.heading}>Chapters</h2>

      <p className={styles.hint}>Click a chapter to jump to that section</p>

      <nav ref={containerRef} className={styles.tocList} aria-label="Table of Contents">
        {chapters.map((chapter, index) => {
          const chapterStories = storiesByChapter.get(index) || [];
          const hasStories = chapterStories.length > 0;
          // If this chapter has stories and one of them is active, don't highlight the chapter
          const isCurrentStoryInThisChapter =
            hasStories && currentStoryId && chapterStories.some((s) => s.id === currentStoryId);
          const isActive = index === currentChapterIndex && !isCurrentStoryInThisChapter;
          const isPast =
            chapter.startTime < currentTime && !isActive && !isCurrentStoryInThisChapter;

          // Check if this chapter itself has an alternate telling
          const chapterId = `chapter-${index}`;
          const chapterAlternate = findAlternateTellingForSegment(
            alternateTellings,
            currentRecordingFolder,
            chapterId
          );

          return (
            <div
              key={index}
              ref={isActive ? activeChapterRef : null}
              className={styles.chapterGroup}
            >
              <button
                onClick={() => onChapterClick(chapter)}
                className={`${styles.tocItem} ${isActive ? styles.active : ""} ${isPast ? styles.past : ""}`}
                aria-current={isActive ? "true" : undefined}
              >
                <span className={styles.chapterNumber}>{index + 1}</span>

                <div className={styles.chapterInfo}>
                  <span className={styles.chapterTitle}>{chapter.title}</span>
                  {chapter.description && (
                    <span className={styles.chapterDescription}>{chapter.description}</span>
                  )}
                </div>

                <span className={styles.timestamp}>{formatTime(chapter.startTime)}</span>

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

              {/* Nested stories */}
              {hasStories && (
                <div className={styles.storiesList}>
                  {chapterStories.map((story) => {
                    // A story is only active if it matches currentStoryId AND we're still in this chapter
                    const isStoryActive =
                      story.id === currentStoryId && index === currentChapterIndex;
                    const isStoryPast = story.startTime < currentTime && !isStoryActive;
                    const storyAlternate = findAlternateTellingForSegment(
                      alternateTellings,
                      currentRecordingFolder,
                      story.id
                    );

                    return (
                      <button
                        key={story.id}
                        onClick={(e) => handleStoryClick(story, e)}
                        className={`${styles.storyItem} ${isStoryActive ? styles.active : ""} ${isStoryPast ? styles.past : ""}`}
                        aria-current={isStoryActive ? "true" : undefined}
                      >
                        <span className={styles.storyBullet}>•</span>

                        <div className={styles.storyInfo}>
                          <span className={styles.storyTitle}>{story.title}</span>
                        </div>

                        <span className={styles.timestamp}>{formatTime(story.startTime)}</span>

                        {storyAlternate && (
                          <span
                            className={styles.alternateTelling}
                            onClick={(e) =>
                              handleAlternateClick(
                                e,
                                storyAlternate.otherRecordingPath,
                                storyAlternate.otherStartTime
                              )
                            }
                            title={`Alternate telling: ${storyAlternate.topic}`}
                            role="button"
                            tabIndex={0}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                handleAlternateClick(
                                  e as unknown as React.MouseEvent,
                                  storyAlternate.otherRecordingPath,
                                  storyAlternate.otherStartTime
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
