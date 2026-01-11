import { formatTime } from "../../hooks/useRecordingData";
import styles from "./Chapters.module.css";

export function Chapters({
  chapters,
  currentTime,
  onChapterClick,
}: {
  chapters: Chapter[];
  currentTime: number;
  onChapterClick: (chapter: Chapter) => void;
}): React.ReactElement {
  // Determine which chapter is currently active
  const getCurrentChapterIndex = (): number | null => {
    for (let i = chapters.length - 1; i >= 0; i--) {
      if (currentTime >= chapters[i].startTime) {
        return i;
      }
    }
    return chapters.length > 0 ? 0 : null;
  };

  const currentChapterIndex = getCurrentChapterIndex();

  return (
    <div className={styles.container}>
      <h2 className={styles.heading}>Chapters</h2>

      <p className={styles.hint}>Click a chapter to jump to that section</p>

      <nav className={styles.tocList} aria-label="Table of Contents">
        {chapters.map((chapter, index) => {
          const isActive = index === currentChapterIndex;
          const isPast = chapter.startTime < currentTime && !isActive;

          return (
            <button
              key={index}
              onClick={() => onChapterClick(chapter)}
              className={`${styles.tocItem} ${isActive ? styles.active : ""} ${isPast ? styles.past : ""}`}
              aria-current={isActive ? "true" : undefined}
            >
              <span className={styles.chapterNumber}>{index + 1}</span>

              <div className={styles.chapterInfo}>
                <span className={styles.chapterTitle}>{chapter.title}</span>
                {chapter.description && (
                  <span className={styles.chapterDescription}>{chapter.description}</span>
                )}
              </div>

              <span className={styles.timestamp}>{formatTime(chapter.startTime)}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
