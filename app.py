####### ---  Tilemap Stats Dashboard Web App v49  ------########

## v48 Baseline — clean working version
## v49 Artist assignment now reads from cell NOTES instead of border/fill colour.
##     Added Artist filter to the Visual Tilemap section.
##     Only tiles with a note matching the known artist list are tracked per-artist.

## NOTES FOR BUGS:
## Tile numbers must be the correct format -94/-263 or they will not be counted/coloured in the Dashboard
## If the visual tilemap isn't displaying correctly check for tile numbers missing / or should be positive, check the hover stats info
## Has to be Sheet1 on the Google Sheet, has to be shared with the email in the credentials file as a Viewer.

## -------------------------------------------------------------------------------------------- ##

import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import AuthorizedSession
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import re
import numpy as np
import plotly.graph_objects as go
import os

# --- ⚙️ CONFIGURABLE SETTINGS ---
totalTiles = 107
MAN_DAY_MULTIPLIER = 1.85

# 🎨 Completion Key Colors
COMPLETION_KEY = {
    "25%": "#ff0000",
    "50%": "#ff9900",
    "75%": "#ffff00",
    "100%": "#00ff00"
}

# 👤 Assignment Key Colors
ASSIGNMENT_KEY = {
    "Kaya": "#9900ff",
    "Greg": "#00ffff",
    "Natalia": "#ff00ff",
    "Elliott": "#4285f4",
    "Ryan": "#674ea7",
    "Iain": "#a64d79",
    "James H": "#ea9999",
    "TomH": "#ffe599",
    "Unassigned": "#c6d9f0",
    "Not Included": "#b7b7b7"
}

# 📋 Known artist names — only cells whose note matches one of these are tracked.
# Matching is case-insensitive and strips whitespace.
KNOWN_ARTISTS = [
    "Kaya", "Greg", "Natalia", "Elliott", "Ryan",
    "Iain", "James H", "TomH", "Unassigned", "Not Included"
]

# Build a lowercase lookup for fast normalisation: "james h" → "James H"
ARTIST_LOOKUP = {a.lower(): a for a in KNOWN_ARTISTS}

# Sync legacy variables for bar graph logic
COLOR_25 = COMPLETION_KEY["25%"]
COLOR_50 = COMPLETION_KEY["50%"]
COLOR_75 = COMPLETION_KEY["75%"]
COLOR_100 = COMPLETION_KEY["100%"]
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


creds = get_creds()
client = gspread.authorize(creds)
SHEET_ID = '1DHW5uoNu02xpdsp6PB8OXlSNtD3Ig9PKXThZ5BGDg6g'  ## Proper Sheet
sheet = client.open_by_key(SHEET_ID).sheet1


# --- 2. Fetch Data ---
@st.cache_data(ttl=60)
def get_dashboard_data():
    creds = get_creds()
    client = gspread.authorize(creds)
    SHEET_ID = '1DHW5uoNu02xpdsp6PB8OXlSNtD3Ig9PKXThZ5BGDg6g'  ## Proper Sheet

    opened_spreadsheet = client.open_by_key(SHEET_ID)
    main_sheet = opened_spreadsheet.sheet1
    raw_main = main_sheet.get_all_values()

    # Milestone Fetch
    raw_milestone = []
    try:
        all_sheets = opened_spreadsheet.worksheets()
        target = next((s for s in all_sheets if "Milestone" in s.title), None)
        if target:
            raw_milestone = target.get_all_values()
    except Exception as e:
        print(f"Milestone fetch error: {e}")

    # Formatting + Notes Fetch
    # Added 'note' to the fields so cell notes (artist assignments) come back
    # alongside the existing colour data in a single API call.
    session = AuthorizedSession(creds)
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
        f"?ranges={sheet.title}!A1:AZ100"
        f"&fields=sheets(data(rowData(values(note,userEnteredFormat(backgroundColor),effectiveFormat(backgroundColor),effectiveValue))))"
    )
    response = session.get(url).json()
    return raw_main, raw_milestone, response


st.set_page_config(page_title="TileMap Stats Dashboard v49", layout="wide")
st.title("📊 TileMap Stats Dashboard v49")

raw_main, raw_milestone, formatting_response = get_dashboard_data()
row_data = formatting_response.get('sheets', [{}])[0].get('data', [{}])[0].get('rowData', [])


# --- 3. Step A: Calibration (unchanged from v48) ---
legend_colors = {"25": None, "50": None, "75": None, "100": None}
target_labels = ["0.25", ".25", "25%", "0.5", "0.50", ".5", "50%", "0.75", ".75", "75%", "1", "1.0", "100%"]

