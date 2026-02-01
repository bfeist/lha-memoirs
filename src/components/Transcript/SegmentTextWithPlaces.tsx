import { memo, useMemo } from "react";
import { PlaceTooltip } from "./PlaceTooltip";
import { parseTextWithPlaces } from "../../hooks/usePlaces";

interface SegmentTextWithPlacesProps {
  text: string;
  placesByName: Map<string, Place>;
  placePattern: RegExp | null;
  currentTranscript?: string;
}

/**
 * Renders transcript segment text with interactive place name tooltips
 */
export const SegmentTextWithPlaces = memo(function SegmentTextWithPlaces({
  text,
  placesByName,
  placePattern,
  currentTranscript,
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
            <PlaceTooltip
              key={`place-${idx}-${segment.place.geonameid}`}
              place={segment.place}
              currentTranscript={currentTranscript}
            >
              {segment.content}
            </PlaceTooltip>
          );
        }
        return <span key={`text-${idx}`}>{segment.content}</span>;
      })}{" "}
    </>
  );
});
