import { useQuery, type UseQueryResult } from "@tanstack/react-query";

const AUDIO_BASE_PATH = "/audio/christmas1986";

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

// Fetch table of contents
export function useTableOfContents(): UseQueryResult<TableOfContentsEntry[], Error> {
  return useQuery<TableOfContentsEntry[]>({
    queryKey: ["christmas1986", "toc"],
    queryFn: async () => {
      const response = await fetch(`${AUDIO_BASE_PATH}/toc.json`);
      if (!response.ok) {
        throw new Error("Failed to load table of contents");
      }
      return response.json();
    },
  });
}

// Fetch peaks.js regions
export function useRegions(): UseQueryResult<PeaksRegion[], Error> {
  return useQuery<PeaksRegion[]>({
    queryKey: ["christmas1986", "regions"],
    queryFn: async () => {
      const response = await fetch(`${AUDIO_BASE_PATH}/regions.json`);
      if (!response.ok) {
        throw new Error("Failed to load regions");
      }
      return response.json();
    },
  });
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