for r_idx in range(0, 15):
    if r_idx < len(raw_main):
        for col_idx, text_val in enumerate(raw_main[r_idx]):
            clean_val = str(text_val).strip()
            if clean_val in target_labels:
                label_key = "25" if "25" in clean_val else "50" if "50" in clean_val or clean_val in ["0.5", ".5"] else "75" if "75" in clean_val else "100"
                for offset in [1, 2]:
                    if col_idx - offset >= 0:
                        cell = row_data[r_idx]['values'][col_idx - offset] if col_idx - offset < len(row_data[r_idx]['values']) else {}
                        bg = cell.get('userEnteredFormat', {}).get('backgroundColor')
                        if bg and not (bg.get('red', 0) == 1 and bg.get('green', 0) == 1 and bg.get('blue', 0) == 1):
                            legend_colors[label_key] = (bg.get('red', 0), bg.get('green', 0), bg.get('blue', 0))
                            break


# --- 4. Step B: Processing ---
tiles_25 = tiles_50 = tiles_75 = tiles_100 = 0
map_points = []
tile_color_lookup = {}


def colors_match(rgb1, rgb2, tol=0.1):
    if rgb1 is None or rgb2 is None: return False
    return all(abs(a - b) < tol for a, b in zip(rgb1, rgb2))


def clean_coord(val):
    cleaned = re.sub(r'[^0-9/-]', '', str(val))
    parts = cleaned.split("/")
    return cleaned if len(parts) == 2 else None


def parse_artist_from_note(note_text: str) -> str | None:
    """
    Extract a known artist name from a cell note.
    Strips whitespace, lowercases, and checks against ARTIST_LOOKUP.
    Returns the canonical artist name (e.g. 'James H') or None if no match.
    """
    if not note_text:
        return None
    # The note may contain additional text beyond just the artist name.
    # Check each line and each word group for a match.
    for line in note_text.strip().splitlines():
        normalised = line.strip().lower()
        if normalised in ARTIST_LOOKUP:
            return ARTIST_LOOKUP[normalised]
    return None


for r_idx, row in enumerate(row_data):
    if r_idx < 14 or r_idx >= len(raw_main): continue
    if 'values' in row:
        current_text_row = raw_main[r_idx]
        for c_idx, cell in enumerate(row['values']):

            # Completion colour counting (unchanged from v48)
            user_bg = cell.get('userEnteredFormat', {}).get('backgroundColor')
            if user_bg:
                u_rgb = (user_bg.get('red', 0), user_bg.get('green', 0), user_bg.get('blue', 0))
                if sum(u_rgb) < 2.9 and sum(u_rgb) > 0:
                    if colors_match(u_rgb, legend_colors["25"]):   tiles_25 += 1
                    elif colors_match(u_rgb, legend_colors["50"]): tiles_50 += 1
                    elif colors_match(u_rgb, legend_colors["75"]): tiles_75 += 1
                    elif colors_match(u_rgb, legend_colors["100"]): tiles_100 += 1

            # TileMap Points — now also reads the cell note for artist name
            if c_idx < len(current_text_row):
                tile_name = str(current_text_row[c_idx]).strip()
                coords = clean_coord(tile_name)
                if coords:
                    eff_bg = cell.get('effectiveFormat', {}).get('backgroundColor', {'red': 1, 'green': 1, 'blue': 1})
                    hex_color = mcolors.to_hex((
                        eff_bg.get('red', 0),
                        eff_bg.get('green', 0),
                        eff_bg.get('blue', 0)
                    ))

                    # Read the cell note and resolve to a known artist (or None)
                    note_text = cell.get('note', '')
                    artist = parse_artist_from_note(note_text)

                    tile_color_lookup[coords] = hex_color

                    x_val, y_val = coords.split("/")

                    map_points.append({
                        'x': int(x_val),
                        'y': int(y_val),
                        'color': hex_color,
                        'name': tile_name,
                        'artist': artist or 'Unassigned'  # fallback if note is blank/unrecognised
                    })


# --- 5. UI Build ---
remaining_work = (totalTiles - tiles_100) - ((tiles_25 * 0.25) + (tiles_50 * 0.5) + (tiles_75 * 0.75))
man_days = round(remaining_work * MAN_DAY_MULTIPLIER)

st.divider()

m_cols = st.columns(7)
m_cols[0].metric("Track Tiles", totalTiles)
m_cols[1].metric("Tiles in Progress", tiles_25 + tiles_50 + tiles_75)
m_cols[2].metric("# Progress at 25%", tiles_25)
m_cols[3].metric("# Progress at 50%", tiles_50)
m_cols[4].metric("# Progress at 75%", tiles_75)
m_cols[5].metric("Tiles Complete", tiles_100)
m_cols[6].metric("Man Days Left", f"{man_days}d")

st.divider()


