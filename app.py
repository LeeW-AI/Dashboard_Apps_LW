####### ---  Tilemap Stats Dashboard Web App v53  ------########

## v52 Baseline — project timeline, artist remaining days, comments, per-tile days, tile request
## v53 Changes:
##     1. Clicking a tile on the tilemap auto-populates the tile in the sidebar request form
##        via st.session_state + plotly_events (streamlit-plotly-events package).
##     2. Sidebar tile request now supports selecting multiple tiles in one request.
##     3. Artist filter keeps Unassigned visible in the tilemap by default.
##        Stats still exclude Unassigned/Not Included from tracked counts.
##     4. parse_note() now handles 3-line notes: Station / Artist / Days (all optional).
##        Station name is preserved but not used in stats. Days defaults to 1.85.
##     5. Page title shows today's date as a styled date badge (no emoji icon number).

## v52 Changes:
##     1. Project Man Day Progress bar — working days from 3 Mar 2026 to 31 Jul 2026,
##        orange = elapsed, green = remaining. Shown above top stats.
##     2. Artist Remaining Days stat — when filtering by a single artist, shows their
##        remaining work days (tiles * day_value, reduced for in-progress tiles),
##        minus holiday days booked. Shown in green if sufficient time remains,
##        red if they are at risk. Reads from Holidays sheet.
##     3. Comments table — reads/writes to Comments sheet. Shown below the tilemap.
##        Artists can add new comments (tile, artist, comment) and save back to the sheet.
##        Requires spreadsheets (not readonly) scope — see Auth note below.
##     4. Per-tile day values — parsed from cell note alongside artist name.
##        Note format: "Iain\n3.5"  — second line is the day override.
##        Falls back to MAN_DAY_MULTIPLIER (1.85) if no value present.
##     5. Tile access request email — sidebar panel appears when a tile is selected
##        from a dropdown below the map. Pulls artist email from Contacts sheet.
##        Constructs a mailto: link to open the user's email client pre-filled.

## NOTES FOR BUGS:
## Tile numbers must be the correct format -94/-263 or they will not be counted/coloured
## Has to be Sheet1 on the Google Sheet, shared with the service account email.
## For Comments write-back, service account needs EDITOR access (not just Viewer).
## Auth scope must include spreadsheets (not spreadsheets.readonly) for write access.

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
from datetime import date, datetime, timedelta
import numpy as np
import urllib.parse

# streamlit-plotly-events enables click events from Plotly charts back into Streamlit.
# Add to requirements.txt: streamlit-plotly-events
try:
    from streamlit_plotly_events import plotly_events
    PLOTLY_EVENTS_AVAILABLE = True
except ImportError:
    PLOTLY_EVENTS_AVAILABLE = False

# --- ⚙️ CONFIGURABLE SETTINGS ---
MAN_DAY_MULTIPLIER = 1.85

PROJECT_START = date(2026, 3, 3)   # First day of project
PROJECT_END   = date(2026, 7, 31)  # Dev Complete deadline

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
    "JamesH":       "#ea9999",
    "TomH":         "#ffe599",
    "ArtistTBD":    "#cccccc",
    "Unassigned":   "#c6d9f0",
    "Not Included": "#b7b7b7"
}

# 📋 Known artist names — only cells whose note matches one of these are tracked.
KNOWN_ARTISTS = [
    "Kaya", "Greg", "Natalia", "Elliott", "Ryan",
    "Iain", "JamesH", "TomH", "ArtistTBD", "Unassigned", "Not Included"
]
EXCLUDED_FROM_TRACKING = {"Unassigned", "Not Included"}
ARTIST_LOOKUP = {a.lower(): a for a in KNOWN_ARTISTS}

COLOR_25   = COMPLETION_KEY["25%"]
COLOR_50   = COMPLETION_KEY["50%"]
COLOR_75   = COMPLETION_KEY["75%"]
COLOR_100  = COMPLETION_KEY["100%"]
COLOR_GRID = '#f8f9fb'


# ── Auth ─────────────────────────────────────────────────────────────────────────
# NOTE: scope changed from spreadsheets.readonly → spreadsheets for Comments write-back.
@st.cache_resource
def get_creds():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",   # read + write
        "https://www.googleapis.com/auth/drive.readonly"
    ]
    if "gcp_service_account" in st.secrets:
        return Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes)
    return Credentials.from_service_account_file("credentials.json", scopes=scopes)


