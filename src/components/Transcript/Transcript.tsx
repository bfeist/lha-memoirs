import { useRef, useLayoutEffect, useMemo, useCallback, useState, memo } from "react";
import { useNavigate } from "react-router-dom";
import { formatTime, useTranscript } from "../../hooks/useRecordingData";
import { usePlaces, buildPlaceNamePattern } from "../../hooks/usePlaces";
import { useTimeline } from "../../hooks/useTimeline";
import { getRecordingByPath } from "../../config/recordings";
import { PhotoInlineSlider } from "./PhotoInlineSlider";
import { VideoInlinePlayer } from "./VideoInlinePlayer";
import { PhotoModal } from "./PhotoModal";
import { VideoModal } from "./VideoModal";
import { AlternateTellingLink } from "./AlternateTellingLink";
import { SegmentTextWithPlaces } from "./SegmentTextWithPlaces";
import { PlacesMapModal } from "../PlacesMap";
import { TimelineModal } from "../Timeline";
import styles from "./Transcript.module.css";

// Extract recording folder name from a path like "memoirs/Norm_red" -> "Norm_red"
function getRecordingFolderName(recordingPath: string): string {
  const parts = recordingPath.split("/");
  return parts[parts.length - 1];
}

interface TranscriptProps {
  segments: TranscriptSegment[];
  chapters: Chapter[];
  currentTime: number;
  onSegmentClick?: (time: number) => void;
  alternateTellings?: AlternateTelling[];
  recordingPath?: string;
  photos?: Photo[];
  videos?: Video[];
  mediaPlacements?: MediaPlacement[];
}

// Custom comparison function for memo - ignore currentTime changes
// since we handle time-based updates via DOM manipulation in useLayoutEffect
function transcriptPropsAreEqual(
  prevProps: InternalTranscriptProps,
  nextProps: InternalTranscriptProps
): boolean {
  // Ignore currentTime - we handle it via refs and DOM manipulation
  // containerRef is stable so we don't need to compare it
  return (
    prevProps.segments === nextProps.segments &&
    prevProps.chapters === nextProps.chapters &&
    prevProps.onSegmentClick === nextProps.onSegmentClick &&
    prevProps.alternateTellings === nextProps.alternateTellings &&
    prevProps.recordingPath === nextProps.recordingPath &&
    prevProps.photos === nextProps.photos &&
    prevProps.videos === nextProps.videos &&
    prevProps.mediaPlacements === nextProps.mediaPlacements
  );
}

interface InternalTranscriptProps extends Omit<TranscriptProps, "currentTime"> {
  currentTime: number; // Still passed but ignored in comparison
  containerRef: React.RefObject<HTMLDivElement | null>;
}

