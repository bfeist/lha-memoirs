import { useEffect, useRef, useState, useCallback } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import styles from "./PlacesMap.module.css";

interface PlacesMapProps {
  places: Place[];
  selectedPlaceId: number | null;
  onPlaceSelect: (placeId: number | null) => void;
}

// Western Canada / NW USA bounding box for initial view
const INITIAL_CENTER: [number, number] = [-110, 52]; // Centered on Alberta/Saskatchewan
const INITIAL_ZOOM = 4;
const MIN_ZOOM = 3;
const MAX_ZOOM = 12;

// Cluster configuration
const CLUSTER_RADIUS = 50;
const CLUSTER_MAX_ZOOM = 10;

/**
 * Muted, historical-feeling map style (CartoDB Positron with sepia tint)
 * Using Stadia Maps for a reliable free tile source
 */
const MAP_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  name: "Historical Muted",
  sources: {
    "carto-light": {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}@2x.png",
        "https://b.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}@2x.png",
        "https://c.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}@2x.png",
      ],
      tileSize: 256,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    },
  },
  layers: [
    {
      id: "carto-tiles",
      type: "raster",
      source: "carto-light",
      paint: {
        "raster-saturation": -0.5,
        "raster-brightness-max": 0.9,
        "raster-contrast": -0.1,
      },
    },
  ],
};

/**
 * Convert places data to GeoJSON for MapLibre
 */
function placesToGeoJSON(places: Place[]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: places.map((place) => ({
      type: "Feature" as const,
      id: place.geonameid,
      geometry: {
        type: "Point" as const,
        coordinates: [place.longitude, place.latitude],
      },
      properties: {
        id: place.geonameid,
        name: place.name,
        admin1_name: place.admin1_name,
        country_code: place.country_code,
        mentionCount: place.mentions.length,
      },
    })),
  };
}

