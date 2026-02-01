import { memo, useMemo } from "react";
import { parseTextWithPlaces } from "../../hooks/usePlaces";
import { parseTextWithYears } from "../../hooks/useTimelineYears";
import type { TimelineData } from "../../types/timeline";
import styles from "./SegmentTextWithPlaces.module.css";

interface SegmentTextWithPlacesProps {
  text: string;
  placesByName: Map<string, Place>;
  placePattern: RegExp | null;
  onPlaceClick?: (place: Place) => void;
  timelineData?: TimelineData | null;
  onYearClick?: (year: number, entryIndex?: number) => void;
}

/**
 * Combined segment type for text that may contain places or years
 */
interface CombinedSegment {
  type: "text" | "place" | "year";
  content: string;
  place?: Place;
  year?: number;
  entryIndex?: number;
}

/**
 * Parse a text segment for years, returning combined segments
 */
function parseSegmentForYears(
  textContent: string,
  timelineData: TimelineData | null
): CombinedSegment[] {
  if (!timelineData) {
    return [{ type: "text", content: textContent }];
  }

  const yearSegments = parseTextWithYears(textContent, timelineData);
  return yearSegments.map((seg): CombinedSegment => {
    if (seg.type === "year") {
      return {
        type: "year",
        content: seg.content,
        year: seg.year,
        entryIndex: seg.entryIndex,
      };
    }
    return { type: "text", content: seg.content };
  });
}

/**
 * Two-pass parsing: first find places, then within text segments find years
 */
function parseTextWithPlacesAndYears(
  text: string,
  placesByName: Map<string, Place>,
  placePattern: RegExp | null,
  timelineData: TimelineData | null
): CombinedSegment[] {
  // First pass: parse for places
  const placeSegments = parseTextWithPlaces(text, placesByName, placePattern);

  // Second pass: for each text segment, parse for years
  const combinedSegments: CombinedSegment[] = [];

  for (const segment of placeSegments) {
    if (segment.type === "place" && segment.place) {
      combinedSegments.push({
        type: "place",
        content: segment.content,
        place: segment.place,
      });
    } else {
      // It's a text segment - check for years
      const yearParsed = parseSegmentForYears(segment.content, timelineData);
      combinedSegments.push(...yearParsed);
    }
  }

  return combinedSegments;
}

/**
 * Renders transcript segment text with interactive place name and year links
 */
export const SegmentTextWithPlaces = memo(function SegmentTextWithPlaces({
  text,
  placesByName,
  placePattern,
  onPlaceClick,
  timelineData,
  onYearClick,
}: SegmentTextWithPlacesProps) {
  const segments = useMemo(
    () => parseTextWithPlacesAndYears(text, placesByName, placePattern, timelineData ?? null),
    [text, placesByName, placePattern, timelineData]
  );

  // If no places or years found, just return the text
  if (segments.length === 1 && segments[0].type === "text") {
    return <>{text} </>;
  }

  return (
    <>
      {segments.map((segment, idx) => {
        if (segment.type === "place" && segment.place) {
          return (
            <button
              key={`place-${idx}-${segment.place.geonameid}`}
              type="button"
              className={styles.placeLink}
              onClick={(e) => {
                e.stopPropagation();
                onPlaceClick?.(segment.place!);
              }}
              title={`View ${segment.place.name} on map`}
            >
              {segment.content}
            </button>
          );
        }
        if (segment.type === "year" && segment.year !== undefined) {
          return (
            <button
              key={`year-${idx}-${segment.year}`}
              type="button"
              className={styles.yearLink}
              onClick={(e) => {
                e.stopPropagation();
                onYearClick?.(segment.year!, segment.entryIndex);
              }}
              title={`View ${segment.year} in timeline`}
            >
              {segment.content}
            </button>
          );
        }
        return <span key={`text-${idx}`}>{segment.content}</span>;
      })}{" "}
    </>
  );
});
