####### ---  Tilemap Stats Dashboard Web App v50  ------########

## v49 Baseline — artist assignment via cell notes
## v50 Artist filter moved to the top of the page and now drives ALL sections:
##     - Top Stats (tile counts, man days)
##     - Milestone section (only milestones containing that artist's tiles shown)
##     - Bar Graph (counts reflect filtered tiles only)
##     - Visual Tilemap (unchanged behaviour, now driven by the shared filter)
##
##     Strategy: all raw tile data is collected into map_points as before.
##     A single df_map DataFrame is built, then the artist filter is applied once
##     at the top of the UI. Every section below reads from df_filtered.

## NOTES FOR BUGS:
## Tile numbers must be the correct format -94/-263 or they will not be counted/coloured
## Has to be Sheet1 on the Google Sheet, shared with the service account email as Viewer.

## -------------------------------------------------------------------------------------------- ##

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import AuthorizedSession
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import re
import plotly.graph_objects as go

# --- ⚙️ CONFIGURABLE SETTINGS ---
totalTiles = 107
MAN_DAY_MULTIPLIER = 1.85

# 🎨 Completion Key Colors
COMPLETION_KEY = {
    "25%":  "#ff0000",
    "50%":  "#ff9900",
    "75%":  "#ffff00",
    "100%": "#00ff00"
}

# 👤 Assignment Key Colors
ASSIGNMENT_KEY = {
    "Kaya":         "#9900ff",
    "Greg":         "#00ffff",
    "Natalia":      "#ff00ff",
    "Elliott":      "#4285f4",
    "Ryan":         "#674ea7",
    "Iain":         "#a64d79",
    "James H":      "#ea9999",
    "TomH":         "#ffe599",
    "Unassigned":   "#c6d9f0",
    "Not Included": "#b7b7b7"
}

# 📋 Known artist names — only cells whose note matches one of these are tracked.
KNOWN_ARTISTS = [
    "Kaya", "Greg", "Natalia", "Elliott", "Ryan",
    "Iain", "James H", "TomH", "Unassigned", "Not Included"
]
ARTIST_LOOKUP = {a.lower(): a for a in KNOWN_ARTISTS}

# Sync legacy colour variables
COLOR_25   = COMPLETION_KEY["25%"]
COLOR_50   = COMPLETION_KEY["50%"]
COLOR_75   = COMPLETION_KEY["75%"]
COLOR_100  = COMPLETION_KEY["100%"]
COLOR_GRID = '#f8f9fb'


# --- 1. Authenticate ---
@st.cache_resource
def get_creds():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly"
    ]
    if "gcp_service_account" in st.secrets:
        return Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes)
    return Credentials.from_service_account_file("credentials.json", scopes=scopes)


creds   = get_creds()
client  = gspread.authorize(creds)
SHEET_ID = '1DHW5uoNu02xpdsp6PB8OXlSNtD3Ig9PKXThZ5BGDg6g' # Test Sheet
sheet   = client.open_by_key(SHEET_ID).sheet1


# --- 2. Fetch Data ---
@st.cache_data(ttl=60)
def get_dashboard_data():
    creds  = get_creds()
    client = gspread.authorize(creds)
    SHEET_ID = '1DHW5uoNu02xpdsp6PB8OXlSNtD3Ig9PKXThZ5BGDg6g' # Test Sheet

    opened_spreadsheet = client.open_by_key(SHEET_ID)
    main_sheet = opened_spreadsheet.sheet1
    raw_main   = main_sheet.get_all_values()

    # Milestone Fetch
    raw_milestone = []
    try:
        all_sheets = opened_spreadsheet.worksheets()
        target = next((s for s in all_sheets if "Milestone" in s.title), None)
        if target:
            raw_milestone = target.get_all_values()
    except Exception as e:
        print(f"Milestone fetch error: {e}")

    # Formatting + Notes — single API call
    session = AuthorizedSession(creds)
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
        f"?ranges={sheet.title}!A1:AZ100"
        f"&fields=sheets(data(rowData(values(note,userEnteredFormat(backgroundColor),effectiveFormat(backgroundColor),effectiveValue))))"
    )
    response = session.get(url).json()
    return raw_main, raw_milestone, response


# --- 3. Page Setup ---
st.set_page_config(page_title="TileMap Stats Dashboard v50", layout="wide")
st.title("📊 TileMap Stats Dashboard v50")

raw_main, raw_milestone, formatting_response = get_dashboard_data()
row_data = formatting_response.get('sheets', [{}])[0].get('data', [{}])[0].get('rowData', [])


