"""
Tilemap Tracker v2
──────────────────
Reads a Google Sheets tilemap and resolves two independent colour systems:
  1. ARTIST assignment  → cell background colour (solid fill per artist)
  2. COMPLETION status  → a second background colour applied on top (red/orange/yellow/green)

The Legend tab drives both systems — no hardcoding required.

Requirements:
    pip install google-api-python-client google-auth pandas
"""

import math
import pandas as pd
from pathlib import Path
from google.oauth2 import service_account
from googleapiclient.discovery import build

import config

# ── Auth ────────────────────────────────────────────────────────────────────────

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def get_sheets_service():
    """Authenticate with the Google Sheets API using a service account."""
    creds = service_account.Credentials.from_service_account_file(
        "credentials.json", scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds).spreadsheets()


# ── Colour Utilities ────────────────────────────────────────────────────────────

def rgb_to_hex(r: float, g: float, b: float) -> str:
    """Convert Google's 0.0–1.0 RGB floats to a #RRGGBB hex string."""
    return "#{:02X}{:02X}{:02X}".format(
        round(r * 255), round(g * 255), round(b * 255)
    )


def hex_to_rgb(hex_colour: str) -> tuple:
    """Convert a #RRGGBB hex string to an (R, G, B) integer tuple."""
    hex_colour = hex_colour.lstrip("#")
    return tuple(int(hex_colour[i:i + 2], 16) for i in (0, 2, 4))


def colour_distance(hex_a: str, hex_b: str) -> float:
    """Euclidean distance in RGB space between two hex colours."""
    r1, g1, b1 = hex_to_rgb(hex_a)
    r2, g2, b2 = hex_to_rgb(hex_b)
    return math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)


def best_colour_match(target_hex: str, candidates: list[dict], key: str) -> dict | None:
    """
    Find the closest colour match from a list of candidates.
    Each candidate dict must have a field named `key` containing a hex colour.
    Returns None if the closest match exceeds COLOUR_TOLERANCE.
    """
    if not target_hex:
        return None
    best = min(candidates, key=lambda c: colour_distance(target_hex, c[key]))
    if colour_distance(target_hex, best[key]) <= config.COLOUR_TOLERANCE:
        return best
    return None


def extract_background_colour(cell: dict) -> str | None:
    """
    Extract effective background colour from a cell.
    Returns None for white (#FFFFFF) or missing — treated as 'no fill'.
    """
    fmt = cell.get("effectiveFormat", {})
    bg = fmt.get("backgroundColor", {})
    r = bg.get("red", 1.0)
    g = bg.get("green", 1.0)
    b = bg.get("blue", 1.0)
    # Pure white = no meaningful fill
    if r >= 0.99 and g >= 0.99 and b >= 0.99:
        return None
    return rgb_to_hex(r, g, b)


# ── Legend Loader ───────────────────────────────────────────────────────────────

def load_legend(sheets_service) -> tuple[list[dict], list[dict]]:
    """
    Load both the artist legend and the completion legend from the Legend tab.

    Expected sheet layout:
    ┌─────────────────┬─────────────────────┐
    │  ARTIST LEGEND  │  COMPLETION LEGEND  │
    ├─────────────────┼─────────────────────┤
    │ Artist Name     │ Completion %        │
    │ Kaya | #6600CC  │ 25% | #FF0000       │
    │ Greg | #00CCCC  │ 50% | #FF8800       │
    │ ...             │ 75% | #FFFF00       │
    │                 │ 100% | #00FF00      │
    └─────────────────┴─────────────────────┘

    Columns A:B = Artist name | Artist hex colour
    Columns D:E = Completion label | Completion hex colour
    """
    result = sheets_service.values().get(
        spreadsheetId=config.SHEET_ID,
        range=f"{config.LEGEND_TAB}!{config.LEGEND_RANGE}"
    ).execute()

    rows = result.get("values", [])
    if len(rows) < 2:
        raise ValueError("Legend tab is empty or missing headers.")

    artists = []
    completions = []

    for row in rows[1:]:  # Skip header row
        # Artist legend: columns A (name) and B (hex colour)
        if len(row) >= 2 and row[0].strip() and row[1].strip():
            artists.append({
                "name": row[0].strip(),
                "colour_hex": row[1].strip().upper()
            })

        # Completion legend: columns D (label) and E (hex colour)
        if len(row) >= 5 and row[3].strip() and row[4].strip():
            try:
                pct = int(row[3].strip().replace("%", ""))
                completions.append({
                    "label": row[3].strip(),
                    "pct": pct,
                    "colour_hex": row[4].strip().upper()
                })
            except ValueError:
                pass

    print(f"✅ Loaded {len(artists)} artists, {len(completions)} completion thresholds.")
    return artists, completions


# ── Sheet Fetcher ───────────────────────────────────────────────────────────────

def fetch_sheet_with_formatting(sheets_service) -> dict:
    """
    Fetch the full tilemap grid including cell formatting via includeGridData.
    This is a single API call that returns both values and format metadata.
    """
    response = sheets_service.get(
        spreadsheetId=config.SHEET_ID,
        ranges=[f"{config.TILEMAP_TAB}!{config.TILEMAP_RANGE}"],
        includeGridData=True
    ).execute()

    return response["sheets"][0]["data"][0]


# ── Core Processor ──────────────────────────────────────────────────────────────

