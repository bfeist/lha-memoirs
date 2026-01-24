// Recording configuration for all available audio recordings

export interface RecordingConfig {
  id: string;
  path: string; // Path relative to /recordings/
  title: string;
  subtitle: string;
  categoryLabel: string;
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
    categoryLabel: "Letter Recording",
    backgroundImages: ["/photos/P1010033.jpg", "/photos/P1010034.jpg", "/photos/P1010038.jpg"],
    category: "recording",
    hasEnhancedAudio: true,
  },
  {
    id: "glynn_interview",
    path: "glynn_interview",
    title: "Glynn Interview",
    subtitle: "Lindy Achen interviewed by Arlene Glynn about life during the Great Depression.",
    categoryLabel: "Interview",
    backgroundImages: ["/photos/P1010033.jpg", "/photos/P1010034.jpg"],
    category: "recording",
    hasEnhancedAudio: false,
  },
  {
    id: "lha_sr_hilary",
    path: "LHA_Sr.Hilary",
    title: "Sister Hilary Recording",
    subtitle: "Recordings with his older sister, Sister Hilary, discussing family and career.",
    categoryLabel: "Family Recording",
    backgroundImages: ["/photos/P1010033.jpg", "/photos/P1010034.jpg"],
    category: "recording",
    hasEnhancedAudio: false,
  },
  {
    id: "tibbits_cd",
    path: "tibbits_cd",
    title: "Tibbits CD",
    subtitle: "Stories and early Tibbits Rd. audio compiled by his granddaughter, Leslie Feist.",
    categoryLabel: "Audio Collection",
    backgroundImages: ["/photos/P1010033.jpg", "/photos/P1010034.jpg"],
    category: "recording",
    hasEnhancedAudio: false,
  },
  // Memoirs (nested under memoirs/)
  {
    id: "memoirs_main",
    path: "memoirs/Norm_red",
    title: "Memoirs",
    subtitle:
      "Lindy Achen's voice memoirs recounting his life farming on the Canadian Prairies and his work expanding rural electricity across western Canada",
    categoryLabel: "Featured",
    backgroundImages: ["/photos/P1010033.jpg", "/photos/P1010034.jpg"],
    category: "memoir",
    hasEnhancedAudio: false,
  },
  {
    id: "memoirs_draft_telling",
    path: "memoirs/TDK_D60_edited_through_air",
    title: "Memoirs - Draft Telling",
    subtitle:
      "A draft recording of Lindy Achen's voice memoirs, recorded before the finished product.",
    categoryLabel: "Draft",
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
