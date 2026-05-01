import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import L from "leaflet";
import type { LeafletMapData } from "@/types";

// Fix default marker icons (Vite/webpack break Leaflet's default icon paths)
const icon = new L.Icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

export default function LeafletMapBlock({ data }: { data: LeafletMapData }) {
  const center = data.center ?? { lat: 0, lon: 0 };
  const markers = data.markers ?? [];
  const zoom = data.zoom ?? 12;

  return (
    <div className="rounded-2xl overflow-hidden border border-white/[0.06]" style={{ height: 380 }}>
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
        {markers.map((m, i) => (
          <Marker key={i} position={[m.lat, m.lon]} icon={icon}>
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
