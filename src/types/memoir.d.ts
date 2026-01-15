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
  title: string;
  startTime: number;
  description: string;
}

interface Story {
  id: string;
  title: string;
  startTime: number;
  description: string;
  chapterIndex: number;
}

interface ChaptersData {
  chapters: Chapter[];
  stories?: Story[];
  summary: string;
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

interface AlternateSegmentRef {
  id: string; // "chapter-0" or "story-5"
  type: "chapter" | "story";
  startTime: number;
  title: string;
}

// Legacy format (kept for backwards compatibility)
interface AlternateStoryRef {
  storyId: string;
  startTime: number;
  title: string;
}

interface AlternateTelling {
  topic: string;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  [recordingKey: string]: string | AlternateSegmentRef | AlternateStoryRef;
}

interface AlternateTellingsData {
  primaryRecording: string;
  secondaryRecording: string;
  description: string;
  alternateTellings: AlternateTelling[];
}