// Wrapper component that receives currentTime and manages DOM updates
// The inner Transcript component is memoized to not re-render on time changes
export function TranscriptWithTimeUpdates(props: TranscriptProps): React.ReactElement {
  const containerRef = useRef<HTMLDivElement>(null);
  const prevSegmentIndexRef = useRef<number>(-1);
  const prevChapterIndexRef = useRef<number>(-1);
  const lastScrolledChapterId = useRef<string | null>(null);
  const lastScrolledSegmentIndex = useRef<number | null>(null);

  const { currentTime, segments, chapters } = props;

  // Get major chapters for index computation
  const majorChapters = useMemo(() => chapters.filter((ch) => !ch.minor), [chapters]);

  // Use layout effect to synchronously update segment highlighting via DOM
  // This runs on every time change but doesn't cause Transcript to re-render
  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Compute current chapter index
    let currentChapterIndex = 0;
    if (majorChapters && majorChapters.length > 0) {
      for (let i = majorChapters.length - 1; i >= 0; i--) {
        if (currentTime >= majorChapters[i].startTime) {
          currentChapterIndex = i;
          break;
        }
      }
    }

    // Compute current segment index
    let currentSegmentIndex = 0;
    for (let i = segments.length - 1; i >= 0; i--) {
      if (currentTime >= segments[i].start) {
        currentSegmentIndex = i;
        break;
      }
    }

    const currentChapterId = `chapter-${currentChapterIndex}`;
    const prevSegmentIdx = prevSegmentIndexRef.current;
    const prevChapterIdx = prevChapterIndexRef.current;

    // Update segment classes if segment changed
    if (prevSegmentIdx !== currentSegmentIndex) {
      // Remove classes from previous segment
      if (prevSegmentIdx >= 0) {
        const prevEl = container.querySelector(
          `[data-segment-index="${prevSegmentIdx}"]`
        ) as HTMLElement | null;
        if (prevEl) {
          prevEl.classList.remove(styles.activeSegment, styles.playingSegment);
          prevEl.classList.add(styles.pastSegment);
        }
      }
      // Add classes to current segment
      const currentEl = container.querySelector(
        `[data-segment-index="${currentSegmentIndex}"]`
      ) as HTMLElement | null;
      if (currentEl) {
        currentEl.classList.add(styles.activeSegment, styles.playingSegment);
        currentEl.classList.remove(styles.pastSegment);

        // Auto-scroll to keep current segment in view
        if (currentSegmentIndex !== lastScrolledSegmentIndex.current) {
          lastScrolledSegmentIndex.current = currentSegmentIndex;
          const containerRect = container.getBoundingClientRect();
          const segmentRect = currentEl.getBoundingClientRect();
          const isAbove = segmentRect.top < containerRect.top + 60;
          const isBelow = segmentRect.bottom > containerRect.bottom - 60;
          if (isAbove || isBelow) {
            currentEl.scrollIntoView({ behavior: "smooth", block: "center" });
          }
        }
      }
      prevSegmentIndexRef.current = currentSegmentIndex;
    }

    // Update chapter classes if chapter changed
    if (prevChapterIdx !== currentChapterIndex) {
      // Remove active class from previous chapter
      if (prevChapterIdx >= 0) {
        const prevChapterEl = container.querySelector(
          `[data-chapter-index="${prevChapterIdx}"]`
        ) as HTMLElement | null;
        if (prevChapterEl) {
          prevChapterEl.classList.remove(styles.activeChapter);
          prevChapterEl.classList.add(styles.pastChapter);
        }
      }
      // Add active class to current chapter
      const currentChapterEl = container.querySelector(
        `[data-chapter-index="${currentChapterIndex}"]`
      ) as HTMLElement | null;
      if (currentChapterEl) {
        currentChapterEl.classList.add(styles.activeChapter);
        currentChapterEl.classList.remove(styles.pastChapter);

        // Auto-scroll if chapter changed and is outside visible area
        if (currentChapterId !== lastScrolledChapterId.current) {
          lastScrolledChapterId.current = currentChapterId;
          const containerRect = container.getBoundingClientRect();
          const chapterRect = currentChapterEl.getBoundingClientRect();
          const isAbove = chapterRect.top < containerRect.top + 50;
          const isBelow = chapterRect.bottom > containerRect.bottom - 100;
          if (isAbove || isBelow) {
            currentChapterEl.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        }
      }
      prevChapterIndexRef.current = currentChapterIndex;
    }
  }, [currentTime, segments, majorChapters]);

  return <Transcript {...props} containerRef={containerRef} />;
}

