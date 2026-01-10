import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useMemo } from "react";

const AUDIO_BASE_PATH = "/recordings/christmas1986";

// Default region color for waveform segments
const REGION_COLOR = "rgba(100, 149, 237, 0.3)";

// Format seconds as MM:SS
export function formatTime(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
}

// Fetch transcript data
export function useTranscript(): UseQueryResult<TranscriptData, Error> {
  return useQuery<TranscriptData>({
    queryKey: ["christmas1986", "transcript"],
    queryFn: async () => {
      const response = await fetch(`${AUDIO_BASE_PATH}/transcript.json`);
      if (!response.ok) {
        throw new Error("Failed to load transcript");
      }
      return response.json();
    },
  });
}

// Fetch chapters data
export function useChapters(): UseQueryResult<ChaptersData, Error> {
  return useQuery<ChaptersData>({
    queryKey: ["christmas1986", "chapters"],
    queryFn: async () => {
      const response = await fetch(`${AUDIO_BASE_PATH}/chapters.json`);
      if (!response.ok) {
        throw new Error("Failed to load chapters");
      }
      return response.json();
    },
  });
}

// Derive peaks.js regions from chapters
export function useRegions(): {
  data: PeaksRegion[] | undefined;
  isLoading: boolean;
  error: Error | null;
} {
  const { data: chaptersData, isLoading, error } = useChapters();

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

// Get audio URL (enhanced version)
export function getAudioUrl(): string {
  return `${AUDIO_BASE_PATH}/audio.mp3`;
}

// Get original audio URL (non-enhanced version)
export function getOriginalAudioUrl(): string {
  return `${AUDIO_BASE_PATH}/audio_original.mp3`;
}

// Get waveform data URL
export function getWaveformDataUrl(): string {
  // Use JSON format as it's more reliable than binary .dat
  return `${AUDIO_BASE_PATH}/waveform.json`;
}

// Get waveform JSON URL (fallback)
export function getWaveformJsonUrl(): string {
  return `${AUDIO_BASE_PATH}/waveform.json`;
}