creds    = get_creds()
client   = gspread.authorize(creds)
SHEET_ID = '1DHW5uoNu02xpdsp6PB8OXlSNtD3Ig9PKXThZ5BGDg6g'  ## Test Sheet
## SHEET_ID = '12FoC4Vz0Yx0WxscjypMM8J3sN7WKaL23LgV6tdAS-Hg'
sheet    = client.open_by_key(SHEET_ID).sheet1


# ── Data Fetch ───────────────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def get_dashboard_data():
    creds   = get_creds()
    client  = gspread.authorize(creds)
    SHEET_ID = '1DHW5uoNu02xpdsp6PB8OXlSNtD3Ig9PKXThZ5BGDg6g'
    ## SHEET_ID = '12FoC4Vz0Yx0WxscjypMM8J3sN7WKaL23LgV6tdAS-Hg'

    opened = client.open_by_key(SHEET_ID)
    raw_main = opened.sheet1.get_all_values()

    raw_milestone, raw_holidays, raw_contacts, raw_comments = [], [], [], []
    try:
        all_sheets = opened.worksheets()
        for ws in all_sheets:
            t = ws.title
            if "Milestone" in t: raw_milestone = ws.get_all_values()
            if "Holiday"   in t: raw_holidays  = ws.get_all_values()
            if "Contact"   in t: raw_contacts  = ws.get_all_values()
            if "Comment"   in t: raw_comments  = ws.get_all_values()
    except Exception as e:
        st.warning(f"Sheet fetch error: {e}")

    session = AuthorizedSession(creds)
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
        f"?ranges={opened.sheet1.title}!A1:AZ100"
        f"&fields=sheets(data(rowData(values(note,userEnteredFormat(backgroundColor),effectiveFormat(backgroundColor),effectiveValue))))"
    )
    response = session.get(url).json()
    return raw_main, raw_milestone, raw_holidays, raw_contacts, raw_comments, response


# ── Working Day Helpers ──────────────────────────────────────────────────────────
def working_days_between(start: date, end: date) -> int:
    """Count working days (Mon–Fri) between start and end inclusive."""
    if end < start:
        return 0
    days = pd.bdate_range(start=start, end=end)
    return len(days)

def working_days_in_ranges(holiday_rows: list, artist_name: str) -> int:
    """
    Total working holiday days for a given artist.
    holiday_rows: list of [artist, start_date_str, end_date_str]
    """
    total = 0
    for row in holiday_rows:
        if len(row) < 3: continue
        if row[0].strip().lower() != artist_name.lower(): continue
        try:
            h_start = datetime.strptime(row[1].strip(), "%d/%m/%Y").date()
            h_end   = datetime.strptime(row[2].strip(), "%d/%m/%Y").date()
            total  += working_days_between(h_start, h_end)
        except ValueError:
            try:
                h_start = datetime.strptime(row[1].strip(), "%Y-%m-%d").date()
                h_end   = datetime.strptime(row[2].strip(), "%Y-%m-%d").date()
                total  += working_days_between(h_start, h_end)
            except ValueError:
                pass
    return total


# ── Page Setup ───────────────────────────────────────────────────────────────────
st.set_page_config(page_title="TileMap Stats Dashboard v53", layout="wide")

