import { useState, useCallback, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faCodeBranch } from "@fortawesome/free-solid-svg-icons";
import styles from "./AlternateTellingLink.module.css";

export function AlternateTellingLink({
  topic,
  preview,
  onClick,
}: {
  topic: string;
  preview: string;
  onClick: () => void;
}): React.ReactElement {
  const [showPreview, setShowPreview] = useState(false);
  const [position, setPosition] = useState({ top: 0, left: 0 });
  const buttonRef = useRef<HTMLSpanElement>(null);

  const updatePosition = useCallback(() => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setPosition({
        top: rect.top + window.scrollY,
        left: rect.left + rect.width / 2 + window.scrollX,
      });
    }
  }, []);

  const handleMouseEnter = useCallback(() => {
    updatePosition();
    setShowPreview(true);
  }, [updatePosition]);

  const handleMouseLeave = useCallback(() => {
    setShowPreview(false);
  }, []);

  const handleClick = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      onClick();
    },
    [onClick]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onClick();
      }
    },
    [onClick]
  );

  // Update position on scroll
  useEffect(() => {
    if (showPreview) {
      window.addEventListener("scroll", updatePosition, true);
      return () => window.removeEventListener("scroll", updatePosition, true);
    }
  }, [showPreview, updatePosition]);

  return (
    <>
      <span
        ref={buttonRef}
        className={styles.alternateTellingButton}
        onClick={handleClick}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        role="button"
        tabIndex={0}
        onKeyDown={handleKeyDown}
        aria-label={`Alternate telling: ${topic}`}
      >
        <FontAwesomeIcon icon={faCodeBranch} />
      </span>
      {showPreview &&
        createPortal(
          <div
            className={styles.previewModal}
            style={{
              top: `${position.top}px`,
              left: `${position.left}px`,
            }}
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
          >
            <div className={styles.previewTopic}>{topic}</div>
            <div className={styles.previewText}>{preview}</div>
          </div>,
          document.body
        )}
    </>
  );
}
