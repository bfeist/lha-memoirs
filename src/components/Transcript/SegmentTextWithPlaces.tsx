import { memo, useMemo } from "react";
import { parseTextWithPlaces } from "../../hooks/usePlaces";
import styles from "./SegmentTextWithPlaces.module.css";

interface SegmentTextWithPlacesProps {
  text: string;
  placesByName: Map<string, Place>;
  placePattern: RegExp | null;
  onPlaceClick?: (place: Place) => void;
}

/**
 * Renders transcript segment text with interactive place name links
 */
export const SegmentTextWithPlaces = memo(function SegmentTextWithPlaces({
  text,
  placesByName,
  placePattern,
  onPlaceClick,
}: SegmentTextWithPlacesProps) {
  const segments = useMemo(
    () => parseTextWithPlaces(text, placesByName, placePattern),
    [text, placesByName, placePattern]
  );

  // If no places found, just return the text
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
        return <span key={`text-${idx}`}>{segment.content}</span>;
      })}{" "}
    </>
  );
});
