"use client";

/**
 * Project map: Leaflet with OpenStreetMap tiles, loaded only when the visitor asks for it
 * (DESIGN_SYSTEM §8 "Map"; ARCHITECTURE §13; task 5.3, D-041).
 *
 * How it works:
 *   1. The server renders the address and a "Get directions" link (works without JavaScript).
 *   2. After hydration a "Show map" button appears. Pressing it loads Leaflet (a separate chunk)
 *      and its stylesheet, then draws the pin with a pop-up: name, address, RERA number and the
 *      directions link.
 *
 * WHY on tap: the map and its tiles are the heaviest thing on the page, and most visitors never
 * open it. Nothing is requested from the tile server until the visitor presses the button.
 *
 * SECURITY: the pop-up is built from DOM text nodes, never an HTML string, so a project name or
 * address can't inject markup. The tile host is in the CSP `img-src` (proxy.ts, SECURITY §4).
 * OpenStreetMap's tile policy (checked 2 Nov 2026): HTTPS URL only, visible attribution, a
 * normal Referer (our Referrer-Policy sends the origin), no bulk or offline use, no SLA, so the
 * address and directions link stay on the page as the fallback.
 */
import { useEffect, useRef, useState, useSyncExternalStore } from "react";

const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

export interface ProjectMapProps {
  lat: number;
  lng: number;
  name: string;
  address: string | null;
  reraNumber: string | null;
  directionsUrl: string;
}

function popupContent(props: ProjectMapProps): HTMLElement {
  const box = document.createElement("div");
  const title = document.createElement("strong");
  title.textContent = props.name;
  box.append(title);
  for (const line of [props.address, props.reraNumber ? `UP-RERA ${props.reraNumber}` : null]) {
    if (!line) continue;
    const p = document.createElement("div");
    p.textContent = line;
    box.append(p);
  }
  const link = document.createElement("a");
  link.href = props.directionsUrl;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = "Get directions";
  box.append(link);
  return box;
}

function noSubscribe(): () => void {
  return () => {};
}

export function ProjectMap(props: ProjectMapProps) {
  // WHY two flags, not one state: the effect that builds the map must not re-run (and remove
  // the map in its clean-up) when loading finishes, only when the visitor opens it.
  const [requested, setRequested] = useState(false);
  const [failed, setFailed] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  // WHY: true only in the browser after hydration, so the button never shows without JavaScript.
  const hydrated = useSyncExternalStore(
    noSubscribe,
    () => true,
    () => false,
  );
  const { lat, lng, name, address, reraNumber, directionsUrl } = props;

  useEffect(() => {
    if (!requested || !container.current) return;
    let map: import("leaflet").Map | undefined;
    let cancelled = false;
    (async () => {
      try {
        const [L] = await Promise.all([import("leaflet"), import("leaflet/dist/leaflet.css")]);
        if (cancelled || !container.current) return;
        const p = { lat, lng, name, address, reraNumber, directionsUrl };
        map = L.map(container.current, { scrollWheelZoom: false }).setView([p.lat, p.lng], 15);
        // WHY a tile layer option, not a global: attribution must stay visible (OSM policy).
        L.tileLayer(TILE_URL, { maxZoom: 19, attribution: ATTRIBUTION }).addTo(map);
        // WHY a circle marker: Leaflet's default pin is an image path that bundlers break.
        L.circleMarker([p.lat, p.lng], {
          radius: 10,
          color: "#D9A441",
          weight: 3,
          fillColor: "#E2B65A",
          fillOpacity: 0.9,
        })
          .addTo(map)
          .bindPopup(popupContent(p))
          .openPopup();
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      map?.remove();
    };
  }, [requested, lat, lng, name, address, reraNumber, directionsUrl]);

  return (
    <div className="flex flex-col gap-3">
      {hydrated && !requested ? (
        <button
          type="button"
          onClick={() => setRequested(true)}
          className="min-h-11 self-start rounded-pill border border-gold-500 px-5 font-semibold text-gold-300 hover:bg-gold-tint"
        >
          Show map
        </button>
      ) : null}
      {failed ? (
        <p role="status" className="text-small text-muted">
          The map couldn&apos;t load. Use the directions link instead.
        </p>
      ) : null}
      {requested && !failed ? (
        <div
          ref={container}
          className="empire-map h-80 w-full overflow-hidden rounded-card border border-line"
          role="region"
          aria-label={`Map showing ${props.name}`}
          data-testid="project-map"
        />
      ) : null}
    </div>
  );
}

export default ProjectMap;
