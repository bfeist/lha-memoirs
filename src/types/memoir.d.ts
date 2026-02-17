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
  /** Optional path to an audio file to display as an inline player below the chapter description */
  audioFile?: string;
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

// Alternate tellings format from 05_find_story_overlaps_fast.py
interface AlternateWindow {
  start: number;
  end: number;
  topics: string;
}

interface AlternateTelling {
  norm_window: AlternateWindow;
  tdk_window: AlternateWindow;
  similarity_score: number;
  tfidf_similarity: number;
}

interface AlternateTellingsData {
  generated_at: string;
  algorithm: string;
  settings: {
    window_duration: number;
    window_overlap: number;
    similarity_threshold: number;
    match_threshold: number;
    model: string;
  };
  stats: {
    norm_windows: number;
    tdk_windows: number;
    matches_found: number;
  };
  alt_tellings: AlternateTelling[];
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

// Place data from places.json
interface PlaceMention {
  transcript: string;
  context: string;
  startSecs: number;
  endSecs: number;
}

interface Place {
  name: string;
  geonameid: number;
  latitude: number;
  longitude: number;
  country_code: string;
  admin1_name: string;
  population: number;
  feature_code: string;
  distance_from_regina_km: number;
  confidence: "high" | "medium" | "low";
  needs_review: boolean;
  mentions: PlaceMention[];
}

interface PlacesData {
  metadata: {
    total_places: number;
    last_updated: string;
    reference_point: {
      name: string;
      latitude: number;
      longitude: number;
    };
  };
  places: Place[];
}