# --- 4. Calibration (unchanged) ---
legend_colors  = {"25": None, "50": None, "75": None, "100": None}
target_labels  = ["0.25", ".25", "25%", "0.5", "0.50", ".5", "50%", "0.75", ".75", "75%", "1", "1.0", "100%"]

for r_idx in range(0, 15):
    if r_idx < len(raw_main):
        for col_idx, text_val in enumerate(raw_main[r_idx]):
            clean_val = str(text_val).strip()
            if clean_val in target_labels:
                label_key = (
                    "25"  if "25"  in clean_val else
                    "50"  if "50"  in clean_val or clean_val in ["0.5", ".5"] else
                    "75"  if "75"  in clean_val else
                    "100"
                )
                for offset in [1, 2]:
                    if col_idx - offset >= 0:
                        cell = row_data[r_idx]['values'][col_idx - offset] if col_idx - offset < len(row_data[r_idx]['values']) else {}
                        bg   = cell.get('userEnteredFormat', {}).get('backgroundColor')
                        if bg and not (bg.get('red', 0) == 1 and bg.get('green', 0) == 1 and bg.get('blue', 0) == 1):
                            legend_colors[label_key] = (bg.get('red', 0), bg.get('green', 0), bg.get('blue', 0))
                            break


# --- 5. Helper Functions ---
def colors_match(rgb1, rgb2, tol=0.1):
    if rgb1 is None or rgb2 is None: return False
    return all(abs(a - b) < tol for a, b in zip(rgb1, rgb2))

def clean_coord(val):
    cleaned = re.sub(r'[^0-9/-]', '', str(val))
    parts   = cleaned.split("/")
    return cleaned if len(parts) == 2 else None

def parse_artist_from_note(note_text: str) -> str | None:
    if not note_text:
        return None
    for line in note_text.strip().splitlines():
        normalised = line.strip().lower()
        if normalised in ARTIST_LOOKUP:
            return ARTIST_LOOKUP[normalised]
    return None

def completion_label(hex_color: str) -> str:
    """Return the completion percentage label for a hex colour, or None."""
    for label, c in COMPLETION_KEY.items():
        if hex_color.lower() == c.lower():
            return label
    return None


# --- 6. Build Full Tile Dataset ---
# Every valid tile coordinate becomes one row in map_points.
# Completion percentage is stored per-tile so we can re-aggregate after filtering.

map_points       = []
tile_color_lookup = {}

for r_idx, row in enumerate(row_data):
    if r_idx < 14 or r_idx >= len(raw_main): continue
    if 'values' not in row: continue

    current_text_row = raw_main[r_idx]
    for c_idx, cell in enumerate(row['values']):
        if c_idx >= len(current_text_row): continue

        tile_name = str(current_text_row[c_idx]).strip()
        coords    = clean_coord(tile_name)
        if not coords:
            continue

        # Background colour
        eff_bg    = cell.get('effectiveFormat', {}).get('backgroundColor', {'red': 1, 'green': 1, 'blue': 1})
        hex_color = mcolors.to_hex((eff_bg.get('red', 0), eff_bg.get('green', 0), eff_bg.get('blue', 0)))
        tile_color_lookup[coords] = hex_color

        # Completion %  — derived from the cell's user-entered background colour
        user_bg   = cell.get('userEnteredFormat', {}).get('backgroundColor')
        comp_pct  = 0
        if user_bg:
            u_rgb = (user_bg.get('red', 0), user_bg.get('green', 0), user_bg.get('blue', 0))
            if sum(u_rgb) < 2.9 and sum(u_rgb) > 0:
                if   colors_match(u_rgb, legend_colors["25"]):  comp_pct = 25
                elif colors_match(u_rgb, legend_colors["50"]):  comp_pct = 50
                elif colors_match(u_rgb, legend_colors["75"]):  comp_pct = 75
                elif colors_match(u_rgb, legend_colors["100"]): comp_pct = 100

        # Artist from note
        note_text = cell.get('note', '')
        artist    = parse_artist_from_note(note_text) or 'Unassigned'

        x_val, y_val = coords.split("/")
        map_points.append({
            'x':       int(x_val),
            'y':       int(y_val),
            'color':   hex_color,
            'name':    tile_name,
            'artist':  artist,
            'comp_pct': comp_pct
        })

df_map = pd.DataFrame(map_points) if map_points else pd.DataFrame(
    columns=['x', 'y', 'color', 'name', 'artist', 'comp_pct']
)