export function PlacesMap({
  places,
  selectedPlaceId,
  onPlaceSelect,
}: PlacesMapProps): React.ReactElement {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapLoaded, setMapLoaded] = useState(false);

  // Initialize map
  useEffect(() => {
    if (!mapContainerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: mapContainerRef.current,
      style: MAP_STYLE,
      center: INITIAL_CENTER,
      zoom: INITIAL_ZOOM,
      minZoom: MIN_ZOOM,
      maxZoom: MAX_ZOOM,
      attributionControl: false,
    });

    // Add minimal attribution
    map.addControl(
      new maplibregl.AttributionControl({
        compact: true,
        customAttribution: "",
      }),
      "bottom-right"
    );

    // Add navigation controls
    map.addControl(
      new maplibregl.NavigationControl({
        showCompass: false,
      }),
      "top-right"
    );

    map.on("load", () => {
      setMapLoaded(true);
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // Add/update data source and layers when map loads or places change
  useEffect(() => {
    if (!mapRef.current || !mapLoaded || places.length === 0) return;

    const map = mapRef.current;
    const geojson = placesToGeoJSON(places);

    // Add or update source
    const source = map.getSource("places") as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData(geojson);
    } else {
      map.addSource("places", {
        type: "geojson",
        data: geojson,
        cluster: true,
        clusterRadius: CLUSTER_RADIUS,
        clusterMaxZoom: CLUSTER_MAX_ZOOM,
        clusterProperties: {
          totalMentions: ["+", ["get", "mentionCount"]],
        },
      });

      // Cluster circles layer
      map.addLayer({
        id: "clusters",
        type: "circle",
        source: "places",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": [
            "step",
            ["get", "point_count"],
            "#8b7355", // small clusters - muted brown
            5,
            "#705d45", // medium clusters - darker brown
            15,
            "#5a4a38", // large clusters - even darker
          ],
          "circle-radius": [
            "step",
            ["get", "point_count"],
            18, // small clusters
            5,
            24, // medium clusters
            15,
            32, // large clusters
          ],
          "circle-stroke-width": 2,
          "circle-stroke-color": "rgba(255, 255, 255, 0.3)",
          "circle-opacity": 0.85,
        },
      });

      // Cluster count labels
      map.addLayer({
        id: "cluster-count",
        type: "symbol",
        source: "places",
        filter: ["has", "point_count"],
        layout: {
          "text-field": "{point_count_abbreviated}",
          "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
          "text-size": 12,
        },
        paint: {
          "text-color": "#ffffff",
        },
      });

      // Individual place markers (unclustered)
      map.addLayer({
        id: "unclustered-point",
        type: "circle",
        source: "places",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": [
            "case",
            ["==", ["get", "id"], selectedPlaceId ?? -1],
            "#d4af37", // selected - gold
            "#8b7355", // default - muted brown
          ],
          "circle-radius": [
            "case",
            ["==", ["get", "id"], selectedPlaceId ?? -1],
            16, // selected - larger
            [
              "step",
              ["get", "mentionCount"],
              7, // 1-2 mentions = small
              3,
              10, // 3-8 mentions = medium
              9,
              14, // 9-22 mentions = large
              23,
              18, // 23+ mentions = extra large
            ],
          ],
          "circle-stroke-width": [
            "case",
            ["==", ["get", "id"], selectedPlaceId ?? -1],
            3, // selected
            1.5, // default
          ],
          "circle-stroke-color": [
            "case",
            ["==", ["get", "id"], selectedPlaceId ?? -1],
            "#ffffff", // selected - white stroke
            "rgba(255, 255, 255, 0.4)", // default - subtle stroke
          ],
          "circle-opacity": 0.9,
        },
      });

      // Place name labels (always visible when not clustered)
      map.addLayer({
        id: "place-labels",
        type: "symbol",
        source: "places",
        filter: ["!", ["has", "point_count"]],
        layout: {
          "text-field": ["get", "name"],
          "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"],
          "text-size": 14,
          "text-offset": [0, -2],
          "text-anchor": "top",
          "text-allow-overlap": false,
          "text-ignore-placement": false,
          "symbol-sort-key": [
            "case",
            ["==", ["get", "id"], selectedPlaceId ?? -1],
            0, // selected place has highest priority
            ["*", -1, ["get", "mentionCount"]], // others sorted by mention count (more mentions = higher priority)
          ],
        },
        paint: {
          "text-color": "#3d3d3d",
          "text-halo-color": "rgba(255, 255, 255, 0.85)",
          "text-halo-width": 1.5,
          "text-opacity": 1, // Always visible on unclustered points
        },
      });
    }
  }, [mapLoaded, places, selectedPlaceId]);

  // Update selected place styling
  useEffect(() => {
    if (!mapRef.current || !mapLoaded) return;

    const map = mapRef.current;

    // Update paint properties for selection
    if (map.getLayer("unclustered-point")) {
      map.setPaintProperty("unclustered-point", "circle-color", [
        "case",
        ["==", ["get", "id"], selectedPlaceId ?? -1],
        "#d4af37",
        "#8b7355",
      ]);
      map.setPaintProperty("unclustered-point", "circle-radius", [
        "case",
        ["==", ["get", "id"], selectedPlaceId ?? -1],
        16,
        ["step", ["get", "mentionCount"], 7, 3, 10, 9, 14, 23, 18],
      ]);
      map.setPaintProperty("unclustered-point", "circle-stroke-width", [
        "case",
        ["==", ["get", "id"], selectedPlaceId ?? -1],
        3,
        1.5,
      ]);
      map.setPaintProperty("unclustered-point", "circle-stroke-color", [
        "case",
        ["==", ["get", "id"], selectedPlaceId ?? -1],
        "#ffffff",
        "rgba(255, 255, 255, 0.4)",
      ]);
    }

    if (map.getLayer("place-labels")) {
      map.setPaintProperty("place-labels", "text-opacity", 1); // Always visible
    }
  }, [selectedPlaceId, mapLoaded]);

  // Pan to selected place
  useEffect(() => {
    if (!mapRef.current || !mapLoaded || !selectedPlaceId) return;

    const selectedPlace = places.find((p) => p.geonameid === selectedPlaceId);
    if (selectedPlace) {
      mapRef.current.flyTo({
        center: [selectedPlace.longitude, selectedPlace.latitude],
        zoom: Math.max(mapRef.current.getZoom(), 7),
        duration: 800,
      });
    }
  }, [selectedPlaceId, places, mapLoaded]);

  // Handle map clicks
  const handleMapClick = useCallback(
    (e: maplibregl.MapMouseEvent) => {
      const map = mapRef.current;
      if (!map) return;

      // Check for cluster clicks
      const clusterFeatures = map.queryRenderedFeatures(e.point, {
        layers: ["clusters"],
      });

      if (clusterFeatures.length > 0) {
        const clusterId = clusterFeatures[0].properties?.cluster_id;
        const source = map.getSource("places") as maplibregl.GeoJSONSource;

        source.getClusterExpansionZoom(clusterId).then((zoom) => {
          const coords = (clusterFeatures[0].geometry as GeoJSON.Point).coordinates as [
            number,
            number,
          ];
          map.flyTo({
            center: coords,
            zoom: zoom ?? 8,
            duration: 500,
          });
        });
        return;
      }

      // Check for point clicks
      const pointFeatures = map.queryRenderedFeatures(e.point, {
        layers: ["unclustered-point"],
      });

      if (pointFeatures.length > 0) {
        const placeId = pointFeatures[0].properties?.id;
        if (placeId) {
          onPlaceSelect(placeId);
        }
      } else {
        // Click on empty area - deselect
        onPlaceSelect(null);
      }
    },
    [onPlaceSelect]
  );

  // Set up click handler
  useEffect(() => {
    if (!mapRef.current || !mapLoaded) return;

    const map = mapRef.current;
    map.on("click", handleMapClick);

    // Cursor changes on hover
    const handleMouseEnter = (): void => {
      map.getCanvas().style.cursor = "pointer";
    };
    const handleMouseLeave = (): void => {
      map.getCanvas().style.cursor = "";
    };

    map.on("mouseenter", "clusters", handleMouseEnter);
    map.on("mouseleave", "clusters", handleMouseLeave);
    map.on("mouseenter", "unclustered-point", handleMouseEnter);
    map.on("mouseleave", "unclustered-point", handleMouseLeave);

    return () => {
      map.off("click", handleMapClick);
      map.off("mouseenter", "clusters", handleMouseEnter);
      map.off("mouseleave", "clusters", handleMouseLeave);
      map.off("mouseenter", "unclustered-point", handleMouseEnter);
      map.off("mouseleave", "unclustered-point", handleMouseLeave);
    };
  }, [mapLoaded, handleMapClick]);

  return (
    <div className={styles.mapContainer}>
      <div ref={mapContainerRef} className={styles.map} />
      {!mapLoaded && (
        <div className={styles.loading}>
          <span>Loading map...</span>
        </div>
      )}
    </div>
  );
}
