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
  uuid?: string;
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

// New format for alternate tellings v2.0
interface AlternateRecordingSegment {
  startTime: number;
  endTime: number;
  preview: string;
}

interface AlternateTelling {
  topic: string;
  confidence: "HIGH" | "MEDIUM" | "LOW";
  score: number;
  Norm_red?: AlternateRecordingSegment;
  TDK_D60_edited_through_air?: AlternateRecordingSegment;
}

interface AlternateTellingsData {
  version: string;
  description: string;
  primaryRecording: string;
  secondaryRecording: string;
  matchingMethod: string;
  windowConfig?: {
    duration: number;
    overlap: number;
  };
  alternateTellings: AlternateTelling[];
  stats?: {
    totalMatches: number;
    highConfidence: number;
    mediumConfidence: number;
  };
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

// Video data from videos.json
interface Video {
  filename: string;
  caption: string;
  location: string;
  date: string;
  credit: string;
}

interface VideosData {
  videos: Video[];
}

// Media placement for inline transcript media
interface MediaPlacement {
  /** Seconds marker where the media should be placed */
  seconds: number;
  /** Type of media - 'photo' for photo slider, 'video' for video player */
  type: "photo" | "video";
  /** Array of filenames (for photos) - references filename in photos.json */
  filenames?: string[];
  /** Start time in seconds for video loop (optional, defaults to 0) */
  start?: number;
  /** End time in seconds for video loop (optional, defaults to video end) */
  end?: number;
}

interface MediaPlacementData {
  placements: MediaPlacement[];
}
