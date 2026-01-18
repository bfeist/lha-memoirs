import { useRef, useEffect, useMemo, useCallback } from "react";
import { formatTime } from "../../hooks/useRecordingData";
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
  const activeSegmentRef = useRef<HTMLSpanElement>(null);
  const lastScrolledChapterId = useRef<string | null>(null);
  const lastScrolledSegmentIndex = useRef<number | null>(null);

  // Extract minor chapters from the chapters array
  const minorChapters = useMemo(() => chapters.filter((ch) => ch.minor), [chapters]);

  // Pre-compute which segment index is the first for each minor chapter
  // Maps segment index -> Chapter (only for the first segment of each minor chapter)
  const minorChapterStartSegments = useMemo(() => {
    const map = new Map<number, Chapter>();
    if (minorChapters.length === 0) return map;

    for (const minorChapter of minorChapters) {
      // Find the first segment that starts at or after the minor chapter's start time
      let firstSegmentIndex = -1;
      for (let i = 0; i < segments.length; i++) {
        if (segments[i].start >= minorChapter.startTime) {
          firstSegmentIndex = i;
          break;
        }
      }
      if (firstSegmentIndex !== -1) {
        // Only set if not already claimed by another minor chapter
        // (earlier minor chapters take precedence if they share a segment)
        if (!map.has(firstSegmentIndex)) {
          map.set(firstSegmentIndex, minorChapter);
        }
      }
    }
    return map;
  }, [minorChapters, segments]);

  // Get only major chapters for grouping segments
  const majorChapters = useMemo(() => chapters.filter((ch) => !ch.minor), [chapters]);

  // Group segments by major chapter
  const chapterGroups = useMemo(() => {
    if (!majorChapters || majorChapters.length === 0) {
      // If no major chapters, treat all segments as one group
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
    const sortedMajorChapters = [...majorChapters].sort((a, b) => a.startTime - b.startTime);

    for (let i = 0; i < sortedMajorChapters.length; i++) {
      const chapter = sortedMajorChapters[i];
      const nextChapter = sortedMajorChapters[i + 1];
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
  }, [segments, majorChapters]);

  // Find current major chapter and segment based on playback time
  const { currentChapterId, currentSegmentIndex } = useMemo(() => {
    let chapterIndex = 0;
    let segmentIndex = 0;

    // Find current major chapter
    if (majorChapters && majorChapters.length > 0) {
      for (let i = majorChapters.length - 1; i >= 0; i--) {
        if (currentTime >= majorChapters[i].startTime) {
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
  }, [majorChapters, segments, currentTime]);

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
                  const minorChapterStart = minorChapterStartSegments.get(actualSegmentIndex);

                  return (
                    <span key={segmentIndex}>
                      {minorChapterStart && (
                        <button
                          type="button"
                          className={styles.minorChapterMarker}
                          onClick={() => handleClick(minorChapterStart.startTime)}
                          title={minorChapterStart.title}
                        >
                          {minorChapterStart.title}
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
