import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faTimes } from "@fortawesome/free-solid-svg-icons";
import { formatCaption, getPhotoFullUrl } from "./InlinePhotoSlider";
import styles from "./PhotoModal.module.css";

export const PhotoModal: React.FC<{
  photo: Photo | null;
  onClose: () => void;
}> = ({ photo, onClose }) => {
  const overlayRef = useRef<HTMLDivElement>(null);

  // Handle escape key and click outside
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    const handleClickOutside = (e: MouseEvent) => {
      if (e.target === overlayRef.current) {
        onClose();
      }
    };

    if (photo) {
      document.addEventListener("keydown", handleKeyDown);
      document.addEventListener("click", handleClickOutside);
      // Prevent body scroll when modal is open
      document.body.style.overflow = "hidden";
    }

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("click", handleClickOutside);
      document.body.style.overflow = "";
    };
  }, [photo, onClose]);

  if (!photo) return null;

  const caption = formatCaption(photo);

  return createPortal(
    <div
      ref={overlayRef}
      className={styles.overlay}
      role="dialog"
      aria-modal="true"
      aria-label={caption || "Photo viewer"}
    >
      <button
        type="button"
        className={styles.closeButton}
        onClick={onClose}
        aria-label="Close photo viewer"
      >
        <FontAwesomeIcon icon={faTimes} />
      </button>

      <div className={styles.content}>
        <img
          src={getPhotoFullUrl(photo.filename)}
          alt={caption || "Historical photo"}
          className={styles.image}
        />

        {caption && <p className={styles.caption}>{caption}</p>}
      </div>
    </div>,
    document.body
  );
};
