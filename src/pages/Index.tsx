import { useState } from "react";
import { Link } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faStar } from "@fortawesome/free-solid-svg-icons";
import { getRecordingsByCategory, type RecordingConfig } from "../config/recordings";
import WhatsNew from "../components/WhatsNew/WhatsNew";
import { useChangelog } from "../hooks/useChangelog";
import styles from "./Index.module.css";
import "../global/global.css";

function RecordingCard({ recording }: { recording: RecordingConfig }): React.ReactElement {
  return (
    <Link to={`/recording/${recording.id}`} className={styles.letterCard}>
      <span className={styles.letterIcon}>{recording.icon}</span>
      <div className={styles.letterInfo}>
        <h3>{recording.title}</h3>
        <p>{recording.subtitle}</p>
      </div>
      <span className={styles.arrow}>→</span>
    </Link>
  );
}

function Index(): React.ReactElement {
  const [showWhatsNew, setShowWhatsNew] = useState(false);
  const { data: changelog } = useChangelog();
  const recordings = getRecordingsByCategory("recording");
  const memoirs = getRecordingsByCategory("memoir");

  return (
    <div className={styles.container}>
      {/* What's New Modal */}
      <WhatsNew isOpen={showWhatsNew} onClose={() => setShowWhatsNew(false)} />

      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <h1 className={styles.title}>The Memoirs of Linden Hilary Achen</h1>
          <p className={styles.subtitle}>(1902 - 1994)</p>
        </div>
        <div className={styles.whatsNewContainer}>
          <button
            className={styles.whatsNewButton}
            onClick={() => setShowWhatsNew(true)}
            aria-label="What's New"
          >
            <FontAwesomeIcon icon={faStar} />
            <span>What&apos;s New</span>
          </button>
          {changelog?.generatedAt && (
            <span className={styles.lastUpdated}>
              Last updated: {new Date(changelog.generatedAt).toLocaleDateString()}
            </span>
          )}
        </div>
      </header>

      {/* Main content */}
      <main className={styles.main}>
        {/* Portrait section */}
        <section className={styles.portraitSection}>
          <div className={styles.portraitFrame}>
            <img
              src="/photos/LHA.jpg"
              alt="Linden Hilary Achen, 1942"
              className={styles.portrait}
            />
          </div>
          <p className={styles.portraitCaption}>L.H.A., 1942</p>
        </section>

        {/* Memoirs section */}
        <section className={styles.memoirsSection}>
          <h2 className={styles.sectionTitle}>Voice Memoirs</h2>
          <div className={styles.lettersList}>
            {memoirs.map((recording) => (
              <RecordingCard key={recording.id} recording={recording} />
            ))}
          </div>
        </section>

        {/* Recordings section */}
        <section className={styles.lettersSection}>
          <h2 className={styles.sectionTitle}>Other Recordings</h2>
          <div className={styles.lettersList}>
            {recordings.map((recording) => (
              <RecordingCard key={recording.id} recording={recording} />
            ))}
          </div>
        </section>

        {/* Footer */}
        <footer className={styles.footer}>
          <p>Made with ❤️ to preserve and share Grandpa&apos;s memories</p>
        </footer>
      </main>
    </div>
  );
}

export default Index;
