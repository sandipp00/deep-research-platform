import { useEffect } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import type { LeafletMapData } from "@/types";

// Custom on-brand pin — gradient violet→pink, glow, matches the rest of the UI.
const pinSvg = `
  <svg xmlns="http://www.w3.org/2000/svg" width="36" height="46" viewBox="0 0 36 46">
    <defs>
      <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#a78bfa"/>
        <stop offset="50%" stop-color="#ec4899"/>
        <stop offset="100%" stop-color="#22d3ee"/>
      </linearGradient>
      <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
        <feGaussianBlur stdDeviation="2.2" result="b"/>
        <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
    </defs>
    <path filter="url(#glow)" fill="url(#g)" stroke="white" stroke-width="2"
      d="M18 2 C26 2 32 8 32 16 C32 26 18 44 18 44 C18 44 4 26 4 16 C4 8 10 2 18 2 Z"/>
    <circle cx="18" cy="16" r="5" fill="white"/>
  </svg>`.trim();

const brandIcon = L.divIcon({
  className: "lumen-pin",
  html: pinSvg,
  iconSize: [36, 46],
  iconAnchor: [18, 44],
  popupAnchor: [0, -38],
});

function FitToMarkers({ markers }: { markers: { lat: number; lon: number }[] }) {
  const map = useMap();
  useEffect(() => {
    if (markers.length === 0) return;
    if (markers.length === 1) {
      map.setView([markers[0].lat, markers[0].lon], 15);
      return;
    }
    const bounds = L.latLngBounds(markers.map((m) => [m.lat, m.lon] as [number, number]));
    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
  }, [map, markers]);
  return null;
}

export default function LeafletMapBlock({ data }: { data: LeafletMapData }) {
  const center = data.center ?? { lat: 0, lon: 0 };
  const markers = data.markers ?? [];
  const zoom = data.zoom ?? 13;

  return (
    <div className="rounded-2xl overflow-hidden border border-white/[0.06] shadow-glow"
         style={{ height: 440 }}>
      <MapContainer
        center={[center.lat, center.lon]}
        zoom={zoom}
        scrollWheelZoom={false}
        style={{ height: "100%", width: "100%" }}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitToMarkers markers={markers} />
        {markers.map((m, i) => (
          <Marker key={i} position={[m.lat, m.lon]} icon={brandIcon}>
            <Popup>
              <div className="font-semibold">{m.label}</div>
              {m.popup && <div className="text-xs mt-1 text-zinc-600">{m.popup}</div>}
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
