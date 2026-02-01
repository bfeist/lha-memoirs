import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useMemo } from "react";

// Default region color for waveform segments
const REGION_COLOR = "rgba(100, 149, 237, 0.3)";

// Build the base path for a recording
function getRecordingBasePath(recordingPath: string): string {
  return `/recordings/${recordingPath}`;
}

// Check if a recording is a memoir (nested under memoirs/)
function isMemoirRecording(recordingPath: string): boolean {
  return recordingPath.startsWith("memoirs/");
}

// Format seconds as MM:SS
export function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

// CSV delimiter used in transcript files
const CSV_DELIMITER = "|";

/**
 * Parse pipe-delimited CSV transcript format into TranscriptData.
 *
 * Format:
 * - Header row: start|end|text
 * - Data rows: 6.45|10.61|I go right back, and it starts in where I taped ...
 */
function parseTranscriptCsv(csvText: string): TranscriptData {
  const lines = csvText.split("\n");
  const segments: TranscriptSegment[] = [];

  let dataStart = 0;

  // Find data start (skip comments and header)
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith("#")) {
      // Skip comment lines
      continue;
    } else if (line.toLowerCase().startsWith("start|")) {
      // Skip header row (must have pipe to distinguish from data)
      dataStart = i + 1;
      break;
    } else if (line) {
      // Non-empty, non-comment, non-header line - data starts here
      dataStart = i;
      break;
    }
  }

  // Parse data rows
  for (let i = dataStart; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line || line.startsWith("#")) continue;

    // Split by delimiter, but only first 2 splits (text may contain |)
    const firstPipe = line.indexOf(CSV_DELIMITER);
    if (firstPipe === -1) continue;

    const secondPipe = line.indexOf(CSV_DELIMITER, firstPipe + 1);
    if (secondPipe === -1) continue;

    const startStr = line.substring(0, firstPipe);
    const endStr = line.substring(firstPipe + 1, secondPipe);
    let text = line.substring(secondPipe + 1);

    // Unescape double pipes back to single pipes
    text = text.replace(/\|\|/g, "|");

    const start = parseFloat(startStr);
    const end = parseFloat(endStr);

    if (!isNaN(start) && !isNaN(end)) {
      segments.push({ start, end, text });
    }
  }

  return {
    segments,
  };
}

// Fetch transcript data for a recording (CSV format)
export function useTranscript(recordingPath: string): UseQueryResult<TranscriptData, Error> {
  const basePath = getRecordingBasePath(recordingPath);

  return useQuery<TranscriptData>({
    queryKey: ["recording", recordingPath, "transcript"],
    queryFn: async () => {
      const response = await fetch(`${basePath}/transcript.csv`);
      if (!response.ok) {
        throw new Error("Failed to load transcript");
      }
      const csvText = await response.text();
      return parseTranscriptCsv(csvText);
    },
    enabled: !!recordingPath,
    // Keep data fresh for 10 minutes - these files don't change during a session
    staleTime: 10 * 60 * 1000,
    // Keep cached data for 30 minutes
    gcTime: 30 * 60 * 1000,
  });
}

// Fetch chapters data for a recording
export function useChapters(recordingPath: string): UseQueryResult<ChaptersData, Error> {
  const basePath = getRecordingBasePath(recordingPath);

  return useQuery<ChaptersData>({
    queryKey: ["recording", recordingPath, "chapters"],
    queryFn: async () => {
      const response = await fetch(`${basePath}/chapters.json`);
      if (!response.ok) {
        throw new Error("Failed to load chapters");
      }
      return response.json();
    },
    enabled: !!recordingPath,
    // Keep data fresh for 10 minutes - these files don't change during a session
    staleTime: 10 * 60 * 1000,
    // Keep cached data for 30 minutes
    gcTime: 30 * 60 * 1000,
  });
}

// Fetch alternate tellings data (only for memoirs)
export function useAlternateTellings(
  recordingPath: string
): UseQueryResult<AlternateTellingsData, Error> {
  const isMemoir = isMemoirRecording(recordingPath);

  return useQuery<AlternateTellingsData>({
    queryKey: ["recording", "memoirs", "alternateTellings"],
    queryFn: async () => {
      const response = await fetch("/recordings/memoirs/alternate_tellings.json");
      if (!response.ok) {
        throw new Error("Failed to load alternate tellings");
      }
      return response.json();
    },
    enabled: isMemoir,
    // Keep data fresh for 10 minutes - these files don't change during a session
    staleTime: 10 * 60 * 1000,
    // Keep cached data for 30 minutes
    gcTime: 30 * 60 * 1000,
  });
}

// Fetch photos data (global photos.json)
export function usePhotos(): UseQueryResult<PhotosData, Error> {
  return useQuery<PhotosData>({
    queryKey: ["photos"],
    queryFn: async () => {
      const response = await fetch("/photos.json");
      if (!response.ok) {
        throw new Error("Failed to load photos");
      }
      return response.json();
    },
    // Keep data fresh for 10 minutes - these files don't change during a session
    staleTime: 10 * 60 * 1000,
    // Keep cached data for 30 minutes
    gcTime: 30 * 60 * 1000,
  });
}

