import { useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { AudioPlayer, usePeaksSeek } from "../components/AudioPlayer/AudioPlayer";
import { Chapters } from "../components/Chapters/Chapters";
import { Transcript } from "../components/Transcript/Transcript";
import {
  useTranscript,
  useChapters,
  useRegions,
  getAudioUrl,
  getOriginalAudioUrl,
  getWaveformDataUrl,
} from "../hooks/useChristmas1986Data";
import styles from "./Christmas1986.module.css";

const BACKGROUND_IMAGES = ["/photos/P1010033.jpg", "/photos/P1010034.jpg", "/photos/P1010038.jpg"];

// Pick a random background image at module load time
const backgroundImage = BACKGROUND_IMAGES[Math.floor(Math.random() * BACKGROUND_IMAGES.length)];

function Christmas1986(): React.ReactElement {
  const [currentTime, setCurrentTime] = useState(0);
  const [isPlayerReady, setIsPlayerReady] = useState(false);

  // Fetch all data
  const {
    data: transcript,
    isLoading: transcriptLoading,
    error: transcriptError,
    refetch: refetchTranscript,
  } = useTranscript();
  const {
    data: chaptersData,
    isLoading: chaptersLoading,
    error: chaptersError,
    refetch: refetchChapters,
  } = useChapters();
  const { data: regions, isLoading: regionsLoading } = useRegions();

  // Extract chapters array for convenience
  const chapters = chaptersData?.chapters;

  // Get seek function from peaks.js
  const seekTo = usePeaksSeek();

  // Handle reload button click
  const handleReloadData = useCallback(async () => {
    await Promise.all([refetchTranscript(), refetchChapters()]);
  }, [refetchTranscript, refetchChapters]);

  // Handle time updates from audio player
  const handleTimeUpdate = useCallback((time: number) => {
    setCurrentTime(time);
  }, []);

  // Handle player ready
  const handlePlayerReady = useCallback(() => {
    setIsPlayerReady(true);
  }, []);

  // Handle TOC entry click
  const handleChapterClick = useCallback(
    (chapter: Chapter) => {
      seekTo(chapter.startTime);
    },
    [seekTo]
  );

  // Handle word click in transcript
  const handleWordClick = useCallback(
    (time: number) => {
      seekTo(time);
    },
    [seekTo]
  );

  // Handle region click
  const handleRegionClick = useCallback(
    (regionId: string) => {
      // regionId is in format "chapter-{index}"
      const match = regionId.match(/^chapter-(\d+)$/);
      if (match && chapters) {
        const index = parseInt(match[1], 10);
        const chapter = chapters[index];
        if (chapter) {
          seekTo(chapter.startTime);
        }
      }
    },
    [chapters, seekTo]
  );

  // Calculate the current chapter ID based on playback time
  const currentChapterId = useMemo(() => {
    if (!chapters || chapters.length === 0) return null;

    // Find the chapter that contains the current time
    for (let i = chapters.length - 1; i >= 0; i--) {
      if (currentTime >= chapters[i].startTime) {
        return `chapter-${i}`;
      }
    }
    return chapters.length > 0 ? `chapter-0` : null;
  }, [currentTime, chapters]);

  // Loading state
  const isLoading = transcriptLoading || chaptersLoading || regionsLoading;

  // Error state
  const hasError = transcriptError || chaptersError;

  if (hasError) {
    return (
      <div
        className={styles.container}
        style={{ "--background-image": `url(${backgroundImage})` } as React.CSSProperties}
      >
        <div className={styles.error}>
          <h1>❌ Unable to Load Memoir</h1>
          <p>
            The audio data files could not be loaded. Make sure you have run the processing scripts
            first.
          </p>
          <div className={styles.errorInstructions}>
            <p>Run these commands in the scripts folder:</p>
            <code>uv run process_all.py</code>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={styles.container}
      style={{ "--background-image": `url(${backgroundImage})` } as React.CSSProperties}
    >
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <h1 className={styles.title}>
            <Link to="/">
              Linden Hilary Achen - Christmas 1986 <span className={styles.titleIcon}>🎄</span>
            </Link>
          </h1>
          <p className={styles.subtitle}>A letter to his son, Norman Achen, November 26, 1986.</p>
        </div>
      </header>

      {/* Loading indicator */}
      {isLoading && (
        <div className={styles.loadingOverlay}>
          <div className={styles.loadingSpinner} />
          <p>Loading memoir data...</p>
        </div>
      )}

      {/* Main content */}
      <main className={styles.main}>
        {/* Audio Player Section */}
        <section className={styles.playerSection}>
          <AudioPlayer
            audioUrl={getAudioUrl()}
            originalAudioUrl={getOriginalAudioUrl()}
            waveformDataUrl={getWaveformDataUrl()}
            regions={regions || []}
            currentChapterId={currentChapterId}
            onTimeUpdate={handleTimeUpdate}
            onRegionClick={handleRegionClick}
            onReady={handlePlayerReady}
            onReload={handleReloadData}
          />

          {!isPlayerReady && !isLoading && (
            <div className={styles.playHint}>
              <span className={styles.playIcon}>▶️</span>
              <span>Press play to begin listening to Grandpa&apos;s words</span>
            </div>
          )}
        </section>

        {/* Content grid: TOC and Transcript side by side */}
        <div className={styles.contentGrid}>
          {/* Table of Contents */}
          <aside className={styles.tocSection}>
            {chapters && chapters.length > 0 ? (
              <Chapters
                chapters={chapters}
                currentTime={currentTime}
                onChapterClick={handleChapterClick}
              />
            ) : (
              <div className={styles.placeholderBox}>
                <h2>Chapters</h2>
                <p>Chapter information will appear here after processing.</p>
              </div>
            )}
          </aside>

          {/* Transcript */}
          <section className={styles.transcriptSection}>
            {transcript && chapters ? (
              <Transcript
                segments={transcript.segments}
                chapters={chapters}
                currentTime={currentTime}
                onSegmentClick={handleWordClick}
              />
            ) : (
              <div className={styles.placeholderBox}>
                <h2>Transcript</h2>
                <p>The transcript will appear here after processing the audio.</p>
              </div>
            )}
          </section>
        </div>
      </main>

      {/* Footer */}
      <footer className={styles.footer}>
        <p>Made with ❤️ to preserve and share Grandpa&apos;s memories</p>
      </footer>
    </div>
  );
}

export default Christmas1986;
