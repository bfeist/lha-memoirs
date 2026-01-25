// Global type definitions for memoir audio data

interface TranscriptSegment {
  start: number;
  end: number;
  text: string;
}

interface TranscriptData {
  segments: TranscriptSegment[];
}

interface Chapter {
  title: string;
  startTime: number;
  description: string;
  /** If true, this is a minor chapter (sub-section/story within a parent chapter) */
  minor?: boolean;
}

interface ChaptersData {
  chapters: Chapter[];
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
  id: string; // "chapter-0" or "chapter-5" (for minor chapters, previously "story-5")
  type: "chapter";
  startTime: number;
  title: string;
  minor?: boolean;
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

// Photo data from photos.json
interface Photo {
  filename: string;
  caption: string;
  location: string;
  date: string;
  credit: string;
}

interface PhotosData {
  photos: Photo[];
}

// Media placement for inline transcript media
interface MediaPlacement {
  /** Seconds marker where the media should be placed */
  seconds: number;
  /** Type of media - 'photo' for photo slider, 'video' for video player */
  type: "photo" | "video";
  /** Array of filenames (for photos) - references filename in photos.json */
  filenames?: string[];
  /** Video filename (for future video support) */
  videoFilename?: string;
}

interface MediaPlacementData {
  placements: MediaPlacement[];
}
