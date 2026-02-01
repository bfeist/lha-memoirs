import { useMemo } from "react";
import type { TimelineData, TimelineEntry } from "../types/timeline";

/**
 * Represents a parsed segment of text that may contain years
 */
export interface YearTextSegment {
  type: "text" | "year";
  content: string;
  /** The full 4-digit year (e.g., 1917 for both "1917" and "'17") */
  year?: number;
  /** The timeline entry index that contains this year, if found */
  entryIndex?: number;
}

/**
 * Build a regex pattern that matches years in text
 * Matches:
 * - Full years: 1902, 1917, 1965, etc. (4-digit years starting with 18 or 19)
 * - Abbreviated years: '02, '17, '65, etc. (apostrophe + 2 digits)
 */
export function buildYearPattern(): RegExp {
  // Match either:
  // - A full 4-digit year (18xx or 19xx) with word boundary
  // - An apostrophe followed by 2 digits (abbreviated year)
  // Use negative lookbehind to avoid matching years that are part of larger numbers
  return /(?<!\d)((?:18|19)\d{2})(?!\d)|'(\d{2})(?!\d)/g;
}

/**
 * Convert a 2-digit abbreviated year to a full 4-digit year
 * Assumes years 00-30 are 1900s (for this historical context)
 */
export function expandAbbreviatedYear(twoDigit: string): number {
  const num = parseInt(twoDigit, 10);
  // All abbreviated years in this context are 1900s
  return 1900 + num;
}

/**
 * Find the timeline entry index that contains a given year
 * Returns the index of the entry where year is within [year_start, year_end], or undefined
 */
export function findTimelineEntryForYear(
  year: number,
  entries: TimelineEntry[]
): number | undefined {
  for (let i = 0; i < entries.length; i++) {
    const entry = entries[i];
    if (year >= entry.year_start && year <= entry.year_end) {
      return i;
    }
  }
  return undefined;
}

/**
 * Parse text and find year matches
 * Returns an array of segments, each being either plain text or a year match
 */
export function parseTextWithYears(
  text: string,
  timelineData: TimelineData | null
): YearTextSegment[] {
  const pattern = buildYearPattern();
  const segments: YearTextSegment[] = [];
  let lastIndex = 0;

  // Reset regex lastIndex before matching
  pattern.lastIndex = 0;

  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    const matchedText = match[0];
    const matchIndex = match.index;

    // Add text before the match
    if (matchIndex > lastIndex) {
      segments.push({
        type: "text",
        content: text.slice(lastIndex, matchIndex),
      });
    }

    // Determine the full year
    let fullYear: number;
    if (match[1]) {
      // Full 4-digit year (group 1)
      fullYear = parseInt(match[1], 10);
    } else {
      // Abbreviated year (group 2)
      fullYear = expandAbbreviatedYear(match[2]);
    }

    // Check if this year falls within the timeline range
    const isInTimelineRange =
      timelineData &&
      fullYear >= timelineData.timelineStart &&
      fullYear <= timelineData.timelineEnd;

    if (isInTimelineRange) {
      // Find the entry that contains this year
      const entryIndex = findTimelineEntryForYear(fullYear, timelineData.entries);

      segments.push({
        type: "year",
        content: matchedText,
        year: fullYear,
        entryIndex,
      });
    } else {
      // Year is outside timeline range, treat as plain text
      segments.push({
        type: "text",
        content: matchedText,
      });
    }

    lastIndex = matchIndex + matchedText.length;
  }

  // Add remaining text after last match
  if (lastIndex < text.length) {
    segments.push({
      type: "text",
      content: text.slice(lastIndex),
    });
  }

  return segments;
}

interface TimelineYearUtils {
  parseText: (text: string) => YearTextSegment[];
  findEntryForYear: (year: number) => number | undefined;
  timelineStart: number;
  timelineEnd: number;
}

/**
 * Hook that provides year parsing utilities with timeline data
 */
export function useTimelineYears(timelineData: TimelineData | null): TimelineYearUtils {
  return useMemo(
    () => ({
      parseText: (text: string) => parseTextWithYears(text, timelineData),
      findEntryForYear: (year: number) =>
        timelineData ? findTimelineEntryForYear(year, timelineData.entries) : undefined,
      timelineStart: timelineData?.timelineStart ?? 0,
      timelineEnd: timelineData?.timelineEnd ?? 0,
    }),
    [timelineData]
  );
}
