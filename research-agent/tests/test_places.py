from research_agent.blocks.block_formatter import (
    ToolResult, extract_places, format_blocks, parse_place_line,
)

TEXT = """Top spots:
1. Third Wave
PLACE|Third Wave Coffee|12.9352|77.6245|80 Feet Rd, Koramangala
PLACE|**Blue Tokai**|12.9719|77.6412|Indiranagar
PLACE|Bad|abc|77|x
PLACE|OutOfRange|95.0|77.0|x
PLACE|NoCoords
- PLACE|Dyu Art Cafe|12.98|77.59|Vasanth Nagar
Done."""


def test_parse_line_valid_and_invalid():
    p = parse_place_line("PLACE|A|12.5|77.5|Addr")
    assert (p.name, p.lat, p.lon, p.address) == ("A", 12.5, 77.5, "Addr")
    assert parse_place_line("PLACE|A|91|77|x") is None
    assert parse_place_line("PLACE|A|12|181|x") is None
    assert parse_place_line("PLACE||12|77|x") is None
    assert parse_place_line("hello") is None


def test_extract_places_strips_all_place_lines():
    places, clean = extract_places(TEXT)
    assert [p.name for p in places] == ["Third Wave Coffee", "Blue Tokai", "Dyu Art Cafe"]
    assert "PLACE|" not in clean
    assert "Top spots" in clean and "Done." in clean


def test_format_blocks_prefers_answer_over_nearby():
    nearby = ToolResult("nearby_places", {}, "PLACE|Generic|12.9|77.6|x|1km")
    r = format_blocks(TEXT, [nearby], "q")
    ids = [b.template_id for b in r.blocks]
    assert ids == ["markdown", "leaflet-map", "data-table"]
    m = r.blocks[1].data
    assert [x.label for x in m.markers] == ["Third Wave Coffee", "Blue Tokai", "Dyu Art Cafe"]
    assert 12.93 < m.center["lat"] < 12.99
    assert [row["Name"] for row in r.blocks[2].data.rows] == [x.label for x in m.markers]
    assert "PLACE|" not in r.blocks[0].data.content


def test_fallback_to_nearby_places():
    nearby = ToolResult("nearby_places", {}, "Found 1\nPLACE|Generic|12.9|77.6|x|1.0km")
    r = format_blocks("No places here", [nearby], "q")
    assert r.blocks[1].data.markers[0].label == "Generic"
