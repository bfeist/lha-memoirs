// Recording configuration for all available audio recordings

export interface RecordingConfig {
  id: string;
  path: string; // Path relative to /recordings/
  title: string;
  subtitle: string;
  icon: string;
  backgroundImages: string[];
  category: "recording" | "memoir";
  hasEnhancedAudio: boolean; // Whether this recording has both original and enhanced audio files
}

// All available recordings
export const RECORDINGS: RecordingConfig[] = [
  {
    id: "christmas1986",
    path: "christmas1986",
    title: "Christmas 1986",
    subtitle: "A letter to his son, Norman Achen. Recorded on November 26, 1986.",
    icon: "🎄",
    backgroundImages: ["/photos/P1010033.jpg", "/photos/P1010034.jpg", "/photos/P1010038.jpg"],
    category: "recording",
    hasEnhancedAudio: true,
  },
  {
    id: "glynn_interview",
    path: "glynn_interview",
    title: "Glynn Interview",
    subtitle: "An interview with Glynn about family history and life experiences.",
    icon: "🎙️",
    backgroundImages: ["/photos/P1010033.jpg", "/photos/P1010034.jpg"],
    category: "recording",
    hasEnhancedAudio: false,
  },
  {
    id: "lha_sr_hilary",
    path: "LHA_Sr.Hilary",
    title: "Sr. Hilary Recording",
    subtitle: "Recordings with Sister Hilary discussing family and career.",
    icon: "📼",
    backgroundImages: ["/photos/P1010033.jpg", "/photos/P1010034.jpg"],
    category: "recording",
    hasEnhancedAudio: false,
  },
  {
    id: "tibbits_cd",
    path: "tibbits_cd",
    title: "Tibbits CD",
    subtitle: "Stories and recordings from a CD created by Leslie Feist.",
    icon: "💿",
    backgroundImages: ["/photos/P1010033.jpg", "/photos/P1010034.jpg"],
    category: "recording",
    hasEnhancedAudio: false,
  },
  // Memoirs (nested under memoirs/)
  {
    id: "memoirs_main",
    path: "memoirs/TDK_D60_edited_through_air",
    title: "Memoirs",
    subtitle: "Lindy Achen's voice memoirs about his working life.",
    icon: "📕",
    backgroundImages: ["/photos/P1010033.jpg", "/photos/P1010034.jpg"],
    category: "memoir",
    hasEnhancedAudio: false,
  },
  {
    id: "memoirs_draft_telling",
    path: "memoirs/Norm_red",
    title: "Memoirs - Draft Telling",
    subtitle:
      "A draft recording of Lindy Achen's voice memoirs, recorded before the finished product.",
    icon: "📗",
    backgroundImages: ["/photos/P1010033.jpg", "/photos/P1010034.jpg"],
    category: "memoir",
    hasEnhancedAudio: false,
  },
];

// Get recordings by category
export function getRecordingsByCategory(category: "recording" | "memoir"): RecordingConfig[] {
  return RECORDINGS.filter((r) => r.category === category);
}

// Find a recording by its ID
export function getRecordingById(id: string): RecordingConfig | undefined {
  return RECORDINGS.find((r) => r.id === id);
}

// Find a recording by its path
export function getRecordingByPath(path: string): RecordingConfig | undefined {
  return RECORDINGS.find((r) => r.path === path);
}

// Get a random background image for a recording
export function getRandomBackgroundImage(recording: RecordingConfig): string {
  const images = recording.backgroundImages;
  return images[Math.floor(Math.random() * images.length)];
}
