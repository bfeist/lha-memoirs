import { useRef, useEffect, useMemo, useCallback } from "react";
import { formatTime } from "../../hooks/useRecordingData";
import styles from "./Transcript.module.css";

export function Transcript({
  segments,
  chapters,
  stories,
  currentTime,
  onSegmentClick,
}: {
  segments: TranscriptSegment[];
  chapters: Chapter[];
  stories?: Story[];
  currentTime: number;
  onSegmentClick?: (time: number) => void;
}): React.ReactElement {
  const containerRef = useRef<HTMLDivElement>(null);
  const activeChapterRef = useRef<HTMLDivElement>(null);
  const activeSegmentRef = useRef<HTMLSpanElement>(null);
  const lastScrolledChapterId = useRef<string | null>(null);
  const lastScrolledSegmentIndex = useRef<number | null>(null);

  // Pre-compute which segment index is the first for each story
  // Maps segment index -> Story (only for the first segment of each story)
  const storyStartSegments = useMemo(() => {
    const map = new Map<number, Story>();
    if (!stories || stories.length === 0) return map;

    for (const story of stories) {
      // Find the first segment that starts at or after the story's start time
      let firstSegmentIndex = -1;
      for (let i = 0; i < segments.length; i++) {
        if (segments[i].start >= story.startTime) {
          firstSegmentIndex = i;
          break;
        }
      }
      if (firstSegmentIndex !== -1) {
        // Only set if not already claimed by another story
        // (earlier stories take precedence if they share a segment)
        if (!map.has(firstSegmentIndex)) {
          map.set(firstSegmentIndex, story);
        }
      }
    }
    return map;
  }, [stories, segments]);

  // Group segments by chapter
  const chapterGroups = useMemo(() => {
    if (!chapters || chapters.length === 0) {
      // If no chapters, treat all segments as one group
      return [
        {
          chapter: {
            title: "Full Recording",
            startTime: 0,
            description: "",
          },
          segments: segments,
          chapterIndex: 0,
        },
      ];
    }

    const groups: { chapter: Chapter; segments: TranscriptSegment[]; chapterIndex: number }[] = [];
    const sortedChapters = [...chapters].sort((a, b) => a.startTime - b.startTime);

    for (let i = 0; i < sortedChapters.length; i++) {
      const chapter = sortedChapters[i];
      const nextChapter = sortedChapters[i + 1];
      const chapterEnd = nextChapter ? nextChapter.startTime : Infinity;

      const chapterSegments = segments.filter(
        (seg) => seg.start >= chapter.startTime && seg.start < chapterEnd
      );

      groups.push({
        chapter,
        segments: chapterSegments,
        chapterIndex: i,
      });
    }

    return groups;
  }, [segments, chapters]);

  // Find current chapter and segment based on playback time
  const { currentChapterId, currentSegmentIndex } = useMemo(() => {
    let chapterIndex = 0;
    let segmentIndex = 0;

    // Find current chapter
    if (chapters && chapters.length > 0) {
      for (let i = chapters.length - 1; i >= 0; i--) {
        if (currentTime >= chapters[i].startTime) {
          chapterIndex = i;
          break;
        }
      }
    }

    // Find current segment
    for (let i = segments.length - 1; i >= 0; i--) {
      if (currentTime >= segments[i].start) {
        segmentIndex = i;
        break;
      }
    }

    return { currentChapterId: `chapter-${chapterIndex}`, currentSegmentIndex: segmentIndex };
  }, [chapters, segments, currentTime]);

  // Auto-scroll only when chapter changes
  useEffect(() => {
    if (
      activeChapterRef.current &&
      containerRef.current &&
      currentChapterId !== lastScrolledChapterId.current
    ) {
      lastScrolledChapterId.current = currentChapterId;
      const container = containerRef.current;
      const activeChapter = activeChapterRef.current;

      const containerRect = container.getBoundingClientRect();
      const chapterRect = activeChapter.getBoundingClientRect();

      // Check if chapter is outside visible area
      const isAbove = chapterRect.top < containerRect.top + 50;
      const isBelow = chapterRect.bottom > containerRect.bottom - 100;

      if (isAbove || isBelow) {
        activeChapter.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      }
    }
  }, [currentChapterId]);

  // Auto-scroll to keep current segment in view
  useEffect(() => {
    if (
      activeSegmentRef.current &&
      containerRef.current &&
      currentSegmentIndex !== lastScrolledSegmentIndex.current
    ) {
      lastScrolledSegmentIndex.current = currentSegmentIndex;
      const container = containerRef.current;
      const activeSegment = activeSegmentRef.current;

      const containerRect = container.getBoundingClientRect();
      const segmentRect = activeSegment.getBoundingClientRect();

      // Check if segment is outside visible area (with some padding)
      const isAbove = segmentRect.top < containerRect.top + 60;
      const isBelow = segmentRect.bottom > containerRect.bottom - 60;

      if (isAbove || isBelow) {
        activeSegment.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      }
    }
  }, [currentSegmentIndex]);

  // Memoized click handler
  const handleClick = useCallback(
    (time: number) => {
      onSegmentClick?.(time);
    },
    [onSegmentClick]
  );

  return (
    <div className={styles.container}>
      <p className={styles.hint}>Click any text to jump to that moment</p>

      <div ref={containerRef} className={styles.transcriptContent}>
        {chapterGroups.map((group, groupIndex) => {
          const chapterIdString = `chapter-${groupIndex}`;
          const isCurrentChapter = chapterIdString === currentChapterId;
          const isPastChapter = group.chapter.startTime < currentTime && !isCurrentChapter;

          return (
            <div
              key={groupIndex}
              ref={isCurrentChapter ? activeChapterRef : null}
              className={`${styles.chapterSection} ${isCurrentChapter ? styles.activeChapter : ""} ${isPastChapter ? styles.pastChapter : ""}`}
            >
              <button
                type="button"
                className={styles.chapterTitle}
                onClick={() => handleClick(group.chapter.startTime)}
              >
                {group.chapter.title}
                <span className={styles.chapterTime}>{formatTime(group.chapter.startTime)}</span>
              </button>

              {group.chapter.description && (
                <p className={styles.chapterDescription}>{group.chapter.description}</p>
              )}

              <p className={styles.paragraph}>
                {group.segments.map((segment, segmentIndex) => {
                  const actualSegmentIndex = segments.findIndex((s) => s === segment);
                  const isCurrentSegment = actualSegmentIndex === currentSegmentIndex;
                  const isPastSegment = segment.end < currentTime;
                  const isPlayingSegment =
                    currentTime >= segment.start && currentTime < segment.end;
                  const storyStart = storyStartSegments.get(actualSegmentIndex);

                  return (
                    <span key={segmentIndex}>
                      {storyStart && (
                        <button
                          type="button"
                          className={styles.storyMarker}
                          onClick={() => handleClick(storyStart.startTime)}
                          title={storyStart.title}
                        >
                          {storyStart.title}
                        </button>
                      )}
                      <span
                        ref={isCurrentSegment ? activeSegmentRef : null}
                        className={`${styles.segmentText} ${isCurrentSegment ? styles.activeSegment : ""} ${isPastSegment ? styles.pastSegment : ""} ${isPlayingSegment ? styles.playingSegment : ""}`}
                        onClick={() => handleClick(segment.start)}
                        role="button"
                        tabIndex={0}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            handleClick(segment.start);
                          }
                        }}
                      >
                        {segment.text}{" "}
                      </span>
                    </span>
                  );
                })}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
