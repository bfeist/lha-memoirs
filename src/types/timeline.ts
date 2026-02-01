// Timeline data types

export interface TimelineExcerpt {
  recordingId: string;
  recordingTitle: string;
  audioUrl: string;
  text: string;
  startTime: number;
  endTime: number;
}

export interface TimelineEntry {
  year_start: number;
  year_end: number;
  title: string;
  description: string;
  age_start: number;
  age_end: number;
  excerpts: TimelineExcerpt[];
}

export interface TimelineData {
  generatedAt: string;
  timelineStart: number;
  timelineEnd: number;
  entries: TimelineEntry[];
}
