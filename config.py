# ── Tilemap Tracker Configuration ──────────────────────────────────────────────

# Your Google Sheet ID (from the URL: /d/SHEET_ID/edit)
SHEET_ID = "YOUR_SHEET_ID_HERE"

# Tab names
TILEMAP_TAB = "Sheet1"   # The tab with your grid
LEGEND_TAB  = "Legend"  # The tab with artist + completion colour mappings

# A1 ranges — expand these to cover your full grid/legend
TILEMAP_RANGE = "A1:BZ300"   # Wide enough to cover your full map
LEGEND_RANGE  = "A1:E20"     # Cols A:B = artists, Cols D:E = completion thresholds

# Colour matching tolerance (0–255 Euclidean RGB distance).
# 15 handles minor rendering differences without causing false matches.
COLOUR_TOLERANCE = 15
