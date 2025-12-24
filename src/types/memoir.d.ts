// Global type definitions for memoir audio data

interface TranscriptWord {
  word: string;
  start: number;
  end: number;
  segment_id: number;
}

interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

interface TranscriptData {
  full_text?: string; // Optional - stripped after generation to reduce file size
  segments: TranscriptSegment[];
  words: TranscriptWord[];
  language: string;
  duration: number;
}

interface Chapter {
  id: number;
  title: string;
  startTime: number;
  description: string;
}

interface ChaptersData {
  chapters: Chapter[];
  summary: string;
}

interface TableOfContentsEntry {
  id: number;
  title: string;
  startTime: number;
  formattedTime: string;
  description: string;
}

interface PeaksRegion {
  id: string;
  startTime: number;
  endTime: number;
  labelText: string;
  color: string;
}

interface WaveformData {
  version: number;
  channels: number;
  sample_rate: number;
  samples_per_pixel: number;
  bits: number;
  length: number;
  data: number[];
}
