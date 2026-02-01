import { useState, useEffect, useCallback, useMemo } from "react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faXmark, faMapMarkerAlt } from "@fortawesome/free-solid-svg-icons";
import { PlacesMap } from "./PlacesMap";
import { PlacesSidePanel } from "./PlacesSidePanel";
import { usePlaces } from "../../hooks/usePlaces";
import styles from "./PlacesMapModal.module.css";

interface PlacesMapModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialPlaceId?: number | null;
}

export function PlacesMapModal({
  isOpen,
  onClose,
  initialPlaceId,
}: PlacesMapModalProps): React.ReactElement | null {
  const { places, isLoading, error } = usePlaces();
  // Use initialPlaceId directly as the initial state, and it will be the selected place
  const [selectedPlaceId, setSelectedPlaceId] = useState<number | null>(
    () => initialPlaceId ?? null
  );

  // Get selected place object
  const selectedPlace = useMemo(() => {
    if (!selectedPlaceId) return null;
    return places.find((p) => p.geonameid === selectedPlaceId) || null;
  }, [selectedPlaceId, places]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === "Escape" && isOpen) {
        if (selectedPlaceId) {
          // First escape deselects
          setSelectedPlaceId(null);
        } else {
          // Second escape closes modal
          onClose();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose, selectedPlaceId]);

  const handlePlaceSelect = useCallback((placeId: number | null) => {
    setSelectedPlaceId(placeId);
  }, []);

  const handleDeselectPlace = useCallback(() => {
    setSelectedPlaceId(null);
  }, []);

  // Handle close with selection reset
  const handleClose = useCallback(() => {
    setSelectedPlaceId(null);
    onClose();
  }, [onClose]);

  if (!isOpen) return null;

  return (
    <div className={styles.overlay}>
      {/* Backdrop for closing */}
      <button
        type="button"
        className={styles.backdrop}
        onClick={handleClose}
        aria-label="Close map"
      />

      <div
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="places-map-title"
      >
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.titleContainer}>
            <FontAwesomeIcon icon={faMapMarkerAlt} className={styles.titleIcon} />
            <h2 id="places-map-title" className={styles.title}>
              Places in the Memoirs
            </h2>
            <span className={styles.placeCount}>{places.length} locations mentioned</span>
          </div>
          <button className={styles.closeButton} onClick={handleClose} aria-label="Close">
            <FontAwesomeIcon icon={faXmark} />
          </button>
        </div>

        {/* Main content area */}
        <div className={styles.content}>
          {isLoading && (
            <div className={styles.loadingState}>
              <span>Loading places data...</span>
            </div>
          )}

          {error && (
            <div className={styles.errorState}>
              <span>Failed to load places: {error.message}</span>
            </div>
          )}

          {!isLoading && !error && (
            <>
              <PlacesMap
                places={places}
                selectedPlaceId={selectedPlaceId}
                onPlaceSelect={handlePlaceSelect}
              />
              <PlacesSidePanel
                place={selectedPlace}
                onClose={handleDeselectPlace}
                onCloseModal={handleClose}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
