import { useState } from "react";
import { Link } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faStar, faRobot } from "@fortawesome/free-solid-svg-icons";
import { getRecordingsByCategory, type RecordingConfig } from "../config/recordings";
import WhatsNew from "../components/WhatsNew/WhatsNew";
import LhaGpt from "../components/LhaGpt";
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
  const [showLhaGpt, setShowLhaGpt] = useState(false);
  const { data: changelog } = useChangelog();
  const recordings = getRecordingsByCategory("recording");
  const memoirs = getRecordingsByCategory("memoir");

  return (
    <div className={styles.container}>
      {/* What's New Modal */}
      <WhatsNew isOpen={showWhatsNew} onClose={() => setShowWhatsNew(false)} />

      {/* LHA-GPT Chat Modal */}
      <LhaGpt isOpen={showLhaGpt} onClose={() => setShowLhaGpt(false)} />

      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <h1 className={styles.title}>The Memoirs of Linden Hilary Achen</h1>
          <p className={styles.subtitle}>(1902 - 1994)</p>
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

        {/* Interactive Features Buttons */}
        <section className={styles.featuresSection}>
          <button
            className={`${styles.featureButton} ${styles.featurePrimary}`}
            onClick={() => setShowLhaGpt(true)}
            aria-label="Chat with LHA-GPT"
          >
            <div className={styles.featureContent}>
              <div className={styles.featureTitleLine}>
                <FontAwesomeIcon icon={faRobot} className={styles.featureIcon} />
                <span className={styles.featureTitle}>LHA-GPT</span>
              </div>
              <span className={styles.featureDescription}>Ask questions about the memoirs</span>
            </div>
          </button>
          <button
            className={`${styles.featureButton} ${styles.featureSecondary}`}
            onClick={() => setShowWhatsNew(true)}
            aria-label="What's New"
          >
            <div className={styles.featureContent}>
              <div className={styles.featureTitleLine}>
                <FontAwesomeIcon icon={faStar} className={styles.featureIcon} />
                <span className={styles.featureTitle}>What&apos;s New</span>
              </div>
              <span className={styles.featureDescription}>
                {changelog?.generatedAt
                  ? `Updated ${new Date(changelog.generatedAt).toLocaleDateString()}`
                  : "Recent updates"}
              </span>
            </div>
          </button>
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