# Header with today's date badge instead of a generic icon (#5)
today = date.today()
st.markdown(
    f"""
    <div style="display:flex; align-items:center; gap:16px; margin-bottom:8px;">
      <div style="background:#1a73e8; color:white; border-radius:10px; padding:6px 14px;
                  text-align:center; min-width:60px; font-family:sans-serif; line-height:1.2;">
        <div style="font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:1px;">
          {today.strftime('%b')}
        </div>
        <div style="font-size:26px; font-weight:700; line-height:1;">{today.day}</div>
      </div>
      <div>
        <h2 style="margin:0; padding:0; font-size:1.6rem;">TileMap Stats Dashboard</h2>
        <div style="color:#888; font-size:0.85rem;">v53 · {today.strftime('%A %d %B %Y')}</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# Session state: tracks which tiles the user has clicked/selected for the request form
if 'selected_request_tiles' not in st.session_state:
    st.session_state.selected_request_tiles = []

raw_main, raw_milestone, raw_holidays, raw_contacts, raw_comments, formatting_response = get_dashboard_data()
row_data = formatting_response.get('sheets', [{}])[0].get('data', [{}])[0].get('rowData', [])


# ── Contacts Lookup ──────────────────────────────────────────────────────────────
# Expected: Artist Name | Email  (row 1 = header)
contacts_lookup = {}  # artist_name → email
for row in raw_contacts[1:]:
    if len(row) >= 2 and row[0].strip() and row[1].strip():
        contacts_lookup[row[0].strip()] = row[1].strip()


# ── Calibration (unchanged) ──────────────────────────────────────────────────────
legend_colors = {"25": None, "50": None, "75": None, "100": None}
target_labels = ["0.25", ".25", "25%", "0.5", "0.50", ".5", "50%", "0.75", ".75", "75%", "1", "1.0", "100%"]

for r_idx in range(0, 15):
    if r_idx < len(raw_main):
        for col_idx, text_val in enumerate(raw_main[r_idx]):
            clean_val = str(text_val).strip()
            if clean_val in target_labels:
                label_key = (
                    "25"  if "25" in clean_val else
                    "50"  if "50" in clean_val or clean_val in ["0.5", ".5"] else
                    "75"  if "75" in clean_val else
                    "100"
                )
                for offset in [1, 2]:
                    if col_idx - offset >= 0:
                        cell = row_data[r_idx]['values'][col_idx - offset] if col_idx - offset < len(row_data[r_idx].get('values', [])) else {}
                        bg = cell.get('userEnteredFormat', {}).get('backgroundColor')
                        if bg and not (bg.get('red', 0) == 1 and bg.get('green', 0) == 1 and bg.get('blue', 0) == 1):
                            legend_colors[label_key] = (bg.get('red', 0), bg.get('green', 0), bg.get('blue', 0))
                            break


# ── Helper Functions ─────────────────────────────────────────────────────────────
def colors_match(rgb1, rgb2, tol=0.1):
    if rgb1 is None or rgb2 is None: return False
    return all(abs(a - b) < tol for a, b in zip(rgb1, rgb2))

def clean_coord(val):
    cleaned = re.sub(r'[^0-9/-]', '', str(val))
    parts = cleaned.split("/")
    return cleaned if len(parts) == 2 else None

def parse_note(note_text: str) -> tuple[str | None, float, str | None]:
    """
    Parse a cell note to extract station name, artist name, and optional day override.

    Supported formats (all lines optional, order is: station first if present, then artist, then days):
        "Iain"                  → station=None,       artist="Iain",  days=1.85
        "Iain\\n3.5"            → station=None,       artist="Iain",  days=3.5
        "Station A\\nIain"      → station="Station A", artist="Iain",  days=1.85
        "Station A\\nIain\\n3.5"→ station="Station A", artist="Iain",  days=3.5

    Strategy: scan every line — if it matches a known artist it's the artist,
    if it parses as a float it's the day value, otherwise it's the station name.
    Returns (artist_or_None, day_value, station_or_None).
    """
    if not note_text:
        return None, MAN_DAY_MULTIPLIER, None

    lines   = note_text.strip().splitlines()
    artist  = None
    day_val = MAN_DAY_MULTIPLIER
    station = None

    for line in lines:
        stripped = line.strip()
        norm     = stripped.lower()
        if not stripped:
            continue
        if norm in ARTIST_LOOKUP:
            artist = ARTIST_LOOKUP[norm]
        else:
            try:
                day_val = float(stripped)
            except ValueError:
                # Not an artist name, not a number → treat as station name
                if station is None:
                    station = stripped

    return artist, day_val, station


# ── Build Full Tile Dataset ──────────────────────────────────────────────────────
map_points        = []
tile_color_lookup = {}

for r_idx, row in enumerate(row_data):
    if r_idx < 14 or r_idx >= len(raw_main): continue
    if 'values' not in row: continue

    current_text_row = raw_main[r_idx]
    for c_idx, cell in enumerate(row['values']):
        if c_idx >= len(current_text_row): continue

        tile_name = str(current_text_row[c_idx]).strip()
        coords    = clean_coord(tile_name)
        if not coords: continue

        eff_bg    = cell.get('effectiveFormat', {}).get('backgroundColor', {'red': 1, 'green': 1, 'blue': 1})
        hex_color = mcolors.to_hex((eff_bg.get('red', 0), eff_bg.get('green', 0), eff_bg.get('blue', 0)))
        tile_color_lookup[coords] = hex_color

        user_bg  = cell.get('userEnteredFormat', {}).get('backgroundColor')
        comp_pct = 0
        if user_bg:
            u_rgb = (user_bg.get('red', 0), user_bg.get('green', 0), user_bg.get('blue', 0))
            if sum(u_rgb) < 2.9 and sum(u_rgb) > 0:
                if   colors_match(u_rgb, legend_colors["25"]):  comp_pct = 25
                elif colors_match(u_rgb, legend_colors["50"]):  comp_pct = 50
                elif colors_match(u_rgb, legend_colors["75"]):  comp_pct = 75
                elif colors_match(u_rgb, legend_colors["100"]): comp_pct = 100

        # Parse note → station + artist + per-tile day override (#4)
        note_text               = cell.get('note', '')
        artist, day_val, station = parse_note(note_text)
        artist                  = artist or 'Unassigned'

        x_val, y_val = coords.split("/")
        map_points.append({
            'x':        int(x_val),
            'y':        int(y_val),
            'color':    hex_color,
            'name':     tile_name,
            'artist':   artist,
            'station':  station or '',
            'comp_pct': comp_pct,
            'day_val':  day_val
        })

df_map = pd.DataFrame(map_points) if map_points else pd.DataFrame(
    columns=['x', 'y', 'color', 'name', 'artist', 'station', 'comp_pct', 'day_val']
)


# ════════════════════════════════════════════════════════════════════
#  📅  PROJECT TIMELINE PROGRESS BAR  (#1)
# ════════════════════════════════════════════════════════════════════

st.divider()

total_proj_days     = working_days_between(PROJECT_START, PROJECT_END)
elapsed_proj_days  = working_days_between(PROJECT_START, min(today, PROJECT_END))
remaining_proj_days = max(0, total_proj_days - elapsed_proj_days)
elapsed_pct        = round(elapsed_proj_days / total_proj_days * 100, 1) if total_proj_days else 0

st.subheader("📅 Project Timeline")

proj_cols = st.columns([2, 1, 1, 1])
proj_cols[0].markdown(f"**Dev Complete:** 31 July 2026 &nbsp;·&nbsp; **Start:** 3 March 2026")
proj_cols[1].metric("Total Working Days", total_proj_days)
proj_cols[2].metric("Days Elapsed",       elapsed_proj_days)
proj_cols[3].metric("Days Remaining",     remaining_proj_days)

# Two-tone progress bar: orange = elapsed, green = remaining
bar_html = f"""
<div style="margin: 8px 0 16px 0;">
  <div style="display:flex; height:22px; border-radius:6px; overflow:hidden; border:1px solid #ccc;">
    <div style="width:{elapsed_pct}%; background:#ff9900; display:flex; align-items:center;
                justify-content:center; font-size:11px; color:white; font-weight:bold; min-width:30px;">
      {elapsed_pct}%
    </div>
    <div style="flex:1; background:#00aa44; display:flex; align-items:center;
                justify-content:center; font-size:11px; color:white; font-weight:bold;">
      {round(100 - elapsed_pct, 1)}%
    </div>
  </div>
  <div style="display:flex; justify-content:space-between; font-size:11px; color:#888; margin-top:3px;">
    <span>3 Mar 2026</span><span style="color:#ff9900;">▌ Elapsed</span>
    <span style="color:#00aa44;">Remaining ▐</span><span>31 Jul 2026</span>
  </div>
</div>
"""
st.markdown(bar_html, unsafe_allow_html=True)
st.divider()


# ════════════════════════════════════════════════════════════════════
#  🎨  ARTIST FILTER
# ════════════════════════════════════════════════════════════════════

artists_in_data  = sorted(df_map['artist'].dropna().unique().tolist())

# Unassigned is included in the default selection for tilemap visibility (#3).
# Stats calculations still exclude EXCLUDED_FROM_TRACKING internally.
selected_artists = st.multiselect(
    "🎨 Filter by Artist  —  all sections below update based on this selection",
    options = artists_in_data,
    default = artists_in_data,
    help    = "Unassigned tiles are included by default for tilemap context. Stats exclude Unassigned/Not Included from tracked counts regardless."
)

df_filtered = df_map[df_map['artist'].isin(selected_artists)].copy() if selected_artists else df_map.iloc[0:0].copy()

if selected_artists:
    parts = [f"**{a}**: {len(df_filtered[df_filtered['artist'] == a])}" for a in selected_artists]
    st.caption("  ·  ".join(parts))

st.divider()


# ════════════════════════════════════════════════════════════════════
#  📊  TOP STATS
# ════════════════════════════════════════════════════════════════════

f_25  = int((df_filtered['comp_pct'] == 25).sum())
f_50  = int((df_filtered['comp_pct'] == 50).sum())
f_75  = int((df_filtered['comp_pct'] == 75).sum())
f_100 = int((df_filtered['comp_pct'] == 100).sum())

df_tracked   = df_filtered[~df_filtered['artist'].isin(EXCLUDED_FROM_TRACKING)]
f_tracked    = len(df_tracked)
f_man_days   = round(df_tracked['day_val'].sum())  # uses per-tile day values


# ── Artist Remaining Days (#2) — shown only when a single artist is selected ────
show_artist_remaining = (
    len(selected_artists) == 1 and
    selected_artists[0] not in EXCLUDED_FROM_TRACKING
)

artist_remaining_days = None
artist_has_enough_time = None

if show_artist_remaining:
    solo = selected_artists[0]
    df_solo = df_filtered[~df_filtered['artist'].isin(EXCLUDED_FROM_TRACKING)].copy()

    # Remaining work = full tiles + partial credit for in-progress tiles
    # A tile at 25% done still has 75% of its day_val left, etc.
    def remaining_cost(row):
        done_fraction = row['comp_pct'] / 100.0
        return row['day_val'] * (1.0 - done_fraction)

    df_solo['remaining_cost'] = df_solo.apply(remaining_cost, axis=1)
    raw_remaining = df_solo['remaining_cost'].sum()

    # Deduct holiday working days booked for this artist
    holiday_days      = working_days_in_ranges(raw_holidays[1:], solo)
    artist_remaining_days = max(0, round(raw_remaining - 0))  # work days needed
    # Available working days = project days remaining minus holidays
    available_days    = max(0, remaining_proj_days - holiday_days)
    artist_has_enough_time = available_days >= artist_remaining_days


# Layout: 7 stats + optionally the artist remaining days stat
num_cols = 8 if show_artist_remaining else 7
m_cols   = st.columns(num_cols)

m_cols[0].metric("Tracked Tiles",      f_tracked)
m_cols[1].metric("Tiles in Progress",  f_25 + f_50 + f_75)
m_cols[2].metric("# Progress at 25%",  f_25)
m_cols[3].metric("# Progress at 50%",  f_50)
m_cols[4].metric("# Progress at 75%",  f_75)
m_cols[5].metric("Tiles Complete",     f_100)
m_cols[6].metric("Man Days Total",     f"{f_man_days}d")

if show_artist_remaining:
    colour_css = "color:green;" if artist_has_enough_time else "color:red;"
    status_icon = "✅" if artist_has_enough_time else "⚠️"
    holiday_note = f" ({holiday_days}d holidays deducted)" if holiday_days > 0 else ""
    m_cols[7].markdown(
        f"""<div style='font-size:13px;color:#555;'>Remaining Days {status_icon}</div>
        <div style='font-size:28px;font-weight:bold;{colour_css}'>{artist_remaining_days}d</div>
        <div style='font-size:11px;color:#888;'>{available_days}d available{holiday_note}</div>""",
        unsafe_allow_html=True
    )

st.divider()


# ════════════════════════════════════════════════════════════════════
#  🚩  MILESTONE TABLE
# ════════════════════════════════════════════════════════════════════

st.subheader("🚩 Milestone Visual Status")
filtered_coords = set(df_filtered['name'].tolist())

if raw_milestone:
    any_shown = False
    for row in raw_milestone[1:]:
        if len(row) < 3: continue
        m_no, m_expected_count, m_tiles_text = str(row[0]).strip(), str(row[1]).strip(), str(row[2]).strip()
        if not m_no or not m_tiles_text: continue

        found_coords = re.findall(r'-?\d+/-?\d+', m_tiles_text)
        if not found_coords: continue

        artist_tiles_in_milestone = [c for c in found_coords if c in filtered_coords]
        if not artist_tiles_in_milestone: continue

        any_shown     = True
        actual_count  = len(found_coords)
        count_display = f"({actual_count} tiles, {len(artist_tiles_in_milestone)} matching filter)"
        if m_expected_count.isdigit() and int(m_expected_count) != actual_count:
            count_display = f"⚠️ Mismatch: Found {actual_count} / Expected {m_expected_count}  ·  {len(artist_tiles_in_milestone)} matching filter"

        html_chips = f"**M{m_no}** {count_display} &nbsp; "
        for c in found_coords:
            bg      = tile_color_lookup.get(c, "#ffffff")
            is_dark = mcolors.rgb_to_hsv(mcolors.to_rgb(bg))[2] < 0.5
            txt     = "white" if is_dark else "black"
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
    st.warning("Milestone data not found.")

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
    leg_1.markdown(f"🔴 **25%:** `{COLOR_25}`"); leg_2.markdown(f"🟠 **50%:** `{COLOR_50}`")
    leg_3.markdown(f"🟡 **75%:** `{COLOR_75}`"); leg_4.markdown(f"🟢 **100%:** `{COLOR_100}`")

with col_r:
    st.subheader("Station Assignments")
    stations_data = [
        {'Station': str(raw_main[i][2]).strip(), 'Tile': str(raw_main[i][3]).strip(), 'Artist': str(raw_main[i][4]).strip()}
        for i in range(10, min(45, len(raw_main)))
        if len(raw_main[i]) > 4 and str(raw_main[i][2]).strip() not in ['nan', 'None', 'Tile', ""]
    ]
    if stations_data:
        df_stations = pd.DataFrame(stations_data)
        def color_tiles(val):
            bg_color = tile_color_lookup.get(val, "#ffffff")
            if not isinstance(bg_color, str): bg_color = "#ffffff"
            rgb = mcolors.to_rgb(bg_color)
            brightness = mcolors.rgb_to_hsv(rgb)[2]
            return f'background-color: {bg_color}; color: {"white" if brightness < 0.5 else "black"}'
        styled_df = df_stations.style.map(color_tiles, subset=['Tile'])
        st.dataframe(styled_df, hide_index=True, use_container_width=True, height=600)
    else:
        st.write("No station assignments found.")

st.divider()


# ════════════════════════════════════════════════════════════════════
#  🗺️  VISUAL TILEMAP  +  SIDEBAR TILE REQUEST
# ════════════════════════════════════════════════════════════════════

st.subheader("📍 Interactive Visual TileMap")

# ── Sidebar: Multi-tile Access Request ───────────────────────────────────────────
with st.sidebar:
    st.header("📬 Request Tile Access")
    st.caption(
        "Click tiles on the map to add them to your request, or use the selector below. "
        "Multiple tiles can be included in one request."
    )

    # All requestable tiles (non-excluded)
    requestable_tiles = sorted(
        df_map[~df_map['artist'].isin(EXCLUDED_FROM_TRACKING)]['name'].tolist()
    )

    # Multi-select — pre-populated from map clicks via session state (#1 & #2)
    selected_request_tiles = st.multiselect(
        "Selected Tiles",
        options  = requestable_tiles,
        default  = st.session_state.selected_request_tiles,
        key      = "tile_request_multiselect",
        help     = "Click tiles on the map to add them here, or select manually."
    )
    # Keep session state in sync with the widget
    st.session_state.selected_request_tiles = selected_request_tiles

    if st.button("🗑️ Clear Selection", use_container_width=True):
        st.session_state.selected_request_tiles = []
        st.rerun()

    if selected_request_tiles:
        # Determine the artist(s) for the selected tiles
        selected_rows   = df_map[df_map['name'].isin(selected_request_tiles)]
        artists_for_req = selected_rows['artist'].unique().tolist()

        st.markdown("---")
        for art in artists_for_req:
            art_tiles = selected_rows[selected_rows['artist'] == art]['name'].tolist()
            email     = contacts_lookup.get(art, "")
            st.markdown(f"**{art}** ({len(art_tiles)} tile{'s' if len(art_tiles) > 1 else ''})")
            if email:
                st.caption(f"📧 {email}")
            else:
                st.caption("⚠️ No email on file")

        st.markdown("---")
        requester_name = st.text_input("Your Name", key="req_name")
        req_date_from  = st.date_input("Date From", value=date.today(),        key="req_from")
        req_date_to    = st.date_input("Date To",   value=date.today() + timedelta(days=2), key="req_to")

        if st.button("📧 Generate Request Email(s)", use_container_width=True):
            # Build one mailto per artist (tiles may span multiple artists)
            for art in artists_for_req:
                art_tiles = selected_rows[selected_rows['artist'] == art]['name'].tolist()
                email     = contacts_lookup.get(art, "")
                if not email:
                    st.warning(f"No email for {art} — skipping.")
                    continue

                tile_list = ", ".join(art_tiles)
                subject   = f"Tile Access Request: {tile_list}"
                body = (
                    f"Hi {art},\n\n"
                    f"{requester_name or 'A team member'} is requesting access to the following "
                    f"tile{'s' if len(art_tiles) > 1 else ''}:\n\n"
                    f"{chr(10).join(f'  • {t}' for t in art_tiles)}\n\n"
                    f"Requested dates: {req_date_from.strftime('%d %b %Y')} – {req_date_to.strftime('%d %b %Y')}\n\n"
                    f"Please confirm availability at your earliest convenience.\n\nThanks"
                )
                mailto = (
                    f"mailto:{urllib.parse.quote(email)}"
                    f"?subject={urllib.parse.quote(subject)}"
                    f"&body={urllib.parse.quote(body)}"
                )
                st.markdown(
                    f'<a href="{mailto}" target="_blank">'
                    f'<button style="background:#4285f4;color:white;border:none;padding:8px 16px;'
                    f'border-radius:6px;cursor:pointer;font-size:13px;width:100%;margin-bottom:6px;">'
                    f'📧 Email {art}</button></a>',
                    unsafe_allow_html=True
                )

    st.divider()
    st.caption("💡 Click a tile on the map to auto-add it to the request form.")


# ── Tilemap Figure ────────────────────────────────────────────────────────────────
if not df_map.empty:
    fig_map = go.Figure()

    for label, color in COMPLETION_KEY.items():
        fig_map.add_trace(go.Scatter(
            x=[None], y=[None], mode='markers',
            marker=dict(size=12, symbol='square', color=color),
            legendgroup='Completion', legendgrouptitle_text='<b>Completion Key</b>',
            name=label, showlegend=True
        ))

    for label, color in ASSIGNMENT_KEY.items():
        fig_map.add_trace(go.Scatter(
            x=[None], y=[None], mode='markers',
            marker=dict(size=12, symbol='square', color=color),
            legendgroup='Assignment', legendgrouptitle_text='<b>Assignment Key</b>',
            name=label, showlegend=True
        ))

    if not df_filtered.empty:
        # Highlight any tiles already in the request selection
        marker_sizes  = df_filtered['name'].apply(
            lambda n: 24 if n in st.session_state.selected_request_tiles else 18
        )
        marker_lines  = df_filtered['name'].apply(
            lambda n: dict(width=3, color='#1a73e8') if n in st.session_state.selected_request_tiles
                      else dict(width=1, color='DarkSlateGrey')
        )

        fig_map.add_trace(go.Scatter(
            x=df_filtered['x'], y=df_filtered['y'],
            mode='markers',
            marker=dict(
                size=marker_sizes.tolist(),
                symbol='square',
                color=df_filtered['color'],
                line=dict(
                    width=[m['width'] for m in marker_lines],
                    color=[m['color'] for m in marker_lines]
                )
            ),
            text=df_filtered.apply(
                lambda r: (
                    f"<b>{r['name']}</b><br>"
                    f"Artist: {r['artist']}"
                    + (f"<br>Station: {r['station']}" if r['station'] else "")
                    + f"<br>Completion: {r['comp_pct']}%"
                    f"<br>Day Value: {r['day_val']}"
                    f"<br><i>Click to add to request form</i>"
                ), axis=1
            ),
            customdata=df_filtered['name'],
            hoverinfo='text',
            showlegend=False
        ))

    fig_map.update_layout(
        plot_bgcolor=COLOR_GRID, width=1000, height=800,
        xaxis=dict(scaleanchor="y", scaleratio=1, side='top'),
        yaxis=dict(autorange="reversed"),
        clickmode='event',
        legend=dict(
            bgcolor="rgba(255, 255, 255, 0.9)", bordercolor="DarkSlateGrey",
            borderwidth=1, tracegroupgap=80, itemsizing='constant',
            itemwidth=40, font=dict(family="Arial", size=18, color="black")
        )
    )

    # ── Render with click events if streamlit-plotly-events is available ──────────
    if PLOTLY_EVENTS_AVAILABLE:
        clicked = plotly_events(fig_map, click_event=True, key="tilemap_clicks")
        if clicked:
            for pt in clicked:
                # customdata holds the tile name
                tile_name_clicked = pt.get('customdata')
                if (tile_name_clicked and
                    tile_name_clicked in requestable_tiles and
                    tile_name_clicked not in st.session_state.selected_request_tiles):
                    st.session_state.selected_request_tiles.append(tile_name_clicked)
                    st.rerun()
        st.caption("💡 Click any tile to add it to the sidebar request form.")
    else:
        # Fallback: standard plotly chart (no click events)
        st.plotly_chart(fig_map, use_container_width=True)
        st.caption(
            "ℹ️ Add `streamlit-plotly-events` to requirements.txt to enable "
            "click-to-select tiles on the map."
        )

else:
    st.warning("No tile map data found.")

st.divider()


# ════════════════════════════════════════════════════════════════════
#  💬  COMMENTS TABLE  (#3)
# ════════════════════════════════════════════════════════════════════

st.subheader("💬 Artist Comments")
st.caption("Comments are saved to the Comments sheet. Expected columns: Date | Tile | Artist | Comment")

# ── Display existing comments ─────────────────────────────────────────────────────
if raw_comments and len(raw_comments) > 1:
    df_comments = pd.DataFrame(raw_comments[1:], columns=raw_comments[0] if raw_comments[0] else ["Date", "Tile", "Artist", "Comment"])
    df_comments = df_comments[df_comments.apply(lambda r: any(str(v).strip() for v in r), axis=1)]  # drop blank rows
    st.dataframe(df_comments, use_container_width=True, hide_index=True)
else:
    st.info("No comments yet. Add the first one below.")

# ── Add new comment form ──────────────────────────────────────────────────────────
st.markdown("**Add a Comment**")

comment_cols = st.columns([1, 1, 2, 1])
with comment_cols[0]:
    comment_tile   = st.selectbox("Tile", options=[""] + sorted(df_map['name'].tolist()), key="c_tile")
with comment_cols[1]:
    comment_artist = st.selectbox("Artist", options=[""] + KNOWN_ARTISTS, key="c_artist")
with comment_cols[2]:
    comment_text   = st.text_input("Comment", placeholder="Enter your comment here...", key="c_text")
with comment_cols[3]:
    st.markdown("<br>", unsafe_allow_html=True)
    save_comment   = st.button("💾 Save Comment")

if save_comment:
    if not comment_tile or not comment_artist or not comment_text.strip():
        st.warning("Please fill in Tile, Artist, and Comment before saving.")
    else:
        try:
            creds_write  = get_creds()
            client_write = gspread.authorize(creds_write)
            opened_write = client_write.open_by_key(SHEET_ID)
            all_sheets   = opened_write.worksheets()
            comments_ws  = next((s for s in all_sheets if "Comment" in s.title), None)

            if comments_ws is None:
                st.error("Comments sheet not found. Make sure a sheet with 'Comment' in its name exists.")
            else:
                new_row = [
                    date.today().strftime("%d/%m/%Y"),
                    comment_tile,
                    comment_artist,
                    comment_text.strip()
                ]
                comments_ws.append_row(new_row, value_input_option="USER_ENTERED")
                st.success("✅ Comment saved successfully!")
                st.cache_data.clear()  # refresh so the new comment shows immediately
                st.rerun()
        except Exception as e:
            st.error(f"Failed to save comment: {e}")
