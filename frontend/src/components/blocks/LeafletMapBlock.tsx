import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import type { LeafletMapData } from "@/types";
import { useTheme } from "@/store/theme";
import "@/styles/map.css";

const TILES = {
  dark: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
  light: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
};

function pinIcon(n: number, active: boolean) {
  return L.divIcon({
    className: `lm-pin${active ? " on" : ""}`,
    html: `<div class="lm-pin-wrap" style="animation-delay:${Math.min(n * 90, 900)}ms"><span class="lm-pin-ring"></span><span class="lm-pin-dot">${n + 1}</span></div>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    popupAnchor: [0, -18],
  });
}

function esc(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]!));
}
void esc;

type Pt = { lat: number; lon: number };

function fit(map: L.Map, markers: Pt[], animate: boolean) {
  if (markers.length === 0) return;
  if (markers.length === 1) {
    map.setView([markers[0].lat, markers[0].lon], 15, { animate });
    return;
  }
  const b = L.latLngBounds(markers.map((m) => [m.lat, m.lon] as [number, number]));
  map.fitBounds(b, { padding: [50, 70], maxZoom: 16, animate, duration: 0.8 });
}

/** Exposes the map instance, fits on data change, and keeps size valid on container resize. */
function MapBridge({ markers, onMap }: { markers: Pt[]; onMap: (m: L.Map) => void }) {
  const map = useMap();
  useEffect(() => { onMap(map); }, [map, onMap]);
  useEffect(() => { fit(map, markers, false); }, [map, markers]);
  useEffect(() => {
    const el = map.getContainer();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => map.invalidateSize());
    ro.observe(el);
    return () => ro.disconnect();
  }, [map]);
  return null;
}

const Icon = ({ d }: { d: string }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
);

export default function LeafletMapBlock({ data }: { data: LeafletMapData }) {
  const theme = useTheme((s) => s.theme);
  const center = data.center ?? { lat: 0, lon: 0 };
  const markers = useMemo(() => data.markers ?? [], [data.markers]);
  const zoom = data.zoom ?? 13;
  const [map, setMap] = useState<L.Map | null>(null);
  const [active, setActive] = useState<number | null>(null);
  const [full, setFull] = useState(false);
  const markerRefs = useRef<(L.Marker | null)[]>([]);
  const stripRef = useRef<HTMLDivElement>(null);
  const ctrlRef = useRef<HTMLDivElement>(null);
  const onMap = useCallback((m: L.Map) => setMap(m), []);

  useEffect(() => {
    [ctrlRef.current, stripRef.current].forEach((el) => {
      if (el) { L.DomEvent.disableClickPropagation(el); L.DomEvent.disableScrollPropagation(el); }
    });
  }, [markers.length]);

  useEffect(() => {
    if (!full) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && setFull(false);
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [full]);

  useEffect(() => {
    if (!map) return;
    const t = setTimeout(() => map.invalidateSize(), 50);
    return () => clearTimeout(t);
  }, [map, full]);

  const focus = (i: number, open: boolean) => {
    setActive(i);
    const m = markers[i];
    if (!map || !m) return;
    map.flyTo([m.lat, m.lon], Math.max(map.getZoom(), 14), { duration: 0.9 });
    if (open) setTimeout(() => markerRefs.current[i]?.openPopup(), 500);
    stripRef.current?.children[i]?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  };

  const dark = theme === "dark";

  return (
    <div className={`lm-root ${dark ? "lm-dark" : ""} ${full ? "lm-full" : ""}`} style={full ? undefined : { height: 460 }}>
      {markers.length > 0 && (
        <div className="lm-chip lm-glass" style={{ top: 12, left: 12 }}>
          <i />{markers.length} place{markers.length === 1 ? "" : "s"}
        </div>
      )}
      <div className="lm-ctrls" ref={ctrlRef}>
        <button className="lm-btn lm-glass" aria-label="Zoom in" onClick={() => map?.zoomIn()}><Icon d="M12 5v14M5 12h14" /></button>
        <button className="lm-btn lm-glass" aria-label="Zoom out" onClick={() => map?.zoomOut()}><Icon d="M5 12h14" /></button>
        <button className="lm-btn lm-glass" aria-label="Fit all" onClick={() => { if (map) { setActive(null); fit(map, markers, true); } }}>
          <Icon d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" />
        </button>
        <button className="lm-btn lm-glass" aria-label="Toggle fullscreen" onClick={() => setFull((f) => !f)}>
          <Icon d={full ? "M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5" : "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"} />
        </button>
      </div>
      <MapContainer
        center={[center.lat, center.lon]}
        zoom={zoom}
        scrollWheelZoom={false}
        zoomControl={false}
        className="lm-map"
      >
        <TileLayer
          key={theme}
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/attributions">CARTO</a>'
          url={dark ? TILES.dark : TILES.light}
          subdomains="abcd"
          maxZoom={19}
        />
        <MapBridge markers={markers} onMap={onMap} />
        {markers.map((m, i) => (
          <Marker
            key={`${i}-${m.lat}-${m.lon}`}
            position={[m.lat, m.lon]}
            icon={pinIcon(i, active === i)}
            ref={(r) => { markerRefs.current[i] = r; }}
            eventHandlers={{ click: () => setActive(i), popupclose: () => setActive((a) => (a === i ? null : a)) }}
          >
            <Popup className="lm-popup" closeButton={false}>
              <div className="lm-popup-t">{m.label}</div>
              {m.popup && <div className="lm-popup-b">{m.popup}</div>}
            </Popup>
          </Marker>
        ))}
      </MapContainer>
      {markers.length > 0 && (
        <div className="lm-strip" ref={stripRef}>
          {markers.map((m, i) => (
            <button
              key={i}
              className={`lm-card lm-glass ${active === i ? "on" : ""}`}
              onClick={() => focus(i, true)}
              onMouseEnter={() => setActive(i)}
              onMouseLeave={() => setActive((a) => (a === i ? null : a))}
            >
              <b>{i + 1}</b>
              <div style={{ minWidth: 0 }}>
                <span>{m.label}</span>
                {m.popup && <small>{m.popup}</small>}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
