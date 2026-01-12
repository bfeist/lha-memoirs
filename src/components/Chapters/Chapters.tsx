import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCommentDots } from "@fortawesome/free-regular-svg-icons";
import { faChevronDown, faChevronRight } from "@fortawesome/free-solid-svg-icons";
import { formatTime } from "../../hooks/useRecordingData";
import { getRecordingByPath } from "../../config/recordings";
import styles from "./Chapters.module.css";

// Extract recording folder name from a path like "memoirs/Norm_red" -> "Norm_red"
function getRecordingFolderName(recordingPath: string): string {
  const parts = recordingPath.split("/");
  return parts[parts.length - 1];
}

// Find alternate telling for a story by matching storyId directly
function findAlternateTellingForStory(
  alternateTellings: AlternateTelling[] | undefined,
  currentRecordingFolder: string,
  storyId: string
): { otherRecordingPath: string; otherStartTime: number; topic: string } | null {
  if (!alternateTellings) return null;

  for (const telling of alternateTellings) {
    const currentRef = telling[currentRecordingFolder] as AlternateStoryRef | undefined;
    if (currentRef && currentRef.storyId === storyId) {
      // Find the other recording in this telling
      for (const key of Object.keys(telling)) {
        if (key !== "topic" && key !== "confidence" && key !== currentRecordingFolder) {
          const otherRef = telling[key] as AlternateStoryRef;
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
  const [expandedChapters, setExpandedChapters] = useState<Set<number>>(new Set());

  // Get current recording folder name for matching
  const currentRecordingFolder = useMemo(
    () => (recordingPath ? getRecordingFolderName(recordingPath) : ""),
    [recordingPath]
  );

  // Group stories by chapter
  const storiesByChapter = useMemo(() => groupStoriesByChapter(stories), [stories]);

  // Determine which chapter is currently active
  const getCurrentChapterIndex = (): number | null => {
    for (let i = chapters.length - 1; i >= 0; i--) {
      if (currentTime >= chapters[i].startTime) {
        return i;
      }
    }
    return chapters.length > 0 ? 0 : null;
  };

  // Determine which story is currently active
  const getCurrentStoryId = (): string | null => {
    if (!stories || stories.length === 0) return null;
    for (let i = stories.length - 1; i >= 0; i--) {
      if (currentTime >= stories[i].startTime) {
        return stories[i].id;
      }
    }
    return stories.length > 0 ? stories[0].id : null;
  };

  const currentChapterIndex = getCurrentChapterIndex();
  const currentStoryId = getCurrentStoryId();

  // Toggle chapter expansion
  const toggleChapter = (index: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setExpandedChapters((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

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

      <nav className={styles.tocList} aria-label="Table of Contents">
        {chapters.map((chapter, index) => {
          const isActive = index === currentChapterIndex;
          const isPast = chapter.startTime < currentTime && !isActive;
          const chapterStories = storiesByChapter.get(index) || [];
          const hasStories = chapterStories.length > 0;
          const isExpanded = expandedChapters.has(index);

          // Count alternate tellings in this chapter's stories
          const storyAlternateTellings = chapterStories
            .map((story) =>
              findAlternateTellingForStory(alternateTellings, currentRecordingFolder, story.id)
            )
            .filter(Boolean);
          const alternateCount = storyAlternateTellings.length;

          return (
            <div key={index} className={styles.chapterGroup}>
              <button
                onClick={() => onChapterClick(chapter)}
                className={`${styles.tocItem} ${isActive ? styles.active : ""} ${isPast ? styles.past : ""}`}
                aria-current={isActive ? "true" : undefined}
              >
                {hasStories && (
                  <span
                    className={styles.expandToggle}
                    onClick={(e) => toggleChapter(index, e)}
                    role="button"
                    tabIndex={0}
                    aria-label={isExpanded ? "Collapse stories" : "Expand stories"}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        toggleChapter(index, e as unknown as React.MouseEvent);
                      }
                    }}
                  >
                    <FontAwesomeIcon icon={isExpanded ? faChevronDown : faChevronRight} />
                  </span>
                )}

                <span className={styles.chapterNumber}>{index + 1}</span>

                <div className={styles.chapterInfo}>
                  <span className={styles.chapterTitle}>{chapter.title}</span>
                  {chapter.description && (
                    <span className={styles.chapterDescription}>{chapter.description}</span>
                  )}
                </div>

                <span className={styles.timestamp}>{formatTime(chapter.startTime)}</span>

                {alternateCount > 0 && (
                  <span
                    className={styles.alternateCount}
                    title={`${alternateCount} alternate telling${alternateCount > 1 ? "s" : ""}`}
                  >
                    <FontAwesomeIcon icon={faCommentDots} />
                    <span className={styles.alternateCountNumber}>{alternateCount}</span>
                  </span>
                )}
              </button>

              {/* Nested stories */}
              {hasStories && isExpanded && (
                <div className={styles.storiesList}>
                  {chapterStories.map((story) => {
                    const isStoryActive = story.id === currentStoryId;
                    const isStoryPast = story.startTime < currentTime && !isStoryActive;
                    const storyAlternate = findAlternateTellingForStory(
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
