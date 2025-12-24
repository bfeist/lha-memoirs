import styles from "./TableOfContents.module.css";

interface TableOfContentsProps {
  entries: TableOfContentsEntry[];
  currentTime: number;
  onEntryClick: (entry: TableOfContentsEntry) => void;
}

export function TableOfContents({
  entries,
  currentTime,
  onEntryClick,
}: TableOfContentsProps): React.ReactElement {
  // Determine which entry is currently active
  const getCurrentEntryId = (): number | null => {
    for (let i = entries.length - 1; i >= 0; i--) {
      if (currentTime >= entries[i].startTime) {
        return entries[i].id;
      }
    }
    return entries.length > 0 ? entries[0].id : null;
  };

  const currentEntryId = getCurrentEntryId();

  return (
    <div className={styles.container}>
      <h2 className={styles.heading}>Chapters</h2>

      <p className={styles.hint}>Click a chapter to jump to that section</p>

      <nav className={styles.tocList} aria-label="Table of Contents">
        {entries.map((entry, index) => {
          const isActive = entry.id === currentEntryId;
          const isPast = entry.startTime < currentTime && !isActive;

          return (
            <button
              key={entry.id}
              onClick={() => onEntryClick(entry)}
              className={`${styles.tocItem} ${isActive ? styles.active : ""} ${isPast ? styles.past : ""}`}
              aria-current={isActive ? "true" : undefined}
            >
              <span className={styles.chapterNumber}>{index + 1}</span>

              <div className={styles.chapterInfo}>
                <span className={styles.chapterTitle}>{entry.title}</span>
                {entry.description && (
                  <span className={styles.chapterDescription}>{entry.description}</span>
                )}
              </div>

              <span className={styles.timestamp}>{entry.formattedTime}</span>
            </button>
          );
        })}
      </nav>
    </div>
  );
}
