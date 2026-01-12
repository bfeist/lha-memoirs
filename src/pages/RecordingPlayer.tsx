import { useState, useCallback, useMemo, useEffect, useRef } from "react";
import { Link, useParams, Navigate, useSearchParams } from "react-router-dom";
import { AudioPlayer, usePeaksSeek } from "../components/AudioPlayer/AudioPlayer";
import { Chapters } from "../components/Chapters/Chapters";
import { Transcript } from "../components/Transcript/Transcript";
import { useRecordingData } from "../hooks/useRecordingData";
import { getRecordingById, getRandomBackgroundImage } from "../config/recordings";
import styles from "./RecordingPlayer.module.css";

function RecordingPlayer(): React.ReactElement {
  const { recordingId } = useParams<{ recordingId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [currentTime, setCurrentTime] = useState(0);
  // Track which recording the player is ready for (null = not ready)
  const [readyForRecordingId, setReadyForRecordingId] = useState<string | null>(null);
  const pendingSeekTime = useRef<number | null>(null);

  // Player is ready only if it's ready for the CURRENT recording
  const isPlayerReady = readyForRecordingId === recordingId;

  // Capture the time parameter immediately on mount or when URL changes
  useEffect(() => {
    const timeParam = searchParams.get("t");
    if (timeParam) {
      const time = parseFloat(timeParam);
      if (!isNaN(time) && time > 0) {
        pendingSeekTime.current = time;
        // Clear the time parameter from URL immediately
        searchParams.delete("t");
        setSearchParams(searchParams, { replace: true });
      }
    }
  }, [searchParams, setSearchParams]);

  // Get recording config
  const recordingConfig = recordingId ? getRecordingById(recordingId) : undefined;

  // Key for AudioPlayer to force remount when recording changes
  const playerKey = recordingId ?? "default";

  // Pick a random background image at component load time
  const backgroundImage = useMemo(
    () => (recordingConfig ? getRandomBackgroundImage(recordingConfig) : "/photos/P1010034.jpg"),
    [recordingConfig]
  );

  // Fetch all data using the generic hook
  const {
    transcript,
    chapters: chaptersQuery,
    alternateTellings,
    regions,
    isLoading,
    hasError,
    refetchAll,
    urls,
    isMemoir,
  } = useRecordingData(recordingConfig?.path ?? "", recordingConfig?.hasEnhancedAudio ?? false);

  // Extract chapters and stories arrays for convenience
  const chapters = chaptersQuery.data?.chapters;
  const stories = chaptersQuery.data?.stories;

  // Get seek function from peaks.js
  const seekTo = usePeaksSeek();

  // Perform pending seek when player becomes ready
  useEffect(() => {
    if (isPlayerReady && pendingSeekTime.current !== null) {
      const timeToSeek = pendingSeekTime.current;
      pendingSeekTime.current = null;
      // Small delay to ensure peaks.js is fully initialized
      setTimeout(() => {
        seekTo(timeToSeek);
      }, 100);
    }
  }, [isPlayerReady, seekTo]);

  // Handle time updates from audio player
  const handleTimeUpdate = useCallback((time: number) => {
    setCurrentTime(time);
  }, []);

  // Handle player ready - mark which recording is now ready
  const handlePlayerReady = useCallback(() => {
    setReadyForRecordingId(recordingId ?? null);
  }, [recordingId]);

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

  // Redirect if recording not found
  if (!recordingConfig) {
    return <Navigate to="/" replace />;
  }

  if (hasError) {
    return (
      <div
        className={styles.container}
        style={{ "--background-image": `url(${backgroundImage})` } as React.CSSProperties}
      >
        <div className={styles.error}>
          <h1>❌ Unable to Load Recording</h1>
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
              Linden Hilary Achen - {recordingConfig.title}{" "}
              <span className={styles.titleIcon}>{recordingConfig.icon}</span>
            </Link>
          </h1>
          <p className={styles.subtitle}>{recordingConfig.subtitle}</p>
        </div>
      </header>

      {/* Loading indicator */}
      {isLoading && (
        <div className={styles.loadingOverlay}>
          <div className={styles.loadingSpinner} />
          <p>Loading recording data...</p>
        </div>
      )}

      {/* Main content */}
      <main className={styles.main}>
        {/* Audio Player Section */}
        <section className={styles.playerSection}>
          <AudioPlayer
            key={playerKey}
            audioUrl={urls.audio}
            originalAudioUrl={urls.originalAudio}
            waveformDataUrl={urls.waveform}
            regions={regions.data || []}
            currentChapterId={currentChapterId}
            onTimeUpdate={handleTimeUpdate}
            onRegionClick={handleRegionClick}
            onReady={handlePlayerReady}
            onReload={refetchAll}
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
                stories={stories}
                currentTime={currentTime}
                onChapterClick={handleChapterClick}
                alternateTellings={isMemoir ? alternateTellings.data?.alternateTellings : undefined}
                recordingPath={recordingConfig?.path}
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
            {transcript.data && chapters ? (
              <Transcript
                segments={transcript.data.segments}
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

export default RecordingPlayer;