const Transcript = memo(function Transcript({
  segments,
  chapters,
  onSegmentClick,
  alternateTellings,
  recordingPath,
  photos,
  videos,
  mediaPlacements,
  containerRef,
}: InternalTranscriptProps): React.ReactElement {
  const navigate = useNavigate();

  // Modal state for viewing full-res photos
  const [modalPhoto, setModalPhoto] = useState<Photo | null>(null);

  // Modal state for viewing videos in fullscreen
  const [modalVideo, setModalVideo] = useState<{
    video: Video;
    startTime?: number;
    endTime?: number;
  } | null>(null);

  // Modal state for viewing places map
  const [showPlacesMap, setShowPlacesMap] = useState(false);
  const [selectedPlaceId, setSelectedPlaceId] = useState<number | null>(null);

  // Modal state for viewing timeline
  const [showTimeline, setShowTimeline] = useState(false);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);

  // Load places data for interactive tooltips
  const { places, placesByName } = usePlaces();

  // Load timeline data for year highlighting
  const { data: timelineData } = useTimeline();

  // Build regex pattern for matching place names in text
  const placePattern = useMemo(() => {
    const placeNames = places.map((p) => p.name);
    return buildPlaceNamePattern(placeNames);
  }, [places]);

  // Get current recording folder name for matching
  const currentRecordingFolder = useMemo(
    () => (recordingPath ? getRecordingFolderName(recordingPath) : ""),
    [recordingPath]
  );

  // Fetch transcripts for both memoir recordings for alternate telling excerpts
  const normRedTranscript = useTranscript("memoirs/Norm_red");
  const tdkTranscript = useTranscript("memoirs/TDK_D60_edited_through_air");

  // Create a lookup map for photos by filename
  const photosByFilename = useMemo(() => {
    const map = new Map<string, Photo>();
    if (photos) {
      for (const photo of photos) {
        map.set(photo.filename, photo);
      }
    }
    return map;
  }, [photos]);

  // Create a lookup map for videos by filename
  const videosByFilename = useMemo(() => {
    const map = new Map<string, Video>();
    if (videos) {
      for (const video of videos) {
        map.set(video.filename, video);
      }
    }
    return map;
  }, [videos]);

  // Pre-compute which segment index should display photos
  // Maps segment index -> array of Photo objects
  const segmentPhotos = useMemo(() => {
    const map = new Map<number, Photo[]>();
    if (!mediaPlacements || mediaPlacements.length === 0 || segments.length === 0) return map;

    for (const placement of mediaPlacements) {
      // Only handle photo placements for now
      if (placement.type !== "photo" || !placement.filenames) continue;

      // Find the segment that contains this seconds marker
      // The photo should appear before/at the segment that starts at or after this time
      let targetSegmentIndex = -1;
      for (let i = 0; i < segments.length; i++) {
        if (segments[i].start >= placement.seconds) {
          targetSegmentIndex = i;
          break;
        }
      }
      // If no segment starts after the placement time, put it at the last segment
      if (targetSegmentIndex === -1) {
        targetSegmentIndex = segments.length - 1;
      }

      // Collect the photos for this placement
      const placementPhotos: Photo[] = [];
      for (const filename of placement.filenames) {
        const photo = photosByFilename.get(filename);
        if (photo) {
          placementPhotos.push(photo);
        }
      }

      if (placementPhotos.length > 0) {
        // Merge with existing photos at this segment if any
        const existing = map.get(targetSegmentIndex) || [];
        map.set(targetSegmentIndex, [...existing, ...placementPhotos]);
      }
    }
    return map;
  }, [mediaPlacements, segments, photosByFilename]);

  // Video placement info includes video metadata plus start/end times
  interface VideoPlacement {
    video: Video;
    startTime?: number;
    endTime?: number;
  }

  // Pre-compute which segment index should display videos
  // Maps segment index -> array of VideoPlacement objects
  const segmentVideos = useMemo(() => {
    const map = new Map<number, VideoPlacement[]>();
    if (!mediaPlacements || mediaPlacements.length === 0 || segments.length === 0) return map;

    for (const placement of mediaPlacements) {
      // Only handle video placements
      if (placement.type !== "video" || !placement.filenames || placement.filenames.length === 0)
        continue;

      // Find the segment that contains this seconds marker
      let targetSegmentIndex = -1;
      for (let i = 0; i < segments.length; i++) {
        if (segments[i].start >= placement.seconds) {
          targetSegmentIndex = i;
          break;
        }
      }
      // If no segment starts after the placement time, put it at the last segment
      if (targetSegmentIndex === -1) {
        targetSegmentIndex = segments.length - 1;
      }

      // Get the video for this placement (use first filename)
      const video = videosByFilename.get(placement.filenames[0]);
      if (video) {
        const videoPlacement: VideoPlacement = {
          video,
          startTime: placement.start,
          endTime: placement.end,
        };
        // Merge with existing videos at this segment if any
        const existing = map.get(targetSegmentIndex) || [];
        map.set(targetSegmentIndex, [...existing, videoPlacement]);
      }
    }
    return map;
  }, [mediaPlacements, segments, videosByFilename]);

  // Pre-compute which alternate tellings should appear before each segment
  // Maps segment index -> array of alternate telling info
  interface AlternatePlacement {
    otherRecordingTitle: string;
    otherTopic: string;
    otherRecordingPath: string;
    otherStartTime: number;
    otherStartSecs: number;
    otherEndSecs: number;
  }

  // Helper function to extract transcript text for a given time range
  const getTranscriptExcerpt = useCallback(
    (transcriptSegments: TranscriptSegment[], startSecs: number, endSecs: number): string => {
      const relevantSegments = transcriptSegments.filter(
        (seg) =>
          (seg.start >= startSecs && seg.start < endSecs) ||
          (seg.end > startSecs && seg.end <= endSecs) ||
          (seg.start <= startSecs && seg.end >= endSecs)
      );
      return relevantSegments.map((seg) => seg.text).join(" ");
    },
    []
  );

  const segmentAlternateTellings = useMemo(() => {
    const map = new Map<number, AlternatePlacement[]>();
    if (!alternateTellings || alternateTellings.length === 0 || segments.length === 0) return map;

    for (const telling of alternateTellings) {
      // Determine which window corresponds to the current recording
      const isNormRed = currentRecordingFolder === "Norm_red";
      const currentWindow = isNormRed ? telling.norm_window : telling.tdk_window;
      const otherWindow = isNormRed ? telling.tdk_window : telling.norm_window;
      const otherRecordingKey = isNormRed ? "TDK_D60_edited_through_air" : "Norm_red";

      // Find the segment that contains or comes after this timestamp
      let targetSegmentIndex = -1;
      for (let i = 0; i < segments.length; i++) {
        if (segments[i].start >= currentWindow.start) {
          targetSegmentIndex = i;
          break;
        }
      }
      // If no segment starts after the placement time, put it at the last segment
      if (targetSegmentIndex === -1) {
        targetSegmentIndex = segments.length - 1;
      }

      // Get the other recording's title from config
      const otherRecording = getRecordingByPath(`memoirs/${otherRecordingKey}`);
      const otherRecordingTitle = otherRecording?.title || otherRecordingKey;

      const placement: AlternatePlacement = {
        otherRecordingTitle,
        otherTopic: otherWindow.topics,
        otherRecordingPath: `memoirs/${otherRecordingKey}`,
        otherStartTime: otherWindow.start,
        otherStartSecs: otherWindow.start,
        otherEndSecs: otherWindow.end,
      };

      // Merge with existing alternate tellings at this segment if any
      const existing = map.get(targetSegmentIndex) || [];
      map.set(targetSegmentIndex, [...existing, placement]);
    }
    return map;
  }, [alternateTellings, segments, currentRecordingFolder]);

  // Handlers for photo modal
  const handlePhotoClick = useCallback((photo: Photo) => {
    setModalPhoto(photo);
  }, []);

  const handleCloseModal = useCallback(() => {
    setModalPhoto(null);
  }, []);

  // Handlers for video modal
  const handleOpenVideoModal = useCallback((video: Video, startTime?: number, endTime?: number) => {
    setModalVideo({ video, startTime, endTime });
  }, []);

  const handleCloseVideoModal = useCallback(() => {
    setModalVideo(null);
  }, []);

  // Handlers for places map modal
  const handlePlaceClick = useCallback((place: Place) => {
    setSelectedPlaceId(place.geonameid);
    setShowPlacesMap(true);
  }, []);

  const handleClosePlacesMap = useCallback(() => {
    setShowPlacesMap(false);
    setSelectedPlaceId(null);
  }, []);

  // Handlers for timeline modal
  const handleYearClick = useCallback((year: number) => {
    setSelectedYear(year);
    setShowTimeline(true);
  }, []);

  const handleCloseTimeline = useCallback(() => {
    setShowTimeline(false);
    setSelectedYear(null);
  }, []);

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

      // For the first chapter, include segments that start slightly before it (up to 5 seconds)
      // This handles cases where transcripts start a few seconds before the first chapter marker
      const chapterStart = i === 0 ? Math.max(0, chapter.startTime - 5) : chapter.startTime;

      const chapterSegments = segments.filter(
        (seg) => seg.start >= chapterStart && seg.start < chapterEnd
      );

      groups.push({
        chapter,
        segments: chapterSegments,
        chapterIndex: i,
      });
    }

    return groups;
  }, [segments, majorChapters]);

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
        {chapterGroups.map((group, groupIndex) => (
          <div key={groupIndex} data-chapter-index={groupIndex} className={styles.chapterSection}>
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

            {group.chapter.audioFile && (
              /* eslint-disable-next-line jsx-a11y/media-has-caption */
              <audio
                controls
                preload="none"
                src={group.chapter.audioFile}
                className={styles.chapterAudio}
              />
            )}

            <div className={styles.paragraph}>
              {group.segments.map((segment, segmentIndex) => {
                const actualSegmentIndex = segments.findIndex((s) => s === segment);
                const minorChapterStart = minorChapterStartSegments.get(actualSegmentIndex);
                const photosForSegment = segmentPhotos.get(actualSegmentIndex);
                const videosForSegment = segmentVideos.get(actualSegmentIndex);
                const alternateTellingsForSegment =
                  segmentAlternateTellings.get(actualSegmentIndex);

                // Alternate float direction for media (odd segments left, even right)
                const mediaFloat = segmentIndex % 2 === 0 ? "right" : "left";

                return (
                  <span key={segmentIndex}>
                    {/* Inline video player - displayed before the segment text */}
                    {videosForSegment &&
                      videosForSegment.length > 0 &&
                      videosForSegment.map((vp, vIdx) => (
                        <VideoInlinePlayer
                          key={`video-${vp.video.filename}-${vIdx}`}
                          video={vp.video}
                          startTime={vp.startTime}
                          endTime={vp.endTime}
                          float={mediaFloat}
                          onOpenModal={() =>
                            handleOpenVideoModal(vp.video, vp.startTime, vp.endTime)
                          }
                        />
                      ))}
                    {/* Inline photo slider - displayed before the segment text */}
                    {photosForSegment && photosForSegment.length > 0 && (
                      <PhotoInlineSlider
                        photos={photosForSegment}
                        onPhotoClick={handlePhotoClick}
                        float={mediaFloat}
                      />
                    )}
                    {/* Alternate telling links - displayed before the segment text */}
                    {alternateTellingsForSegment &&
                      alternateTellingsForSegment.length > 0 &&
                      alternateTellingsForSegment.map((alt, altIdx) => {
                        // Get the other recording's transcript
                        const otherTranscriptData =
                          alt.otherRecordingPath === "memoirs/Norm_red"
                            ? normRedTranscript.data
                            : tdkTranscript.data;
                        const transcriptExcerpt = otherTranscriptData
                          ? getTranscriptExcerpt(
                              otherTranscriptData.segments,
                              alt.otherStartSecs,
                              alt.otherEndSecs
                            )
                          : "";

                        return (
                          <AlternateTellingLink
                            key={`alt-${actualSegmentIndex}-${altIdx}`}
                            recordingTitle={alt.otherRecordingTitle}
                            topic={alt.otherTopic}
                            transcriptExcerpt={transcriptExcerpt}
                            onClick={() => {
                              const otherRecording = getRecordingByPath(alt.otherRecordingPath);
                              if (otherRecording) {
                                navigate(
                                  `/recording/${otherRecording.id}?t=${Math.floor(alt.otherStartTime)}`
                                );
                              }
                            }}
                          />
                        );
                      })}
                    {minorChapterStart && (
                      <button
                        type="button"
                        className={styles.minorChapterMarker}
                        onClick={() => handleClick(minorChapterStart.startTime)}
                        title={minorChapterStart.description || minorChapterStart.title}
                      >
                        {minorChapterStart.title}
                      </button>
                    )}
                    <span
                      data-segment-index={actualSegmentIndex}
                      className={styles.segmentText}
                      onClick={() => handleClick(segment.start)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          handleClick(segment.start);
                        }
                      }}
                    >
                      <SegmentTextWithPlaces
                        text={segment.text}
                        placesByName={placesByName}
                        placePattern={placePattern}
                        onPlaceClick={handlePlaceClick}
                        timelineData={timelineData}
                        onYearClick={handleYearClick}
                      />
                    </span>
                  </span>
                );
              })}
              {/* Clearfix for floated photos */}
              <span className={styles.clearfix} />
            </div>
          </div>
        ))}
      </div>

      {/* Photo Modal for viewing full-resolution photos */}
      <PhotoModal photo={modalPhoto} onClose={handleCloseModal} />

      {/* Video Modal for fullscreen video playback */}
      <VideoModal
        video={modalVideo?.video ?? null}
        startTime={modalVideo?.startTime}
        endTime={modalVideo?.endTime}
        onClose={handleCloseVideoModal}
      />

      {/* Places Map Modal for viewing places */}
      <PlacesMapModal
        key={`places-map-${selectedPlaceId}`}
        isOpen={showPlacesMap}
        onClose={handleClosePlacesMap}
        initialPlaceId={selectedPlaceId}
      />

      {/* Timeline Modal for viewing years */}
      <TimelineModal
        key={`timeline-${selectedYear}`}
        isOpen={showTimeline}
        onClose={handleCloseTimeline}
        initialYear={selectedYear}
      />
    </div>
  );
}, transcriptPropsAreEqual);
