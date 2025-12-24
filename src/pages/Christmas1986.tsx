import { useState, useCallback, useMemo } from "react";
import { AudioPlayer, usePeaksSeek } from "../components/AudioPlayer/AudioPlayer";
import { TableOfContents } from "../components/TableOfContents/TableOfContents";
import { Transcript } from "../components/Transcript/Transcript";
import {
  useTranscript,
  useTableOfContents,
  useRegions,
  getAudioUrl,
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
  } = useTranscript();
  const { data: toc, isLoading: tocLoading, error: tocError } = useTableOfContents();
  const { data: regions, isLoading: regionsLoading } = useRegions();

  // Get seek function from peaks.js
  const seekTo = usePeaksSeek();

  // Handle time updates from audio player
  const handleTimeUpdate = useCallback((time: number) => {
    setCurrentTime(time);
  }, []);

  // Handle player ready
  const handlePlayerReady = useCallback(() => {
    setIsPlayerReady(true);
  }, []);

  // Handle TOC entry click
  const handleTocClick = useCallback(
    (entry: TableOfContentsEntry) => {
      seekTo(entry.startTime);
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
      const chapter = toc?.find((t) => `chapter-${t.id}` === regionId);
      if (chapter) {
        seekTo(chapter.startTime);
      }
    },
    [toc, seekTo]
  );

  // Calculate the current chapter ID based on playback time
  const currentChapterId = useMemo(() => {
    if (!toc || toc.length === 0) return null;

    // Find the chapter that contains the current time
    for (let i = toc.length - 1; i >= 0; i--) {
      if (currentTime >= toc[i].startTime) {
        return `chapter-${toc[i].id}`;
      }
    }
    return toc.length > 0 ? `chapter-${toc[0].id}` : null;
  }, [currentTime, toc]);

  // Loading state
  const isLoading = transcriptLoading || tocLoading || regionsLoading;

  // Error state
  const hasError = transcriptError || tocError;

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
            <span className={styles.titleIcon}>🎄</span>
            Christmas 1986
          </h1>
          <p className={styles.subtitle}>
            A letter from Grandpa to his son, recorded during the holiday season
          </p>
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
            waveformDataUrl={getWaveformDataUrl()}
            regions={regions || []}
            currentChapterId={currentChapterId}
            onTimeUpdate={handleTimeUpdate}
            onRegionClick={handleRegionClick}
            onReady={handlePlayerReady}
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
            {toc && toc.length > 0 ? (
              <TableOfContents
                entries={toc}
                currentTime={currentTime}
                onEntryClick={handleTocClick}
              />
            ) : (
              <div className={styles.placeholderBox}>
                <h2>📖 Table of Contents</h2>
                <p>Chapter information will appear here after processing.</p>
              </div>
            )}
          </aside>

          {/* Transcript */}
          <section className={styles.transcriptSection}>
            {transcript && toc ? (
              <Transcript
                segments={transcript.segments}
                chapters={toc}
                currentTime={currentTime}
                onSegmentClick={handleWordClick}
              />
            ) : (
              <div className={styles.placeholderBox}>
                <h2>📝 Full Transcript</h2>
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
