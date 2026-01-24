import { useState, useCallback, useMemo, useEffect, useRef } from "react";
import { Link, useParams, Navigate, useSearchParams } from "react-router-dom";
import { AudioPlayer, usePeaksSeek } from "../components/AudioPlayer/AudioPlayer";
import { Chapters } from "../components/Chapters/Chapters";
import { Transcript } from "../components/Transcript/Transcript";
import { ResizablePanels } from "../components/ResizablePanels/ResizablePanels";
import { useRecordingData } from "../hooks/useRecordingData";
import {
  usePlaybackProgress,
  formatProgressTime,
  formatTimeSince,
} from "../hooks/usePlaybackProgress";
import { getRecordingById, getRandomBackgroundImage } from "../config/recordings";
import styles from "./RecordingPlayer.module.css";
import { PeaksInstance } from "peaks.js";

function RecordingPlayer(): React.ReactElement {
  const { recordingId } = useParams<{ recordingId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const [currentTime, setCurrentTime] = useState(0);
  // Track which recording the player is ready for (null = not ready)
  const [readyForRecordingId, setReadyForRecordingId] = useState<string | null>(null);
  const pendingSeekTime = useRef<number | null>(null);
  const peaksInstanceRef = useRef<PeaksInstance | null>(null);
  // Track chapters panel collapse state on mobile
  const [chaptersExpanded, setChaptersExpanded] = useState(false);

  // Player is ready only if it's ready for the CURRENT recording
  const isPlayerReady = readyForRecordingId === recordingId;

  // Track audio duration for progress saving
  const [audioDuration, setAudioDuration] = useState(0);
  // Whether the user has dismissed the resume banner for this session
  const [resumeDismissed, setResumeDismissed] = useState(false);

  // Playback progress (bookmarking)
  const { savedProgress, saveProgress, clearProgress, hasSavedProgress, progressPercentage } =
    usePlaybackProgress(recordingId);

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

  // Extract chapters array for convenience
  const chapters = chaptersQuery.data?.chapters;

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
  const handleTimeUpdate = useCallback(
    (time: number) => {
      setCurrentTime(time);
      // Save progress periodically (the hook throttles this internally)
      if (audioDuration > 0) {
        saveProgress(time, audioDuration);
      }
    },
    [audioDuration, saveProgress]
  );

  // Handle duration change from audio player
  const handleDurationChange = useCallback((duration: number) => {
    setAudioDuration(duration);
  }, []);

  // Handle player ready - mark which recording is now ready
  const handlePlayerReady = useCallback(
    (peaksInstance: PeaksInstance) => {
      setReadyForRecordingId(recordingId ?? null);
      peaksInstanceRef.current = peaksInstance;
    },
    [recordingId]
  );

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

  // Handle resume button click
  const handleResume = useCallback(() => {
    if (savedProgress) {
      seekTo(savedProgress.time);
      setResumeDismissed(true);
      // Start playing after seeking
      setTimeout(() => {
        peaksInstanceRef.current?.player.play();
      }, 100);
    }
  }, [savedProgress, seekTo]);

  // Handle dismiss resume banner
  const handleDismissResume = useCallback(() => {
    setResumeDismissed(true);
  }, []);

  // Handle start from beginning
  const handleStartFromBeginning = useCallback(() => {
    clearProgress();
    setResumeDismissed(true);
    seekTo(0);
  }, [clearProgress, seekTo]);

  // Toggle chapters panel on mobile
  const toggleChapters = useCallback(() => {
    setChaptersExpanded((prev) => !prev);
  }, []);

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
      <Link to="/" className={styles.backButton} aria-label="Back to home">
        ←<span className={styles.backButtonText}> Back</span>
      </Link>
      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <h1 className={styles.title}>
            <Link to="/">Linden Hilary Achen - {recordingConfig.title}</Link>
            <span
              className={`${styles.categoryBadge} ${styles[`badge${recordingConfig.category.charAt(0).toUpperCase() + recordingConfig.category.slice(1)}`]}`}
            >
              {recordingConfig.categoryLabel}
            </span>
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
            onDurationChange={handleDurationChange}
            onReady={handlePlayerReady}
            onReload={refetchAll}
          />

          {/* Resume banner - show when there's saved progress and player is ready */}
          {isPlayerReady && hasSavedProgress && !resumeDismissed && savedProgress && (
            <div className={styles.resumeBanner}>
              <div className={styles.resumeInfo}>
                <span className={styles.resumeIcon}>📍</span>
                <span className={styles.resumeText}>
                  You left off at <strong>{formatProgressTime(savedProgress.time)}</strong>
                  {progressPercentage !== null && (
                    <span className={styles.resumeProgress}> ({progressPercentage}% complete)</span>
                  )}
                  <span className={styles.resumeTime}>
                    {" "}
                    • {formatTimeSince(savedProgress.savedAt)}
                  </span>
                </span>
              </div>
              <div className={styles.resumeActions}>
                <button type="button" className={styles.resumeButton} onClick={handleResume}>
                  Resume
                </button>
                <button
                  type="button"
                  className={styles.resumeStartOver}
                  onClick={handleStartFromBeginning}
                >
                  Start Over
                </button>
                <button
                  type="button"
                  className={styles.resumeDismiss}
                  onClick={handleDismissResume}
                  aria-label="Dismiss"
                >
                  ✕
                </button>
              </div>
            </div>
          )}

          {!isPlayerReady && !isLoading && (
            <div className={styles.playHint}>
              <span className={styles.playIcon}>▶️</span>
              <span>Press play to begin listening to Grandpa&apos;s words</span>
            </div>
          )}
        </section>

        {/* Content with resizable panels: TOC and Transcript */}
        <ResizablePanels
          chaptersExpanded={chaptersExpanded}
          onToggleChapters={toggleChapters}
          leftPanel={
            chapters && chapters.length > 0 ? (
              <Chapters
                chapters={chapters}
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
            )
          }
          rightPanel={
            transcript.data && chapters ? (
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
            )
          }
        />
      </main>

      {/* Footer */}
      <footer className={styles.footer}>
        <p>Made with ❤️ to preserve and share Grandpa&apos;s memories</p>
      </footer>
    </div>
  );
}

export default RecordingPlayer;
