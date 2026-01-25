import { useState, useCallback, useEffect } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faChevronLeft, faChevronRight } from "@fortawesome/free-solid-svg-icons";
import styles from "./InlinePhotoSlider.module.css";

// Build photo URLs from filename
function getPhotoSmallUrl(filename: string): string {
  return `/static_assets/photos/historical/small/${filename}.small.jpg`;
}

function getPhotoFullUrl(filename: string): string {
  return `/static_assets/photos/historical/${filename}.jpg`;
}

// Format caption with date, location, and credit
export function formatCaption(photo: Photo): string {
  const parts: string[] = [];

  if (photo.caption) {
    parts.push(photo.caption);
  }

  const metadata: string[] = [];
  if (photo.date) {
    metadata.push(photo.date);
  }
  if (photo.location && photo.location !== "Unknown") {
    metadata.push(photo.location);
  }
  if (photo.credit) {
    metadata.push(`Photo courtesy of ${photo.credit}`);
  }

  if (metadata.length > 0) {
    if (parts.length > 0) {
      parts.push(`(${metadata.join(", ")})`);
    } else {
      parts.push(metadata.join(", "));
    }
  }

  return parts.join(" ");
}

export const InlinePhotoSlider: React.FC<{
  photos: Photo[];
  onPhotoClick: (photo: Photo) => void;
  float?: "left" | "right";
}> = ({ photos, onPhotoClick, float = "right" }) => {
  const [currentIndex, setCurrentIndex] = useState(0);

  const hasMultiple = photos.length > 1;
  const currentPhoto = photos[currentIndex];

  useEffect(() => {
    if (!hasMultiple) return;

    const interval = setInterval(() => {
      setCurrentIndex((prev) => (prev < photos.length - 1 ? prev + 1 : 0));
    }, 10000); // 10 seconds

    return () => clearInterval(interval);
  }, [hasMultiple, photos.length]);

  const handlePrev = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      setCurrentIndex((prev) => (prev > 0 ? prev - 1 : photos.length - 1));
    },
    [photos.length]
  );

  const handleNext = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      setCurrentIndex((prev) => (prev < photos.length - 1 ? prev + 1 : 0));
    },
    [photos.length]
  );

  const handleClick = useCallback(() => {
    onPhotoClick(currentPhoto);
  }, [currentPhoto, onPhotoClick]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowLeft" && hasMultiple) {
        e.preventDefault();
        setCurrentIndex((prev) => (prev > 0 ? prev - 1 : photos.length - 1));
      } else if (e.key === "ArrowRight" && hasMultiple) {
        e.preventDefault();
        setCurrentIndex((prev) => (prev < photos.length - 1 ? prev + 1 : 0));
      }
    },
    [hasMultiple, photos.length]
  );

  if (!currentPhoto) return null;

  const caption = formatCaption(currentPhoto);

  return (
    <figure
      className={`${styles.photoSlider} ${float === "left" ? styles.floatLeft : styles.floatRight}`}
    >
      <div className={styles.imageContainer}>
        <button
          type="button"
          className={styles.imageButton}
          onClick={handleClick}
          onKeyDown={handleKeyDown}
          aria-label={caption || "View historical photo"}
        >
          {photos.map((photo, index) => (
            <img
              key={photo.filename}
              src={getPhotoSmallUrl(photo.filename)}
              alt={formatCaption(photo) || "Historical photo"}
              className={`${styles.image} ${index === currentIndex ? styles.active : ""}`}
              loading="lazy"
            />
          ))}
        </button>

        {hasMultiple && (
          <>
            <button
              type="button"
              className={`${styles.navButton} ${styles.prevButton}`}
              onClick={handlePrev}
              aria-label="Previous photo"
            >
              <FontAwesomeIcon icon={faChevronLeft} />
            </button>
            <button
              type="button"
              className={`${styles.navButton} ${styles.nextButton}`}
              onClick={handleNext}
              aria-label="Next photo"
            >
              <FontAwesomeIcon icon={faChevronRight} />
            </button>
            <div className={styles.indicator}>
              {currentIndex + 1} / {photos.length}
            </div>
          </>
        )}
      </div>

      {caption && <figcaption className={styles.caption}>{caption}</figcaption>}
    </figure>
  );
};

// Export the URL builder for use in PhotoModal
export { getPhotoFullUrl };
