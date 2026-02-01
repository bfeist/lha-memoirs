import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import type { TimelineData } from "../../types/timeline";
import styles from "./Timeline.module.css";

interface TimelineProps {
  data: TimelineData;
  selectedEntryIndex: number | null;
  onEntrySelect: (index: number | null) => void;
}

/**
 * Calculate the position of a year on the timeline (0-100%)
 */
function getYearPosition(year: number, startYear: number, endYear: number): number {
  return ((year - startYear) / (endYear - startYear)) * 100;
}

/**
 * Interactive horizontal timeline bar
 */
export function Timeline({
  data,
  selectedEntryIndex,
  onEntrySelect,
}: TimelineProps): React.ReactElement {
  const timelineRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  const { timelineStart, timelineEnd, entries } = data;

  // Create decade markers
  const decades = useMemo(() => {
    const result: number[] = [];
    const startDecade = Math.ceil(timelineStart / 10) * 10;
    for (let year = startDecade; year <= timelineEnd; year += 10) {
      result.push(year);
    }
    return result;
  }, [timelineStart, timelineEnd]);

  // Find entry by year
  const findEntryByYear = useCallback(
    (year: number): number | null => {
      for (let i = 0; i < entries.length; i++) {
        const entry = entries[i];
        if (year >= entry.year_start && year <= entry.year_end) {
          return i;
        }
      }
      // Find closest entry
      let closestIdx = 0;
      let closestDist = Math.abs(entries[0].year_start - year);
      for (let i = 1; i < entries.length; i++) {
        const dist = Math.min(
          Math.abs(entries[i].year_start - year),
          Math.abs(entries[i].year_end - year)
        );
        if (dist < closestDist) {
          closestDist = dist;
          closestIdx = i;
        }
      }
      return closestIdx;
    },
    [entries]
  );

  // Get year from mouse position
  const getYearFromPosition = useCallback(
    (clientX: number): number => {
      if (!timelineRef.current) return timelineStart;
      const rect = timelineRef.current.getBoundingClientRect();
      const percentage = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      const year = Math.round(timelineStart + percentage * (timelineEnd - timelineStart));
      return Math.max(timelineStart, Math.min(timelineEnd, year));
    },
    [timelineStart, timelineEnd]
  );

  // Handle mouse/touch move - always select entry on hover/drag
  const handleMove = useCallback(
    (clientX: number) => {
      const year = getYearFromPosition(clientX);
      const entryIdx = findEntryByYear(year);
      // Always select on hover - panel stays until user interacts again
      onEntrySelect(entryIdx);
    },
    [getYearFromPosition, findEntryByYear, onEntrySelect]
  );

  // Mouse handlers
  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      handleMove(e.clientX);
    },
    [handleMove]
  );

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleMouseLeave = useCallback(() => {
    // Don't clear selection on mouse leave - panel stays until next interaction
    setIsDragging(false);
  }, []);

  // Touch handlers
  const handleTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (e.touches.length === 1) {
        const touch = e.touches[0];
        const year = getYearFromPosition(touch.clientX);
        const entryIdx = findEntryByYear(year);
        onEntrySelect(entryIdx);
        setIsDragging(true);
      }
    },
    [getYearFromPosition, findEntryByYear, onEntrySelect]
  );

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (e.touches.length === 1 && isDragging) {
        const touch = e.touches[0];
        handleMove(touch.clientX);
      }
    },
    [handleMove, isDragging]
  );

  const handleTouchEnd = useCallback(() => {
    setIsDragging(false);
  }, []);

  // Global mouse up handler for drag
  useEffect(() => {
    const handleGlobalMouseUp = (): void => {
      setIsDragging(false);
    };
    window.addEventListener("mouseup", handleGlobalMouseUp);
    return () => window.removeEventListener("mouseup", handleGlobalMouseUp);
  }, []);

  // Get the entry to display
  const displayEntry = selectedEntryIndex !== null ? entries[selectedEntryIndex] : null;

  return (
    <div className={styles.timelineWrapper}>
      {/* Year labels for quick preview */}
      <div className={styles.yearPreview}>
        {displayEntry ? (
          <span className={styles.yearLabel}>
            {displayEntry.year_start === displayEntry.year_end
              ? displayEntry.year_start
              : `${displayEntry.year_start}–${displayEntry.year_end}`}
            <span className={styles.ageLabel}>
              (age{" "}
              {displayEntry.age_start === displayEntry.age_end
                ? displayEntry.age_start
                : `${displayEntry.age_start}–${displayEntry.age_end}`}
              )
            </span>
          </span>
        ) : (
          <span className={styles.yearLabelEmpty}>Hover or tap the timeline</span>
        )}
      </div>

      {/* Timeline bar */}
      <div
        ref={timelineRef}
        className={styles.timeline}
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseLeave}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        role="slider"
        aria-label="Timeline from 1902 to 1966"
        aria-valuemin={timelineStart}
        aria-valuemax={timelineEnd}
        aria-valuenow={displayEntry?.year_start}
        tabIndex={0}
      >
        {/* Background track */}
        <div className={styles.track} />

        {/* Entry markers/segments */}
        {entries.map((entry, idx) => {
          const startPos = getYearPosition(entry.year_start, timelineStart, timelineEnd);
          const endPos = getYearPosition(entry.year_end, timelineStart, timelineEnd);
          const width = Math.max(1, endPos - startPos);
          const isActive = idx === selectedEntryIndex;
          const isSelected = idx === selectedEntryIndex;

          return (
            <div
              key={idx}
              className={`${styles.segment} ${isActive ? styles.active : ""} ${isSelected ? styles.selected : ""}`}
              style={{
                left: `${startPos}%`,
                width: `${width}%`,
              }}
            />
          );
        })}

        {/* Decade markers */}
        {decades.map((decade) => {
          const pos = getYearPosition(decade, timelineStart, timelineEnd);
          return (
            <div key={decade} className={styles.decadeMarker} style={{ left: `${pos}%` }}>
              <span className={styles.decadeLabel}>{decade}</span>
            </div>
          );
        })}

        {/* Active position indicator */}
        {displayEntry && (
          <div
            className={styles.indicator}
            style={{
              left: `${getYearPosition((displayEntry.year_start + displayEntry.year_end) / 2, timelineStart, timelineEnd)}%`,
            }}
          />
        )}
      </div>

      {/* Start/End year labels */}
      <div className={styles.yearBounds}>
        <span>{timelineStart}</span>
        <span>{timelineEnd}</span>
      </div>
    </div>
  );
}
