import { Link } from "react-router-dom";
import styles from "./Index.module.css";
import "../global/global.css";

function Index(): React.ReactElement {
  return (
    <div className={styles.container}>
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

        {/* Memoirs section */}
        <section className={styles.memoirsSection}>
          <h2 className={styles.sectionTitle}>
            <span className={styles.sectionIcon}>📖</span>
            Voice Memoirs
          </h2>
          <div className={styles.comingSoon}>
            <p>Coming Soon</p>
          </div>
        </section>

        {/* Christmas Letters section */}
        <section className={styles.lettersSection}>
          <h2 className={styles.sectionTitle}>
            <span className={styles.sectionIcon}>✉️</span>
            Other Recordings
          </h2>
          <div className={styles.lettersList}>
            <Link to="/christmas1986" className={styles.letterCard}>
              <span className={styles.letterIcon}>🎄</span>
              <div className={styles.letterInfo}>
                <h3>Christmas Letter, 1986</h3>
                <p>A letter from Grandpa to his son, recorded during the holiday season</p>
              </div>
              <span className={styles.arrow}>→</span>
            </Link>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className={styles.footer}>
        <p>Made with ❤️ to preserve and share Grandpa&apos;s memories</p>
      </footer>
    </div>
  );
}

export default Index;
