import { useEffect } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faStar, faXmark } from "@fortawesome/free-solid-svg-icons";
import { faGithub } from "@fortawesome/free-brands-svg-icons";
import { useChangelog } from "../../hooks/useChangelog";
import styles from "./WhatsNew.module.css";

const WhatsNew: React.FC<{
  isOpen: boolean;
  onClose: () => void;
}> = ({ isOpen, onClose }) => {
  const { data: changelog, isLoading, error } = useChangelog();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const formatDate = (dateStr: string): string => {
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  };

  return (
    <div className={styles.overlay}>
      {/* Backdrop button for closing - accessible click-to-close */}
      <button
        type="button"
        className={styles.backdrop}
        onClick={onClose}
        aria-label="Close dialog"
      />
      <div
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="whats-new-title"
      >
        <div className={styles.header}>
          <h2 id="whats-new-title" className={styles.title}>
            <FontAwesomeIcon icon={faStar} className={styles.titleIcon} />
            What&apos;s New
          </h2>
          <div className={styles.headerActions}>
            <a
              href="https://github.com/bfeist/lha-memoirs"
              target="_blank"
              rel="noopener noreferrer"
              className={styles.githubLink}
            >
              <FontAwesomeIcon icon={faGithub} />
              <span>View on GitHub</span>
            </a>
            <button className={styles.closeButton} onClick={onClose} aria-label="Close">
              <FontAwesomeIcon icon={faXmark} />
            </button>
          </div>
        </div>

        <div className={styles.content}>
          {isLoading && <div className={styles.loading}>Loading updates...</div>}
          {error && <div className={styles.error}>{error.message}</div>}
          {changelog && changelog.commits.length === 0 && (
            <div className={styles.empty}>No updates available yet.</div>
          )}
          {changelog && changelog.commits.length > 0 && (
            <div className={styles.commitList}>
              {changelog.commits.map((commit) => (
                <div key={commit.hash} className={styles.commitItem}>
                  <span className={styles.commitDate}>{formatDate(commit.date)}</span>
                  <span className={styles.commitMessage}>{commit.message}</span>
                  <span className={styles.commitHash}>{commit.hash}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {changelog && (
          <div className={styles.generatedAt}>
            Last updated: {new Date(changelog.generatedAt).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  );
};

export default WhatsNew;