# --- 6. Milestone Table (unchanged from v48) ---
st.subheader("🚩 Milestone Visual Status")
if raw_milestone:
    for row in raw_milestone[1:]:
        if len(row) >= 3:
            m_no = str(row[0]).strip()
            m_expected_count = str(row[1]).strip()
            m_tiles_text = str(row[2]).strip()

            if not m_no or not m_tiles_text: continue

            found_coords = re.findall(r'-?\d+/-?\d+', m_tiles_text)
            actual_count = len(found_coords)

            if found_coords:
                count_display = f"({actual_count} tiles)"
                if m_expected_count.isdigit() and int(m_expected_count) != actual_count:
                    count_display = f"⚠️ Mismatch: Found {actual_count} / Expected {m_expected_count}"

                html_chips = f"**M{m_no}** {count_display} &nbsp; "

                for c in found_coords:
                    bg = tile_color_lookup.get(c, "#ffffff")
                    is_dark = mcolors.rgb_to_hsv(mcolors.to_rgb(bg))[2] < 0.5
                    txt = "white" if is_dark else "black"
                    html_chips += (
                        f'<span style="background-color:{bg}; color:{txt}; padding:2px 6px; '
                        f'border-radius:4px; border:1px solid #ddd; margin-right:4px; '
                        f'font-family:monospace; font-size:12px;">{c}</span>'
                    )

                st.markdown(html_chips, unsafe_allow_html=True)
else:
    st.warning("Milestone data not found in the spreadsheet.")

st.divider()


# --- 7. Progress and Station Assignment Tables (unchanged from v48) ---
col_l, col_r = st.columns([2, 1])

with col_l:
    st.subheader("Progress Distribution")
    labels = ['25% Done', '50% Done', '75% Done', '100% Done']
    counts = [tiles_25, tiles_50, tiles_75, tiles_100]
    bar_colors = [COLOR_25, COLOR_50, COLOR_75, COLOR_100]

    fig, ax = plt.subplots(figsize=(10, 7))
    ax.bar(labels, counts, color=bar_colors, edgecolor='grey')
    ax.bar_label(ax.containers[0], padding=3)
    st.pyplot(fig)

    st.caption("Graph Color Legend (Editable in Script)")
    leg_1, leg_2, leg_3, leg_4 = st.columns(4)
    leg_1.markdown(f"🔴 **25%:** `{COLOR_25}`"); leg_2.markdown(f"🟠 **50%:** `{COLOR_50}`")
    leg_3.markdown(f"🟡 **75%:** `{COLOR_75}`"); leg_4.markdown(f"🟢 **100%:** `{COLOR_100}`")

with col_r:
    st.subheader("Station Assignments")

    stations_data = [
        {
            'Station': str(raw_main[i][2]).strip(),
            'Tile': str(raw_main[i][3]).strip(),
            'Artist': str(raw_main[i][4]).strip()
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
            rgb = mcolors.to_rgb(bg_color)
            brightness = mcolors.rgb_to_hsv(rgb)[2]
            text_color = "white" if brightness < 0.5 else "black"
            return f'background-color: {bg_color}; color: {text_color}'

        styled_df = df_stations.style.map(color_tiles, subset=['Tile'])
        st.dataframe(styled_df, hide_index=True, use_container_width=True, height=600)
    else:
        st.write("No station assignments found.")

st.divider()


# --- 8. Visual Tilemap with Artist Filter ---
st.subheader("📍 Interactive Visual TileMap")

if map_points:
    df_map = pd.DataFrame(map_points)

    # ── Artist Filter ────────────────────────────────────────────────────────────
    # Only show artists that actually appear in the current tile data.
    # "All Artists" is always the default — selecting specific names narrows the map.
    artists_in_data = sorted(df_map['artist'].dropna().unique().tolist())

    selected_artists = st.multiselect(
        "🎨 Filter by Artist",
        options=artists_in_data,
        default=artists_in_data,
        help="Select one or more artists to highlight their tiles. Deselect all to hide all tiles."
    )

    # Apply filter — tiles not matching the selection are hidden from the plot
    df_filtered = df_map[df_map['artist'].isin(selected_artists)] if selected_artists else df_map.iloc[0:0]

    # Show a small summary count beneath the filter
    if selected_artists:
        summary_parts = []
        for artist in selected_artists:
            count = len(df_map[df_map['artist'] == artist])
            summary_parts.append(f"**{artist}**: {count}")
        st.caption("  ·  ".join(summary_parts))

    # ── Build Figure ─────────────────────────────────────────────────────────────
    fig_map = go.Figure()

    # Completion Legend (dummy traces)
    for label, color in COMPLETION_KEY.items():
        fig_map.add_trace(go.Scatter(
            x=[None], y=[None], mode='markers',
            marker=dict(size=12, symbol='square', color=color),
            legendgroup='Completion',
            legendgrouptitle_text='<b>Completion Key</b>',
            name=label, showlegend=True
        ))

    # Assignment Legend (dummy traces)
    for label, color in ASSIGNMENT_KEY.items():
        fig_map.add_trace(go.Scatter(
            x=[None], y=[None], mode='markers',
            marker=dict(size=12, symbol='square', color=color),
            legendgroup='Assignment',
            legendgrouptitle_text='<b>Assignment Key</b>',
            name=label, showlegend=True
        ))

    # Actual tile data — filtered
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
            # Hover shows tile coordinate + artist name from note
            text=df_filtered.apply(
                lambda r: f"{r['name']}<br>Artist: {r['artist']}", axis=1
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
