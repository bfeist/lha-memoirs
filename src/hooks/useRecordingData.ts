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

// Fetch transcript data for a recording
export function useTranscript(recordingPath: string): UseQueryResult<TranscriptData, Error> {
  const basePath = getRecordingBasePath(recordingPath);

  return useQuery<TranscriptData>({
    queryKey: ["recording", recordingPath, "transcript"],
    queryFn: async () => {
      const response = await fetch(`${basePath}/transcript.json`);
      if (!response.ok) {
        throw new Error("Failed to load transcript");
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
  const basePath = getRecordingBasePath(recordingPath);
  return hasEnhancedAudio ? `${basePath}/audio_enhanced.mp3` : `${basePath}/audio_original.mp3`;
}

// Get original audio URL (non-enhanced version) - only valid if hasEnhancedAudio is true
export function getOriginalAudioUrl(recordingPath: string): string {
  return `${getRecordingBasePath(recordingPath)}/audio_original.mp3`;
}

// Get waveform data URL
export function getWaveformDataUrl(recordingPath: string): string {
  return `${getRecordingBasePath(recordingPath)}/waveform.json`;
}

// Comprehensive hook that combines all data fetching for a recording
export function useRecordingData(
  recordingPath: string,
  hasEnhancedAudio: boolean = false
): {
  transcript: UseQueryResult<TranscriptData, Error>;
  chapters: UseQueryResult<ChaptersData, Error>;
  alternateTellings: UseQueryResult<AlternateTellingsData, Error>;
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
  const regions = useRegions(recordingPath);

  const isLoading =
    transcript.isLoading || chapters.isLoading || regions.isLoading || alternateTellings.isLoading;

  // Only show error if we have an error AND don't have cached data
  // This prevents the UI from crashing if a transient error occurs after data was loaded
  const hasError = (!!transcript.error && !transcript.data) || (!!chapters.error && !chapters.data);

  const refetchAll = async () => {
    await Promise.all([transcript.refetch(), chapters.refetch(), alternateTellings.refetch()]);
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
    regions,
    isLoading,
    hasError,
    refetchAll,
    urls,
    isMemoir: isMemoirRecording(recordingPath),
  };
}
