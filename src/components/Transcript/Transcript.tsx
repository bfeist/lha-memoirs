import { useRef, useEffect, useMemo, useCallback, useState, memo } from "react";
import { useNavigate } from "react-router-dom";
import { formatTime } from "../../hooks/useRecordingData";
import { usePlaces, buildPlaceNamePattern } from "../../hooks/usePlaces";
import { getRecordingByPath } from "../../config/recordings";
import { PhotoInlineSlider } from "./PhotoInlineSlider";
import { VideoInlinePlayer } from "./VideoInlinePlayer";
import { PhotoModal } from "./PhotoModal";
import { VideoModal } from "./VideoModal";
import { AlternateTellingLink } from "./AlternateTellingLink";
import { SegmentTextWithPlaces } from "./SegmentTextWithPlaces";
import styles from "./Transcript.module.css";

// Extract recording folder name from a path like "memoirs/Norm_red" -> "Norm_red"
function getRecordingFolderName(recordingPath: string): string {
  const parts = recordingPath.split("/");
  return parts[parts.length - 1];
}

export const Transcript = memo(function Transcript({
  segments,
  chapters,
  currentTime,
  onSegmentClick,
  alternateTellings,
  recordingPath,
  photos,
  videos,
  mediaPlacements,
}: {
  segments: TranscriptSegment[];
  chapters: Chapter[];
  currentTime: number;
  onSegmentClick?: (time: number) => void;
  alternateTellings?: AlternateTelling[];
  recordingPath?: string;
  photos?: Photo[];
  videos?: Video[];
  mediaPlacements?: MediaPlacement[];
}): React.ReactElement {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const activeChapterRef = useRef<HTMLDivElement>(null);
  const activeSegmentRef = useRef<HTMLSpanElement>(null);
  const lastScrolledChapterId = useRef<string | null>(null);
  const lastScrolledSegmentIndex = useRef<number | null>(null);

  // Modal state for viewing full-res photos
  const [modalPhoto, setModalPhoto] = useState<Photo | null>(null);

  // Modal state for viewing videos in fullscreen
  const [modalVideo, setModalVideo] = useState<{
    video: Video;
    startTime?: number;
    endTime?: number;
  } | null>(null);

  // Load places data for interactive tooltips
  const { places, placesByName } = usePlaces();

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
    topic: string;
    preview: string;
    otherRecordingPath: string;
    otherStartTime: number;
  }

  const segmentAlternateTellings = useMemo(() => {
    const map = new Map<number, AlternatePlacement[]>();
    if (!alternateTellings || alternateTellings.length === 0 || segments.length === 0) return map;

    for (const telling of alternateTellings) {
      // Get the current and other recording data
      const currentData = telling[currentRecordingFolder as keyof AlternateTelling] as
        | AlternateRecordingSegment
        | undefined;
      if (!currentData || typeof currentData !== "object" || !currentData.startTime) continue;

      // Find the other recording (the one that's not current)
      const otherRecordingKey =
        currentRecordingFolder === "Norm_red" ? "TDK_D60_edited_through_air" : "Norm_red";
      const otherData = telling[otherRecordingKey as keyof AlternateTelling] as
        | AlternateRecordingSegment
        | undefined;
      if (!otherData || typeof otherData !== "object" || !otherData.startTime) continue;

      // Find the segment that contains or comes after this timestamp
      let targetSegmentIndex = -1;
      for (let i = 0; i < segments.length; i++) {
        if (segments[i].start >= currentData.startTime) {
          targetSegmentIndex = i;
          break;
        }
      }
      // If no segment starts after the placement time, put it at the last segment
      if (targetSegmentIndex === -1) {
        targetSegmentIndex = segments.length - 1;
      }

      const placement: AlternatePlacement = {
        topic: telling.topic,
        preview: otherData.preview,
        otherRecordingPath: `memoirs/${otherRecordingKey}`,
        otherStartTime: otherData.startTime,
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

              <div className={styles.paragraph}>
                {group.segments.map((segment, segmentIndex) => {
                  const actualSegmentIndex = segments.findIndex((s) => s === segment);
                  const isCurrentSegment = actualSegmentIndex === currentSegmentIndex;
                  const isPastSegment = segment.end < currentTime;
                  const isPlayingSegment =
                    currentTime >= segment.start && currentTime < segment.end;
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
                        alternateTellingsForSegment.map((alt, altIdx) => (
                          <AlternateTellingLink
                            key={`alt-${actualSegmentIndex}-${altIdx}`}
                            topic={alt.topic}
                            preview={alt.preview}
                            onClick={() => {
                              const otherRecording = getRecordingByPath(alt.otherRecordingPath);
                              if (otherRecording) {
                                navigate(
                                  `/recording/${otherRecording.id}?t=${Math.floor(alt.otherStartTime)}`
                                );
                              }
                            }}
                          />
                        ))}
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
                        <SegmentTextWithPlaces
                          text={segment.text}
                          placesByName={placesByName}
                          placePattern={placePattern}
                          currentTranscript={recordingPath}
                        />
                      </span>
                    </span>
                  );
                })}
                {/* Clearfix for floated photos */}
                <span className={styles.clearfix} />
              </div>
            </div>
          );
        })}
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
    </div>
  );
});
