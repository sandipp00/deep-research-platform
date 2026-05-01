export interface User {
  id: string;
  email: string;
  name: string;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
}

export interface MarkdownData { content: string }
export interface DataTableData { columns: string[]; rows: Record<string, unknown>[] }
export interface InsightItem { title: string; body: string; severity?: "info" | "warning" | "success" }
export interface InsightCardsData { items: InsightItem[] }
export interface MapMarker { lat: number; lon: number; label: string; popup?: string }
export interface LeafletMapData { center: { lat: number; lon: number }; zoom?: number; markers: MapMarker[] }
export interface ChartPoint { label: string; value: number }
export interface BarChartData { x_axis: string; y_axis: string; points: ChartPoint[] }

export type Block =
  | { template_id: "markdown"; data: MarkdownData }
  | { template_id: "data-table"; data: DataTableData }
  | { template_id: "insight-cards"; data: InsightCardsData }
  | { template_id: "leaflet-map"; data: LeafletMapData }
  | { template_id: "bar-chart"; data: BarChartData }
  | { template_id: string; data: unknown };  // catch-all for forward compatibility

export interface FollowUp { label: string; query: string; category?: string }

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  blocks?: Block[] | null;
  sources?: string[] | null;
  followUps?: FollowUp[] | null;
  createdAt: string;
}

export interface Checkpoint {
  status: string;
  content: string;
  tool?: string;
}