def process_tilemap(sheet_data: dict, artists: list[dict], completions: list[dict]) -> list[dict]:
    """
    Walk every cell in the tilemap. For each valid tile coordinate:

    ARTIST RESOLUTION:
      - Read the cell background colour
      - Match it against the artist legend (closest colour within tolerance)
      - White/no-fill cells within the grid = assigned but not started (0%)

    COMPLETION RESOLUTION:
      - The completion colour IS the background colour when a tile is in progress
      - When a tile is "done" (100%) the cell will be green
      - When a tile is "not started" the cell is white (artist colour shown as border
        in the sheet, but the script reads background for assignment here)

    NOTE: Looking at the screenshot more carefully — the artist assignment colour
    IS the cell background when the tile belongs to that artist. The completion
    colours (red/orange/yellow/green) REPLACE the artist background when applied.
    So we check completion colours FIRST, then artist colours.
    """
    tiles = []
    rows = sheet_data.get("rowData", [])

    for row_data in rows:
        cells = row_data.get("values", [])
        for cell in cells:
            # Only process cells with a tile coordinate (format: -NN/-NNN)
            cell_value = cell.get("formattedValue", "").strip()
            if not cell_value or "/" not in cell_value:
                continue

            # Validate it looks like a coordinate pair
            parts = cell_value.split("/")
            if len(parts) != 2:
                continue
            try:
                x, y = int(parts[0]), int(parts[1])
            except ValueError:
                continue

            # Get background colour
            bg_hex = extract_background_colour(cell)

            # ── Step 1: Check if this is a completion colour ──────────────
            completion_match = None
            completion_pct = 0
            if bg_hex and completions:
                completion_match = best_colour_match(bg_hex, completions, "colour_hex")
                if completion_match:
                    completion_pct = completion_match["pct"]

            # ── Step 2: Determine artist assignment ───────────────────────
            # If completion colour matched, the artist colour is obscured —
            # we still record the tile but mark artist as "needs_border_check"
            # In practice, cross-reference with tile coordinate ranges if needed.
            artist_match = None
            if bg_hex and not completion_match:
                # No completion colour — background IS the artist colour
                artist_match = best_colour_match(bg_hex, artists, "colour_hex")

            artist_name = artist_match["name"] if artist_match else (
                "IN_PROGRESS" if completion_match else "UNASSIGNED"
            )

            tiles.append({
                "tile": cell_value,
                "x": x,
                "y": y,
                "artist": artist_name,
                "background_hex": bg_hex or "#FFFFFF",
                "completion_pct": completion_pct,
                "completion_label": completion_match["label"] if completion_match else (
                    "Not Started" if bg_hex else "Empty"
                ),
                "is_done": completion_pct == 100,
            })

    return tiles


# ── Report Generator ─────────────────────────────────────────────────────────────

def generate_report(tiles: list[dict]) -> pd.DataFrame:
    """Print a clean per-artist progress summary to the console."""
    df = pd.DataFrame(tiles)

    print("\n" + "═" * 60)
    print("  TILEMAP PROGRESS REPORT")
    print("═" * 60)

    # Filter out unassigned/in-progress for the main summary
    assigned = df[~df["artist"].isin(["UNASSIGNED", "IN_PROGRESS", "Empty"])]

    if assigned.empty:
        print("⚠️  No assigned tiles found. Check your Legend colours.")
        return df

    summary = (
        assigned.groupby("artist")
        .agg(total_tiles=("tile", "count"), completed=("is_done", "sum"))
        .assign(remaining=lambda x: x["total_tiles"] - x["completed"])
        .assign(progress_pct=lambda x: (x["completed"] / x["total_tiles"] * 100).round(1))
        .sort_values("progress_pct", ascending=False)
    )

    print(summary.to_string())
    print("═" * 60)

    unassigned_count = len(df[df["artist"] == "UNASSIGNED"])
    in_progress_count = len(df[df["artist"] == "IN_PROGRESS"])

    if unassigned_count:
        print(f"\n⚠️  {unassigned_count} tiles with no artist match (check Legend colours)")
    if in_progress_count:
        print(f"🔄  {in_progress_count} tiles show completion colour (artist obscured — normal)")

    return df


def save_output(df: pd.DataFrame):
    """Save tile-level data to CSV for dashboards or further processing."""
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "progress_report.csv"
    df.to_csv(output_path, index=False)
    print(f"\n💾 Saved to: {output_path}")

    # Also save a clean per-artist summary CSV
    summary_path = output_dir / "artist_summary.csv"
    assigned = df[~df["artist"].isin(["UNASSIGNED", "IN_PROGRESS", "Empty"])]
    if not assigned.empty:
        summary = (
            assigned.groupby("artist")
            .agg(total_tiles=("tile", "count"), completed=("is_done", "sum"))
            .assign(remaining=lambda x: x["total_tiles"] - x["completed"])
            .assign(progress_pct=lambda x: (x["completed"] / x["total_tiles"] * 100).round(1))
            .reset_index()
        )
        summary.to_csv(summary_path, index=False)
        print(f"💾 Summary saved to: {summary_path}")


# ── Entry Point ──────────────────────────────────────────────────────────────────

def main():
    print("🗺️  Tilemap Tracker v2 — Starting...\n")

    sheets_service = get_sheets_service()

    print("📋 Loading legend...")
    artists, completions = load_legend(sheets_service)

    print(f"📡 Fetching tilemap from '{config.TILEMAP_TAB}'...")
    sheet_data = fetch_sheet_with_formatting(sheets_service)

    print("🔍 Processing cells...")
    tiles = process_tilemap(sheet_data, artists, completions)
    print(f"   Found {len(tiles)} valid tile coordinates.")

    df = generate_report(tiles)
    save_output(df)

    print("\n✅ Done.")


if __name__ == "__main__":
    main()
