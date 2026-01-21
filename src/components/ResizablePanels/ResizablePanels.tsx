import { useState, useRef, useEffect, useCallback } from "react";
import styles from "./ResizablePanels.module.css";

export const ResizablePanels: React.FC<{
  leftPanel: React.ReactNode;
  rightPanel: React.ReactNode;
  defaultLeftWidth?: number;
  minLeftWidth?: number;
  maxLeftWidth?: number;
  chaptersExpanded?: boolean;
  onToggleChapters?: () => void;
}> = ({
  leftPanel,
  rightPanel,
  defaultLeftWidth = 320,
  minLeftWidth = 200,
  maxLeftWidth = 600,
  chaptersExpanded = false,
  onToggleChapters,
}) => {
  const [leftWidth, setLeftWidth] = useState(defaultLeftWidth);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isDragging || !containerRef.current) return;

      const containerRect = containerRef.current.getBoundingClientRect();
      const newWidth = e.clientX - containerRect.left;

      // Clamp the width within min and max bounds
      const clampedWidth = Math.max(minLeftWidth, Math.min(maxLeftWidth, newWidth));
      setLeftWidth(clampedWidth);
    },
    [isDragging, minLeftWidth, maxLeftWidth]
  );

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const step = e.shiftKey ? 50 : 10;

      switch (e.key) {
        case "ArrowLeft":
          e.preventDefault();
          setLeftWidth((prev) => Math.max(minLeftWidth, prev - step));
          break;
        case "ArrowRight":
          e.preventDefault();
          setLeftWidth((prev) => Math.min(maxLeftWidth, prev + step));
          break;
        case "Home":
          e.preventDefault();
          setLeftWidth(minLeftWidth);
          break;
        case "End":
          e.preventDefault();
          setLeftWidth(maxLeftWidth);
          break;
      }
    },
    [minLeftWidth, maxLeftWidth]
  );

  // Set up global mouse event listeners when dragging
  useEffect(() => {
    if (isDragging) {
      document.addEventListener("mousemove", handleMouseMove);
      document.addEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";

      return () => {
        document.removeEventListener("mousemove", handleMouseMove);
        document.removeEventListener("mouseup", handleMouseUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      };
    }
  }, [isDragging, handleMouseMove, handleMouseUp]);

  return (
    <div ref={containerRef} className={styles.container}>
      {/* Mobile toggle button - only visible on mobile */}
      {onToggleChapters && (
        <button
          type="button"
          className={styles.mobileToggle}
          onClick={onToggleChapters}
          aria-label={chaptersExpanded ? "Hide chapters" : "Show chapters"}
        >
          <span className={styles.toggleIcon}>{chaptersExpanded ? "▼" : "▶"}</span>
          <span className={styles.toggleText}>
            {chaptersExpanded ? "Hide Chapters" : "Show Chapters"}
          </span>
        </button>
      )}

      <div
        className={`${styles.leftPanel} ${chaptersExpanded ? styles.expanded : ""}`}
        style={{ width: `${leftWidth}px` }}
      >
        {leftPanel}
      </div>

      <div
        className={`${styles.divider} ${isDragging ? styles.dragging : ""}`}
        onMouseDown={handleMouseDown}
        onKeyDown={handleKeyDown}
        role="slider"
        tabIndex={0}
        aria-label="Resize panels"
        aria-valuenow={leftWidth}
        aria-valuemin={minLeftWidth}
        aria-valuemax={maxLeftWidth}
        aria-orientation="horizontal"
      >
        <div className={styles.dividerHandle} />
      </div>

      <div className={styles.rightPanel}>{rightPanel}</div>
    </div>
  );
};