# ════════════════════════════════════════════════════════════════════
#  🎨  ARTIST FILTER  — placed at the top, drives every section below
# ════════════════════════════════════════════════════════════════════

st.divider()

artists_in_data  = sorted(df_map['artist'].dropna().unique().tolist())

selected_artists = st.multiselect(
    "🎨 Filter by Artist  —  all sections below update based on this selection",
    options  = artists_in_data,
    default  = artists_in_data,
    help     = "Select one or more artists. All stats, milestones, the bar graph and the tilemap will reflect only the chosen artists."
)

# Single filtered DataFrame used by every section
df_filtered = df_map[df_map['artist'].isin(selected_artists)].copy() if selected_artists else df_map.iloc[0:0].copy()

# Tile count caption
if selected_artists:
    parts = [f"**{a}**: {len(df_filtered[df_filtered['artist'] == a])}" for a in selected_artists]
    st.caption("  ·  ".join(parts))

st.divider()


# ════════════════════════════════════════════════════════════════════
#  📊  TOP STATS  — counts derived from df_filtered
# ════════════════════════════════════════════════════════════════════

f_25  = int((df_filtered['comp_pct'] == 25).sum())
f_50  = int((df_filtered['comp_pct'] == 50).sum())
f_75  = int((df_filtered['comp_pct'] == 75).sum())
f_100 = int((df_filtered['comp_pct'] == 100).sum())

f_total     = len(df_filtered)
f_remaining = (f_total - f_100) - ((f_25 * 0.25) + (f_50 * 0.5) + (f_75 * 0.75))
f_man_days  = round(f_remaining * MAN_DAY_MULTIPLIER)

m_cols = st.columns(7)
m_cols[0].metric("Tracked Tiles",       f_total)
m_cols[1].metric("Tiles in Progress",   f_25 + f_50 + f_75)
m_cols[2].metric("# Progress at 25%",   f_25)
m_cols[3].metric("# Progress at 50%",   f_50)
m_cols[4].metric("# Progress at 75%",   f_75)
m_cols[5].metric("Tiles Complete",      f_100)
m_cols[6].metric("Man Days Left",       f"{f_man_days}d")

st.divider()


# ════════════════════════════════════════════════════════════════════
#  🚩  MILESTONE TABLE  — only milestones that contain a filtered tile
# ════════════════════════════════════════════════════════════════════

st.subheader("🚩 Milestone Visual Status")

# Set of tile coordinates belonging to the current filter — used for fast lookup
filtered_coords = set(df_filtered['name'].tolist())

if raw_milestone:
    any_shown = False
    for row in raw_milestone[1:]:
        if len(row) < 3: continue
        m_no             = str(row[0]).strip()
        m_expected_count = str(row[1]).strip()
        m_tiles_text     = str(row[2]).strip()
        if not m_no or not m_tiles_text: continue

        found_coords = re.findall(r'-?\d+/-?\d+', m_tiles_text)
        if not found_coords: continue

        # Only render this milestone if at least one tile belongs to a selected artist
        artist_tiles_in_milestone = [c for c in found_coords if c in filtered_coords]
        if not artist_tiles_in_milestone:
            continue

        any_shown    = True
        actual_count = len(found_coords)
        count_display = f"({actual_count} tiles, {len(artist_tiles_in_milestone)} matching filter)"
        if m_expected_count.isdigit() and int(m_expected_count) != actual_count:
            count_display = f"⚠️ Mismatch: Found {actual_count} / Expected {m_expected_count}  ·  {len(artist_tiles_in_milestone)} matching filter"

        html_chips = f"**M{m_no}** {count_display} &nbsp; "

        for c in found_coords:
            bg      = tile_color_lookup.get(c, "#ffffff")
            is_dark = mcolors.rgb_to_hsv(mcolors.to_rgb(bg))[2] < 0.5
            txt     = "white" if is_dark else "black"
            # Dim tiles that don't belong to the current filter so the artist's tiles stand out
            opacity = "1.0" if c in filtered_coords else "0.25"
            html_chips += (
                f'<span style="background-color:{bg}; color:{txt}; opacity:{opacity}; '
                f'padding:2px 6px; border-radius:4px; border:1px solid #ddd; '
                f'margin-right:4px; font-family:monospace; font-size:12px;">{c}</span>'
            )

        st.markdown(html_chips, unsafe_allow_html=True)

    if not any_shown:
        st.info("No milestones contain tiles assigned to the selected artist(s).")
else:
    st.warning("Milestone data not found in the spreadsheet.")

st.divider()