// Fetch videos data (global videos.json)
export function useVideos(): UseQueryResult<VideosData, Error> {
  return useQuery<VideosData>({
    queryKey: ["videos"],
    queryFn: async () => {
      const response = await fetch("/videos.json");
      if (!response.ok) {
        throw new Error("Failed to load videos");
      }
      return response.json();
    },
    // Keep data fresh for 10 minutes - these files don't change during a session
    staleTime: 10 * 60 * 1000,
    // Keep cached data for 30 minutes
    gcTime: 30 * 60 * 1000,
  });
}

// Fetch media placements for a recording
export function useMediaPlacements(
  recordingPath: string
): UseQueryResult<MediaPlacementData, Error> {
  const basePath = getRecordingBasePath(recordingPath);

  return useQuery<MediaPlacementData>({
    queryKey: ["recording", recordingPath, "mediaPlacements"],
    queryFn: async () => {
      const response = await fetch(`${basePath}/mediaPlacement.json`);
      if (!response.ok) {
        // Return empty placements if file doesn't exist
        if (response.status === 404) {
          return { placements: [] };
        }
        throw new Error("Failed to load media placements");
      }
      return response.json();
    },
    enabled: !!recordingPath,
    // Keep data fresh for 10 minutes - these files don't change during a session
    staleTime: 10 * 60 * 1000,
    // Keep cached data for 30 minutes
    gcTime: 30 * 60 * 1000,
  });
}

// Derive peaks.js regions from chapters
export function useRegions(recordingPath: string): {
  data: PeaksRegion[] | undefined;
  isLoading: boolean;
  error: Error | null;
} {
  const { data: chaptersData, isLoading, error } = useChapters(recordingPath);

  const data = useMemo(() => {
    if (!chaptersData?.chapters) return undefined;
    const chapters = chaptersData.chapters;
    return chapters.map((chapter, index) => {
      // endTime is the start of the next chapter, or a large value for the last chapter
      const endTime =
        index < chapters.length - 1 ? chapters[index + 1].startTime : chapter.startTime + 3600; // 1 hour fallback for last chapter
      return {
        id: `chapter-${index}`,
        startTime: chapter.startTime,
        endTime,
        labelText: chapter.title,
        color: REGION_COLOR,
      };
    });
  }, [chaptersData]);

  return { data, isLoading, error };
}

// Get audio URL - returns enhanced if available, otherwise original
export function getAudioUrl(recordingPath: string, hasEnhancedAudio: boolean): string {
  const audioBasePath = `/static_assets/audio/${recordingPath}`;
  return hasEnhancedAudio
    ? `${audioBasePath}/audio_enhanced.mp3`
    : `${audioBasePath}/audio_original.mp3`;
}

// Get original audio URL (non-enhanced version) - only valid if hasEnhancedAudio is true
export function getOriginalAudioUrl(recordingPath: string): string {
  return `/static_assets/audio/${recordingPath}/audio_original.mp3`;
}

// Get waveform data URL
export function getWaveformDataUrl(recordingPath: string): string {
  return `/static_assets/audio/${recordingPath}/waveform.json`;
}

// Comprehensive hook that combines all data fetching for a recording
export function useRecordingData(
  recordingPath: string,
  hasEnhancedAudio: boolean = false
): {
  transcript: UseQueryResult<TranscriptData, Error>;
  chapters: UseQueryResult<ChaptersData, Error>;
  alternateTellings: UseQueryResult<AlternateTellingsData, Error>;
  photos: UseQueryResult<PhotosData, Error>;
  videos: UseQueryResult<VideosData, Error>;
  mediaPlacements: UseQueryResult<MediaPlacementData, Error>;
  regions: { data: PeaksRegion[] | undefined; isLoading: boolean; error: Error | null };
  isLoading: boolean;
  hasError: boolean;
  refetchAll: () => Promise<void>;
  urls: {
    audio: string;
    originalAudio: string | undefined;
    waveform: string;
  };
  isMemoir: boolean;
} {
  const transcript = useTranscript(recordingPath);
  const chapters = useChapters(recordingPath);
  const alternateTellings = useAlternateTellings(recordingPath);
  const photos = usePhotos();
  const videos = useVideos();
  const mediaPlacements = useMediaPlacements(recordingPath);
  const regions = useRegions(recordingPath);

  const isLoading =
    transcript.isLoading || chapters.isLoading || regions.isLoading || alternateTellings.isLoading;

  // Only show error if we have an error AND don't have cached data
  // This prevents the UI from crashing if a transient error occurs after data was loaded
  const hasError = (!!transcript.error && !transcript.data) || (!!chapters.error && !chapters.data);

  const refetchAll = async () => {
    await Promise.all([
      transcript.refetch(),
      chapters.refetch(),
      alternateTellings.refetch(),
      photos.refetch(),
      videos.refetch(),
      mediaPlacements.refetch(),
    ]);
  };

  const urls = {
    audio: getAudioUrl(recordingPath, hasEnhancedAudio),
    originalAudio: hasEnhancedAudio ? getOriginalAudioUrl(recordingPath) : undefined,
    waveform: getWaveformDataUrl(recordingPath),
  };

  return {
    transcript,
    chapters,
    alternateTellings,
    photos,
    videos,
    mediaPlacements,
    regions,
    isLoading,
    hasError,
    refetchAll,
    urls,
    isMemoir: isMemoirRecording(recordingPath),
  };
}
