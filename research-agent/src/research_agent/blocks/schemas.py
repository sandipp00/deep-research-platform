from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


# ── Block data models ─────────────────────────────────────────────────────────

class MarkdownData(BaseModel):
    content: str


class DataTableData(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]


class InsightItem(BaseModel):
    title: str
    body: str
    severity: Literal["info", "warning", "success"] = "info"


class InsightCardsData(BaseModel):
    items: list[InsightItem]


class MapMarker(BaseModel):
    lat: float
    lon: float
    label: str
    popup: str = ""


class LeafletMapData(BaseModel):
    center: dict[str, float]    # {"lat": float, "lon": float}
    zoom: int = 12
    markers: list[MapMarker]


# ── Block wrapper models (discriminated union) ────────────────────────────────

class MarkdownBlock(BaseModel):
    template_id: Literal["markdown"] = "markdown"
    data: MarkdownData


class DataTableBlock(BaseModel):
    template_id: Literal["data-table"] = "data-table"
    data: DataTableData


class InsightCardsBlock(BaseModel):
    template_id: Literal["insight-cards"] = "insight-cards"
    data: InsightCardsData


class LeafletMapBlock(BaseModel):
    template_id: Literal["leaflet-map"] = "leaflet-map"
    data: LeafletMapData


Block = Annotated[
    MarkdownBlock | DataTableBlock | InsightCardsBlock | LeafletMapBlock,
    Field(discriminator="template_id"),
]


class FollowUp(BaseModel):
    label: str
    query: str
    category: str = "deeper"


class ResearchResponse(BaseModel):
    query: str
    blocks: list[Block]
    sources: list[str] = []
    follow_ups: list[FollowUp] = []