# ════════════════════════════════════════════════════════════════════
#  📈  PROGRESS BAR GRAPH + STATION ASSIGNMENTS
# ════════════════════════════════════════════════════════════════════

col_l, col_r = st.columns([2, 1])

with col_l:
    st.subheader("Progress Distribution")

    labels     = ['25% Done', '50% Done', '75% Done', '100% Done']
    counts     = [f_25, f_50, f_75, f_100]
    bar_colors = [COLOR_25, COLOR_50, COLOR_75, COLOR_100]

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.bar(labels, counts, color=bar_colors, edgecolor='grey')
    ax.bar_label(ax.containers[0], padding=3)
    st.pyplot(fig)

    st.caption("Graph Color Legend (Editable in Script)")
    leg_1, leg_2, leg_3, leg_4 = st.columns(4)
    leg_1.markdown(f"🔴 **25%:** `{COLOR_25}`");  leg_2.markdown(f"🟠 **50%:** `{COLOR_50}`")
    leg_3.markdown(f"🟡 **75%:** `{COLOR_75}`");  leg_4.markdown(f"🟢 **100%:** `{COLOR_100}`")

with col_r:
    st.subheader("Station Assignments")

    stations_data = [
        {
            'Station': str(raw_main[i][2]).strip(),
            'Tile':    str(raw_main[i][3]).strip(),
            'Artist':  str(raw_main[i][4]).strip()
        }
        for i in range(10, min(45, len(raw_main)))
        if len(raw_main[i]) > 4 and str(raw_main[i][2]).strip() not in ['nan', 'None', 'Tile', ""]
    ]

    if stations_data:
        df_stations = pd.DataFrame(stations_data)

        def color_tiles(val):
            bg_color = tile_color_lookup.get(val, "#ffffff")
            if not isinstance(bg_color, str):
                bg_color = "#ffffff"
            rgb        = mcolors.to_rgb(bg_color)
            brightness = mcolors.rgb_to_hsv(rgb)[2]
            text_color = "white" if brightness < 0.5 else "black"
            return f'background-color: {bg_color}; color: {text_color}'

        styled_df = df_stations.style.map(color_tiles, subset=['Tile'])
        st.dataframe(styled_df, hide_index=True, use_container_width=True, height=600)
    else:
        st.write("No station assignments found.")

st.divider()


# ════════════════════════════════════════════════════════════════════
#  🗺️  VISUAL TILEMAP
# ════════════════════════════════════════════════════════════════════

st.subheader("📍 Interactive Visual TileMap")

if not df_map.empty:
    fig_map = go.Figure()

    # Completion Legend
    for label, color in COMPLETION_KEY.items():
        fig_map.add_trace(go.Scatter(
            x=[None], y=[None], mode='markers',
            marker=dict(size=12, symbol='square', color=color),
            legendgroup='Completion',
            legendgrouptitle_text='<b>Completion Key</b>',
            name=label, showlegend=True
        ))

    # Assignment Legend
    for label, color in ASSIGNMENT_KEY.items():
        fig_map.add_trace(go.Scatter(
            x=[None], y=[None], mode='markers',
            marker=dict(size=12, symbol='square', color=color),
            legendgroup='Assignment',
            legendgrouptitle_text='<b>Assignment Key</b>',
            name=label, showlegend=True
        ))

    # Filtered tile data
    if not df_filtered.empty:
        fig_map.add_trace(go.Scatter(
            x=df_filtered['x'],
            y=df_filtered['y'],
            mode='markers',
            marker=dict(
                size=18, symbol='square',
                color=df_filtered['color'],
                line=dict(width=1, color='DarkSlateGrey')
            ),
            text=df_filtered.apply(
                lambda r: f"{r['name']}<br>Artist: {r['artist']}<br>Completion: {r['comp_pct']}%", axis=1
            ),
            hoverinfo='text',
            showlegend=False
        ))

    fig_map.update_layout(
        plot_bgcolor=COLOR_GRID,
        width=1000,
        height=800,
        xaxis=dict(scaleanchor="y", scaleratio=1, side='top'),
        yaxis=dict(autorange="reversed"),
        legend=dict(
            bgcolor="rgba(255, 255, 255, 0.9)",
            bordercolor="DarkSlateGrey",
            borderwidth=1,
            tracegroupgap=80,
            itemsizing='constant',
            itemwidth=40,
            font=dict(family="Arial", size=18, color="black")
        )
    )

    st.plotly_chart(fig_map, use_container_width=True)

else:
    st.warning("No tile map data found.")
