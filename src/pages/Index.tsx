import { useState } from "react";
import { Link } from "react-router-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faRobot, faMapMarkerAlt, faArrowAltCircleRight } from "@fortawesome/free-solid-svg-icons";
import { getRecordingsByCategory, type RecordingConfig } from "../config/recordings";
import WhatsNew from "../components/WhatsNew/WhatsNew";
import LhaGpt from "../components/LhaGpt/LhaGpt";
import { PlacesMapModal } from "../components/PlacesMap";
import TranscriptSearch from "../components/TranscriptSearch/TranscriptSearch";
import { useChangelog } from "../hooks/useChangelog";
import styles from "./Index.module.css";
import "../global/global.css";
import { faGithub } from "@fortawesome/free-brands-svg-icons";

function RecordingCard({ recording }: { recording: RecordingConfig }): React.ReactElement {
  return (
    <Link to={`/recording/${recording.id}`} className={styles.letterCard}>
      <div className={styles.letterInfo}>
        <div className={styles.titleRow}>
          <h3>{recording.title}</h3>
          <div
            className={`${styles.categoryBadge} ${styles[`badge${recording.category.charAt(0).toUpperCase() + recording.category.slice(1)}`]}`}
          >
            {recording.categoryLabel}
          </div>
        </div>
        <p>{recording.subtitle}</p>
      </div>
      <div className={styles.arrow}>
        <FontAwesomeIcon icon={faArrowAltCircleRight} />
      </div>
    </Link>
  );
}

function Index(): React.ReactElement {
  const [showWhatsNew, setShowWhatsNew] = useState(false);
  const [showLhaGpt, setShowLhaGpt] = useState(false);
  const [showPlacesMap, setShowPlacesMap] = useState(false);
  const { data: changelog } = useChangelog();
  const recordings = getRecordingsByCategory("recording");
  const memoirs = getRecordingsByCategory("memoir");

  return (
    <div className={styles.container}>
      {/* What's New Modal */}
      <WhatsNew isOpen={showWhatsNew} onClose={() => setShowWhatsNew(false)} />

      {/* LHA-GPT Chat Modal */}
      <LhaGpt isOpen={showLhaGpt} onClose={() => setShowLhaGpt(false)} />

      {/* Places Map Modal */}
      <PlacesMapModal isOpen={showPlacesMap} onClose={() => setShowPlacesMap(false)} />

      {/* Header */}
      <header className={styles.header}>
        <div className={styles.headerContent}>
          <h1 className={styles.title}>
            A Life on the Canadian Prairies: The Memoirs of Linden Hilary Achen
          </h1>
          <p className={styles.subtitle}>
            The recorded memoirs of Linden &quot;Lindy&quot; Hilary Achen (1902–1994), recounting
            his life farming on the Canadian Prairies and his work expanding rural electricity
            across western Canada
          </p>
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
            <p className={styles.portraitCaption}>Lindy Achen, 1942</p>
          </div>
        </section>

        {/* Search section */}
        <section className={styles.searchSection}>
          <TranscriptSearch />
        </section>

        {/* Interactive Features Buttons */}
        <section className={styles.featuresSection}>
          <button
            className={`${styles.featureButton}`}
            onClick={() => setShowPlacesMap(true)}
            aria-label="Explore Places Map"
          >
            <div className={styles.featureContent}>
              <div className={styles.featureTitleLine}>
                <FontAwesomeIcon icon={faMapMarkerAlt} className={styles.featureIcon} />
                <span className={styles.featureTitle}>Travel Map</span>
              </div>
              <span className={styles.featureDescription}>Places Lindy Mentions</span>
            </div>
          </button>
          <button
            className={`${styles.featureButton}`}
            onClick={() => setShowLhaGpt(true)}
            aria-label="Chat with LHA-GPT"
          >
            <div className={styles.featureContent}>
              <div className={styles.featureTitleLine}>
                <FontAwesomeIcon icon={faRobot} className={styles.featureIcon} />
                <span className={styles.featureTitle}>LHA-GPT</span>
              </div>
              <span className={styles.featureDescription}>Ask questions</span>
            </div>
          </button>
          <button
            className={`${styles.featureButton}`}
            onClick={() => setShowWhatsNew(true)}
            aria-label="What's New"
          >
            <div className={styles.featureContent}>
              <div className={styles.featureTitleLine}>
                <FontAwesomeIcon icon={faGithub} className={styles.featureIcon} />
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
