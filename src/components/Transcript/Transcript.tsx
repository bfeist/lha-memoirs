import { useRef, useEffect, useMemo, useCallback } from "react";
import { formatTime } from "../../hooks/useChristmas1986Data";
import styles from "./Transcript.module.css";

export function Transcript({
  segments,
  chapters,
  currentTime,
  onSegmentClick,
}: {
  segments: TranscriptSegment[];
  chapters: Chapter[];
  currentTime: number;
  onSegmentClick?: (time: number) => void;
}): React.ReactElement {
  const containerRef = useRef<HTMLDivElement>(null);
  const activeChapterRef = useRef<HTMLDivElement>(null);
  const lastScrolledChapterId = useRef<string | null>(null);

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
        },
      ];
    }

    const groups: { chapter: Chapter; segments: TranscriptSegment[] }[] = [];
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
                <span className={styles.chapterIcon}>§</span>
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

                  return (
                    <span
                      key={segmentIndex}
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
