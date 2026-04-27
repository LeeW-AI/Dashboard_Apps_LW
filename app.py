"""
app.py — Tilemap Tracker Dashboard
────────────────────────────────────
Streamlit Cloud entry point.
Fetches data directly from Google Sheets then renders the dashboard —
all in a single process (no subprocess, no local CSV files needed).

Credentials are read from Streamlit Secrets, not credentials.json.
"""

import math
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ── Page Config ─────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Tilemap Tracker",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ── Custom CSS ───────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Inter:wght@300;400;600&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    h1, h2, h3 { font-family: 'Space Mono', monospace; letter-spacing: -0.03em; }
    .stApp { background: #0f1117; color: #e8eaf0; }
    .metric-card {
        background: #1a1d27; border: 1px solid #2a2d3a;
        border-radius: 12px; padding: 1.25rem 1.5rem; margin-bottom: 0.75rem;
    }
    .metric-card h4 {
        margin: 0 0 0.5rem 0; font-size: 0.85rem; color: #8b8fa8;
        font-family: 'Space Mono', monospace; text-transform: uppercase; letter-spacing: 0.08em;
    }
    .metric-card .value { font-size: 2.2rem; font-weight: 600; color: #e8eaf0; line-height: 1; }
    .metric-card .sub { font-size: 0.78rem; color: #6b6f85; margin-top: 0.3rem; }
    .progress-row {
        background: #1a1d27; border: 1px solid #2a2d3a;
        border-radius: 10px; padding: 0.9rem 1.2rem; margin-bottom: 0.5rem;
    }
    .progress-row .artist-name { font-weight: 600; font-size: 0.95rem; margin-bottom: 0.4rem; }
    .progress-bar-bg { background: #2a2d3a; border-radius: 4px; height: 8px; width: 100%; }
    .progress-bar-fill { border-radius: 4px; height: 8px; }
    .section-header {
        font-family: 'Space Mono', monospace; font-size: 0.7rem; text-transform: uppercase;
        letter-spacing: 0.12em; color: #555870; border-bottom: 1px solid #2a2d3a;
        padding-bottom: 0.5rem; margin: 1.5rem 0 1rem 0;
    }
</style>
""", unsafe_allow_html=True)


# ── Config (replaces config.py — edit these values) ─────────────────────────────

SHEET_ID        = st.secrets.get("SHEET_ID", "1DHW5uoNu02xpdsp6PB8OXlSNtD3Ig9PKXThZ5BGDg6g")
TILEMAP_TAB     = st.secrets.get("TILEMAP_TAB", "Airedale_Wharfdale TileMap")
LEGEND_TAB      = st.secrets.get("LEGEND_TAB", "Legend")
TILEMAP_RANGE   = st.secrets.get("TILEMAP_RANGE", "I16:AW48")
LEGEND_RANGE    = st.secrets.get("LEGEND_RANGE", "A1:E12")
COLOUR_TOLERANCE = 15


# ── Auth ─────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_sheets_service():
    """Authenticate using credentials stored in Streamlit Secrets."""
    creds = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
    )
    return build("sheets", "v4", credentials=creds).spreadsheets()


# ── Colour Utilities ─────────────────────────────────────────────────────────────

def rgb_to_hex(r, g, b):
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))

def hex_to_rgb(hex_colour):
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def colour_distance(hex_a, hex_b):
    r1,g1,b1 = hex_to_rgb(hex_a)
    r2,g2,b2 = hex_to_rgb(hex_b)
    return math.sqrt((r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2)

def best_colour_match(target_hex, candidates, key):
    if not target_hex or not candidates:
        return None
    best = min(candidates, key=lambda c: colour_distance(target_hex, c[key]))
    return best if colour_distance(target_hex, best[key]) <= COLOUR_TOLERANCE else None

def extract_background_colour(cell):
    bg = cell.get("effectiveFormat", {}).get("backgroundColor", {})
    r, g, b = bg.get("red", 1.0), bg.get("green", 1.0), bg.get("blue", 1.0)
    if r >= 0.99 and g >= 0.99 and b >= 0.99:
        return None
    return rgb_to_hex(r, g, b)


# ── Data Fetching ────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300, show_spinner=False)  # Cache for 5 minutes
def load_all_data():
    """Fetch legend + tilemap from Google Sheets. Cached for 5 min."""
    service = get_sheets_service()

    # ── Load Legend ──────────────────────────────────────────────────────────────
    legend_result = service.values().get(
        spreadsheetId=SHEET_ID,
        range=f"{LEGEND_TAB}!{LEGEND_RANGE}"
    ).execute()

    legend_rows = legend_result.get("values", [])
    artists, completions = [], []

    for row in legend_rows[1:]:  # skip header
        if len(row) >= 2 and row[0].strip() and row[1].strip():
            artists.append({"name": row[0].strip(), "colour_hex": row[1].strip().upper()})
        if len(row) >= 5 and row[3].strip() and row[4].strip():
            try:
                completions.append({
                    "label": row[3].strip(),
                    "pct": int(row[3].strip().replace("%", "")),
                    "colour_hex": row[4].strip().upper()
                })
            except ValueError:
                pass

    # ── Load Tilemap Grid ────────────────────────────────────────────────────────
    grid_result = service.get(
        spreadsheetId=SHEET_ID,
        ranges=[f"{TILEMAP_TAB}!{TILEMAP_RANGE}"],
        includeGridData=True
    ).execute()

    sheet_data = grid_result["sheets"][0]["data"][0]

    # ── Process Cells ────────────────────────────────────────────────────────────
    tiles = []
    for row_data in sheet_data.get("rowData", []):
        for cell in row_data.get("values", []):
            cell_value = cell.get("formattedValue", "").strip()
            if not cell_value or "/" not in cell_value:
                continue
            parts = cell_value.split("/")
            if len(parts) != 2:
                continue
            try:
                x, y = int(parts[0]), int(parts[1])
            except ValueError:
                continue

            bg_hex = extract_background_colour(cell)

            # Check completion colour first
            completion_match = best_colour_match(bg_hex, completions, "colour_hex") if bg_hex else None
            completion_pct   = completion_match["pct"] if completion_match else 0

            # Then artist colour
            artist_match = None
            if bg_hex and not completion_match:
                artist_match = best_colour_match(bg_hex, artists, "colour_hex")

            artist_name = (
                artist_match["name"] if artist_match
                else "IN_PROGRESS" if completion_match
                else "UNASSIGNED"
            )

            tiles.append({
                "tile": cell_value,
                "x": x, "y": y,
                "artist": artist_name,
                "background_hex": bg_hex or "#FFFFFF",
                "completion_pct": completion_pct,
                "completion_label": completion_match["label"] if completion_match else (
                    "Not Started" if bg_hex else "Empty"
                ),
                "is_done": completion_pct == 100,
            })

    df = pd.DataFrame(tiles)

    # ── Build Summary ────────────────────────────────────────────────────────────
    assigned = df[~df["artist"].isin(["UNASSIGNED", "IN_PROGRESS", "Empty"])]
    summary = None
    if not assigned.empty:
        summary = (
            assigned.groupby("artist")
            .agg(total_tiles=("tile", "count"), completed=("is_done", "sum"))
            .assign(remaining=lambda x: x["total_tiles"] - x["completed"])
            .assign(progress_pct=lambda x: (x["completed"] / x["total_tiles"] * 100).round(1))
            .reset_index()
            .sort_values("progress_pct", ascending=False)
        )

    return df, summary, artists


# ── Header ───────────────────────────────────────────────────────────────────────

st.markdown("# 🗺️ Tilemap Tracker")
st.markdown('<p style="color:#6b6f85;margin-top:-0.5rem;font-size:0.9rem;">UE4 Level Tile Assignment & Progress Dashboard</p>', unsafe_allow_html=True)

# Manual refresh button
col_title, col_btn = st.columns([6, 1])
with col_btn:
    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()

# ── Load Data ────────────────────────────────────────────────────────────────────

with st.spinner("Fetching latest data from Google Sheets..."):
    try:
        tiles_df, summary_df, artists = load_all_data()
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        st.info("Check your Streamlit Secrets — make sure `gcp_service_account` and `SHEET_ID` are set correctly.")
        st.stop()

if tiles_df.empty:
    st.warning("No tile data found. Check your TILEMAP_TAB and TILEMAP_RANGE in Secrets.")
    st.stop()


# ── Top Metrics ──────────────────────────────────────────────────────────────────

total_tiles = len(tiles_df)
done_tiles  = int(tiles_df["is_done"].sum())
n_artists   = summary_df["artist"].nunique() if summary_df is not None else 0
overall_pct = round(done_tiles / total_tiles * 100, 1) if total_tiles else 0

m1, m2, m3, m4 = st.columns(4)

with m1:
    st.markdown(f'<div class="metric-card"><h4>Total Tiles</h4><div class="value">{total_tiles:,}</div><div class="sub">in tracked region</div></div>', unsafe_allow_html=True)
with m2:
    assigned_count = len(tiles_df[~tiles_df["artist"].isin(["UNASSIGNED", "IN_PROGRESS", "Empty"])])
    st.markdown(f'<div class="metric-card"><h4>Assigned</h4><div class="value">{assigned_count:,}</div><div class="sub">across {n_artists} artists</div></div>', unsafe_allow_html=True)
with m3:
    st.markdown(f'<div class="metric-card"><h4>Completed</h4><div class="value">{done_tiles:,}</div><div class="sub">tiles at 100%</div></div>', unsafe_allow_html=True)
with m4:
    colour = "#00C896" if overall_pct >= 75 else "#FFB800" if overall_pct >= 40 else "#FF4B4B"
    st.markdown(f'<div class="metric-card"><h4>Overall Progress</h4><div class="value" style="color:{colour}">{overall_pct}%</div><div class="sub">of assigned tiles done</div></div>', unsafe_allow_html=True)


# ── Main Layout ──────────────────────────────────────────────────────────────────

left_col, right_col = st.columns([1, 2])

# ── Artist Progress Bars ──────────────────────────────────────────────────────

with left_col:
    st.markdown('<div class="section-header">Artist Progress</div>', unsafe_allow_html=True)

    if summary_df is not None:
        for _, row in summary_df.iterrows():
            pct = row["progress_pct"]
            bar_colour = (
                "#00C896" if pct >= 100 else
                "#4CAF50" if pct >= 75  else
                "#FFB800" if pct >= 50  else
                "#FF8C00" if pct >= 25  else
                "#FF4B4B"
            )
            st.markdown(f"""
            <div class="progress-row">
                <div class="artist-name">{row['artist']}</div>
                <div style="display:flex;justify-content:space-between;font-size:0.78rem;color:#8b8fa8;margin-bottom:0.35rem;">
                    <span>{int(row['completed'])}/{int(row['total_tiles'])} tiles</span>
                    <span style="color:{bar_colour};font-weight:600">{pct}%</span>
                </div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" style="width:{pct}%;background:{bar_colour}"></div>
                </div>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No assigned tiles found. Check Legend colours match your sheet.")


# ── Interactive Tilemap ───────────────────────────────────────────────────────

with right_col:
    st.markdown('<div class="section-header">Tilemap View</div>', unsafe_allow_html=True)

    fig = go.Figure()

    for colour, group in tiles_df.groupby("background_hex"):
        if colour == "#FFFFFF":
            continue
        hover = group.apply(
            lambda r: f"<b>{r['tile']}</b><br>Artist: {r['artist']}<br>Completion: {r['completion_label']}",
            axis=1
        )
        fig.add_trace(go.Scatter(
            x=group["x"], y=group["y"],
            mode="markers",
            marker=dict(color=colour, size=10, symbol="square",
                        line=dict(color="#0f1117", width=0.5)),
            hovertemplate="%{text}<extra></extra>",
            text=hover,
            showlegend=False
        ))

    fig.update_layout(
        paper_bgcolor="#0f1117", plot_bgcolor="#1a1d27",
        font=dict(color="#e8eaf0", family="Space Mono"),
        xaxis=dict(showgrid=True, gridcolor="#2a2d3a", zeroline=False, title="X"),
        yaxis=dict(showgrid=True, gridcolor="#2a2d3a", zeroline=False, title="Y"),
        margin=dict(l=20, r=20, t=20, b=20),
        height=480, hovermode="closest"
    )

    st.plotly_chart(fig, width="stretch")


# ── Data Explorer ─────────────────────────────────────────────────────────────

st.markdown('<div class="section-header">Data Explorer</div>', unsafe_allow_html=True)

filter_artist = st.multiselect(
    "Filter by Artist",
    options=sorted(tiles_df["artist"].unique()),
    default=[]
)

display_df = tiles_df if not filter_artist else tiles_df[tiles_df["artist"].isin(filter_artist)]
st.dataframe(
    display_df[["tile", "artist", "completion_pct", "completion_label", "background_hex"]],
    width="stretch", height=280
)

st.markdown(
    f'<p style="color:#333650;font-size:0.75rem;text-align:center;margin-top:2rem;">'
    f'Auto-refreshes every 5 min · {total_tiles} tiles parsed · '
    f'<a href="https://docs.streamlit.io/deploy/streamlit-community-cloud" style="color:#555870">Streamlit Cloud</a></p>',
    unsafe_allow_html=True
)
