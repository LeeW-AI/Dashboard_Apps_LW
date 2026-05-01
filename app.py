####### ---  Tilemap Stats Dashboard Web App v57  ------########

## v56 Baseline — sidebar-only tile request, cleaned up UI
## v57 Changes:
##     1. Unassigned in artist filter only affects tilemap — never counted in stats
##     2. Comment form fields clear after successful save (session state counter trick)
##     3. Delete button per comment row with confirmation dialog
##     4. Holiday date parser handles "22 April" format (no year) with alias map
##        for artist name mismatches (e.g. "James" in sheet → "JamesH" in code)
##.    5. Added some more text to say there is a small delay when updating the Comments table.


## v53 Baseline — date badge header, 3-line note parsing, multi-tile request, Unassigned filter fix
## v54 Changes:
##     1. Removed streamlit-plotly-events entirely — broke the tilemap display.
##        Tile selection now uses a searchable multiselect below the map instead.
##     2. Comments sheet column order fixed: Date | Artist Name | Tile | Comment
##     3. parse_note() debug-hardened — strips whitespace/newlines more aggressively
##        to fix day value not being picked up from notes with trailing spaces.
##     4. Email request now shows both a mailto: button (iPad/desktop mail client)
##        AND a Gmail web compose link for browser-based Gmail users.
##     5. Holidays stat added to artist stats panel — shows upcoming holiday days
##        from today onwards for the filtered artist.

## v53 Changes:
##     1. Clicking a tile on the tilemap auto-populates the tile in the sidebar request form
##     2. Sidebar tile request now supports selecting multiple tiles in one request.
##     3. Artist filter keeps Unassigned visible in the tilemap by default.
##     4. parse_note() now handles 3-line notes: Station / Artist / Days (all optional).
##     5. Page title shows today's date as a styled date badge.

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
            if "Holidays"   in t: raw_holidays  = ws.get_all_values()
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

# Maps artist names as they appear in the Holidays sheet → canonical KNOWN_ARTISTS name.
# Add any mismatches here without touching the rest of the code.
HOLIDAY_NAME_ALIASES = {
    "james":  "JamesH",
    "jamesh": "JamesH",
    "iain":   "Iain",
}

def working_days_in_ranges(holidays_rows: list, artist_name: str, from_date: date | None = None) -> int:
    """
    Total holiday days for a given artist from the Holidays sheet.
    Sheet columns: Artist | Start Date | End Date | Days

    Date formats handled (all tried in order):
        "22 April"        → assumes PROJECT_END year (2026)
        "22 April 2026"   → explicit year
        "22/04/2026"      → DD/MM/YYYY
        "2026-04-22"      → ISO

    Uses the Days column directly when present.
    If from_date is set, only counts holidays that end on or after from_date.
    Artist name is matched via HOLIDAY_NAME_ALIASES for sheet↔code mismatches.
    """
    def parse_holiday_date(s: str) -> date | None:
        s = s.strip()
        if not s:
            return None
        year = PROJECT_END.year   # default year when none is given in the cell
        for fmt in (
            "%d %B %Y",   # "22 April 2026"
            "%d %B",      # "22 April"  ← main format seen in the sheet
            "%d/%m/%Y",   # "22/04/2026"
            "%d-%m-%Y",   # "22-04-2026"
            "%Y-%m-%d",   # "2026-04-22"
        ):
            try:
                d = datetime.strptime(s, fmt)
                # If year wasn't in the format string, apply the default year
                if "%Y" not in fmt:
                    d = d.replace(year=year)
                return d.date()
            except ValueError:
                continue
        return None

    # Normalise the target artist name via aliases
    canonical = artist_name.strip().lower()
    canonical = HOLIDAY_NAME_ALIASES.get(canonical, artist_name)  # resolve alias
    canonical_lower = canonical.lower()

    total = 0
    for row in holidays_rows:
        if len(row) < 3:
            continue

        # Match sheet artist name → canonical name via alias, then compare
        sheet_artist = row[0].strip()
        resolved     = HOLIDAY_NAME_ALIASES.get(sheet_artist.lower(), sheet_artist)
        if resolved.lower() != canonical_lower:
            continue

        h_start = parse_holiday_date(row[1])
        h_end   = parse_holiday_date(row[2]) if len(row) > 2 else None
        if not h_start or not h_end:
            continue

        # Skip holidays that ended before our from_date filter
        if from_date and h_end < from_date:
            continue

        # Use Days column if valid
        if len(row) >= 4 and row[3].strip():
            try:
                days = float(row[3].strip())
                if from_date and h_start < from_date:
                    # Partially past — recalculate from from_date
                    total += working_days_between(from_date, h_end)
                else:
                    total += int(days)
                continue
            except ValueError:
                pass

        # Fallback: count working days from range
        effective_start = max(h_start, from_date) if from_date else h_start
        total += working_days_between(effective_start, h_end)

    return total


# ── Page Setup ───────────────────────────────────────────────────────────────────
st.set_page_config(page_title="TileMap Stats Dashboard v57", layout="wide")

# Header with today's date badge
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
        <div style="color:#888; font-size:0.85rem;">v57 · {today.strftime('%A %d %B %Y')}</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True
)

# Session state: tracks which tiles the user has clicked/selected for the request form
if 'selected_request_tiles' not in st.session_state:
    st.session_state.selected_request_tiles = []

# Comment form key counter — incrementing this forces Streamlit to reset the widgets (#2)
if 'comment_form_key' not in st.session_state:
    st.session_state.comment_form_key = 0

# Delete confirmation state: stores the row index pending confirmation (#3)
if 'delete_confirm_row' not in st.session_state:
    st.session_state.delete_confirm_row = None

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

    Handles two formats:
      Multi-line (one value per line, any order):
        "Leeds"              → station="Leeds", artist=None,        days=1.85
        "Leeds\nIain\n2.5"  → station="Leeds", artist="Iain",      days=2.5
        "Iain\n2.5 days"    → station=None,    artist="Iain",      days=2.5

      Single-line space-separated (legacy):
        "Leeds ArtistTBD 2.5 days" → station="Leeds", artist="ArtistTBD", days=2.5

    Robustness:
      - Strips trailing "days" / "day" suffix from numeric tokens (case-insensitive)
      - Handles comma decimal separators (e.g. "2,5")
      - Strips CRLF line endings from Google Sheets
    """
    if not note_text:
        return None, MAN_DAY_MULTIPLIER, None

    def try_parse_float(s: str) -> float | None:
        """Strip 'days'/'day' suffix then try float parse."""
        s = re.sub(r'\s*(days?)\s*$', '', s.strip(), flags=re.IGNORECASE)
        s = s.replace(',', '.')
        try:
            return float(s)
        except ValueError:
            return None

    # Normalise — replace CRLF, then try both multi-line and single-line
    normalised = note_text.replace('\r', '').strip()

    # Collect all tokens: split by newlines first, then by spaces within each line
    tokens = []
    for line in normalised.splitlines():
        line = line.strip()
        if not line:
            continue
        # If the line contains a known artist name exactly, keep as one token
        if line.lower() in ARTIST_LOOKUP:
            tokens.append(line)
        else:
            # Split the line into individual words/tokens for single-line format
            tokens.extend(line.split())

    artist  = None
    day_val = MAN_DAY_MULTIPLIER
    station_parts = []

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        # Check artist — try progressively longer phrases (handles "James H")
        matched_artist = None
        for length in range(3, 0, -1):
            phrase = ' '.join(tokens[i:i+length]).strip()
            if phrase.lower() in ARTIST_LOOKUP:
                matched_artist = ARTIST_LOOKUP[phrase.lower()]
                i += length
                break

        if matched_artist:
            artist = matched_artist
            continue

        # Check numeric (day value) — may be followed by "days"
        num = try_parse_float(tok)
        if num is not None:
            day_val = num
            i += 1
            # Consume a trailing standalone "days"/"day" token if present
            if i < len(tokens) and re.fullmatch(r'days?', tokens[i], re.IGNORECASE):
                i += 1
            continue

        # Skip standalone "days"/"day" that wasn't consumed above
        if re.fullmatch(r'days?', tok, re.IGNORECASE):
            i += 1
            continue

        # Everything else is part of the station name
        station_parts.append(tok)
        i += 1

    station = ' '.join(station_parts) if station_parts else None
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
proj_cols[0].markdown(f"**Start:** 3 March 2026 &nbsp;·&nbsp; **Dev Complete:** 31 July 2026") # updated for v56
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

# Stats are always computed from non-excluded artists only (#1)
# Unassigned may be in df_filtered for tilemap display but must never enter stats
df_stats = df_filtered[~df_filtered['artist'].isin(EXCLUDED_FROM_TRACKING)].copy()

if selected_artists:
    # Caption shows counts only for real artists (not Unassigned)
    real_selected = [a for a in selected_artists if a not in EXCLUDED_FROM_TRACKING]
    parts = [f"**{a}**: {len(df_stats[df_stats['artist'] == a])}" for a in real_selected]
    if parts:
        st.caption("  ·  ".join(parts))

st.divider()


# ════════════════════════════════════════════════════════════════════
#  📊  TOP STATS
# ════════════════════════════════════════════════════════════════════

# All stats come from df_stats (already excludes EXCLUDED_FROM_TRACKING)
f_tracked  = len(df_stats)
f_man_days = round(df_stats['day_val'].sum())
f_25  = int((df_stats['comp_pct'] == 25).sum())
f_50  = int((df_stats['comp_pct'] == 50).sum())
f_75  = int((df_stats['comp_pct'] == 75).sum())
f_100 = int((df_stats['comp_pct'] == 100).sum())


# Artist remaining days — only when exactly one real (non-excluded) artist is selected
real_selected_artists = [a for a in selected_artists if a not in EXCLUDED_FROM_TRACKING]
show_artist_remaining = (len(real_selected_artists) == 1)

artist_remaining_days  = None
artist_has_enough_time = None
upcoming_holiday_days  = 0
holiday_days_total     = 0

if show_artist_remaining:
    solo    = real_selected_artists[0]
    df_solo = df_stats.copy()   # already scoped to selected artists, excl. Unassigned

    def remaining_cost(row):
        done_fraction = row['comp_pct'] / 100.0
        return row['day_val'] * (1.0 - done_fraction)

    df_solo['remaining_cost'] = df_solo.apply(remaining_cost, axis=1)
    raw_remaining = df_solo['remaining_cost'].sum()

    holiday_days_total    = working_days_in_ranges(raw_holidays[1:], solo)
    upcoming_holiday_days = working_days_in_ranges(raw_holidays[1:], solo, from_date=today)

    artist_remaining_days  = max(0, round(raw_remaining))
    available_days         = max(0, remaining_proj_days - holiday_days_total)
    artist_has_enough_time = available_days >= artist_remaining_days


# Layout: base 7 stats + 2 extra when single artist selected (remaining days + holidays)
num_cols = 9 if show_artist_remaining else 7
m_cols   = st.columns(num_cols)

m_cols[0].metric("Tracked Tiles",      f_tracked)
m_cols[1].metric("Tiles in Progress",  f_25 + f_50 + f_75)
m_cols[2].metric("# Progress at 25%",  f_25)
m_cols[3].metric("# Progress at 50%",  f_50)
m_cols[4].metric("# Progress at 75%",  f_75)
m_cols[5].metric("Tiles Complete",     f_100)
m_cols[6].metric("Man Days Total",     f"{f_man_days}d")

if show_artist_remaining:
    colour_css  = "color:green;" if artist_has_enough_time else "color:red;"
    status_icon = "✅" if artist_has_enough_time else "⚠️"
    holiday_note = f"({holiday_days_total}d total deducted)" if holiday_days_total > 0 else "no holidays booked"
    m_cols[7].markdown(
        f"""<div style='font-size:13px;color:#555;'>Remaining Days {status_icon}</div>
        <div style='font-size:28px;font-weight:bold;{colour_css}'>{artist_remaining_days}d</div>
        <div style='font-size:11px;color:#888;'>{available_days}d available · {holiday_note}</div>""",
        unsafe_allow_html=True
    )
    # Upcoming holidays stat (#5)
    hol_colour = "#e67e00" if upcoming_holiday_days > 0 else "#888"
    m_cols[8].markdown(
        f"""<div style='font-size:13px;color:#555;'>🏖️ Upcoming Holidays</div>
        <div style='font-size:28px;font-weight:bold;color:{hol_colour}'>{upcoming_holiday_days}d</div>
        <div style='font-size:11px;color:#888;'>from today onwards</div>""",
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
    st.caption("Select tiles using the dropdown list below, then fill in the form.")

    # Requestable tiles: exclude Unassigned and Not Included (#2)
    requestable_tiles = sorted(
        df_map[~df_map['artist'].isin(EXCLUDED_FROM_TRACKING)]['name'].tolist()
    )

    # Multi-select driven by session state — populated from the selector below the map
    selected_request_tiles = st.multiselect(
        "Selected Tiles",
        options = requestable_tiles,
        default = st.session_state.selected_request_tiles,
        key     = "tile_request_multiselect",
        help    = "Pick tiles directly from the list."
    )
    st.session_state.selected_request_tiles = selected_request_tiles

    if selected_request_tiles:
        selected_rows   = df_map[df_map['name'].isin(selected_request_tiles)]
        artists_for_req = selected_rows['artist'].unique().tolist()

        st.markdown("---")
        for art in artists_for_req:
            art_tiles = selected_rows[selected_rows['artist'] == art]['name'].tolist()
            email     = contacts_lookup.get(art, "")
            st.markdown(f"**{art}** — {len(art_tiles)} tile{'s' if len(art_tiles) > 1 else ''}")
            if email:
                st.caption(f"📧 {email}")
            else:
                st.caption("⚠️ No email on file")

        st.markdown("---")
        requester_name = st.text_input("Your Name", key="req_name")
        req_date_from  = st.date_input("Date From", value=today,                         key="req_from")
        req_date_to    = st.date_input("Date To",   value=today + timedelta(days=2),     key="req_to")

        if st.button("📧 Prepare Emails", use_container_width=True):
            for art in artists_for_req:
                art_tiles = selected_rows[selected_rows['artist'] == art]['name'].tolist()
                email     = contacts_lookup.get(art, "")
                if not email:
                    st.warning(f"No email for {art} — skipping.")
                    continue

                tile_list = ", ".join(art_tiles)
                subject   = f"Tile Access Request: {tile_list}"
                body_plain = (
                    f"Hi {art},\n\n"
                    f"{requester_name or 'A team member'} is requesting access to the "
                    f"following tile{'s' if len(art_tiles) > 1 else ''}:\n\n"
                    + "\n".join(f"  • {t}" for t in art_tiles)
                    + f"\n\nRequested dates: {req_date_from.strftime('%d %b %Y')} – {req_date_to.strftime('%d %b %Y')}"
                    + "\n\nPlease confirm availability at your earliest convenience.\n\nThanks"
                )

                # mailto: link — opens default mail client (iPad/Outlook/Apple Mail)
                mailto = (
                    f"mailto:{urllib.parse.quote(email)}"
                    f"?subject={urllib.parse.quote(subject)}"
                    f"&body={urllib.parse.quote(body_plain)}"
                )

	                # Gmail web compose — percent-encode manually so spaces become %20
                # and newlines become %0A (Gmail ignores + encoded spaces in body)
                def gmail_encode(s: str) -> str:
                    return urllib.parse.quote(s, safe='')

                gmail_url = (
                    f"https://mail.google.com/mail/?view=cm&fs=1"
                    f"&to={gmail_encode(email)}"
                    f"&su={gmail_encode(subject)}"
                    f"&body={gmail_encode(body_plain)}"
                )

                st.markdown(f"**{art}**")
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(
                        f'<a href="{mailto}" target="_blank">'
                        f'<button style="background:#4285f4;color:white;border:none;padding:7px 10px;'
                        f'border-radius:6px;cursor:pointer;font-size:12px;width:100%;">'
                        f'📧 Mail App</button></a>',
                        unsafe_allow_html=True
                    )
                with col_b:
                    st.markdown(
                        f'<a href="{gmail_url}" target="_blank">'
                        f'<button style="background:#d93025;color:white;border:none;padding:7px 10px;'
                        f'border-radius:6px;cursor:pointer;font-size:12px;width:100%;">'
                        f'📧 Gmail</button></a>',
                        unsafe_allow_html=True
                    )

    st.divider()

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
        # Highlight tiles already in the request selection with a blue border
        marker_sizes = df_filtered['name'].apply(
            lambda n: 24 if n in st.session_state.selected_request_tiles else 18
        ).tolist()
        border_widths = df_filtered['name'].apply(
            lambda n: 3 if n in st.session_state.selected_request_tiles else 1
        ).tolist()
        border_colors = df_filtered['name'].apply(
            lambda n: '#1a73e8' if n in st.session_state.selected_request_tiles else 'DarkSlateGrey'
        ).tolist()

        fig_map.add_trace(go.Scatter(
            x=df_filtered['x'], y=df_filtered['y'],
            mode='markers',
            marker=dict(
                size=marker_sizes, symbol='square',
                color=df_filtered['color'],
                line=dict(width=border_widths, color=border_colors)
            ),
            text=df_filtered.apply(
                lambda r: (
                    f"<b>{r['name']}</b><br>"
                    f"Artist: {r['artist']}"
                    + (f"<br>Station: {r['station']}" if r['station'] else "")
                    + f"<br>Completion: {r['comp_pct']}%"
                    f"<br>Day Value: {r['day_val']}"
                ), axis=1
            ),
            hoverinfo='text', showlegend=False
        ))

    fig_map.update_layout(
        plot_bgcolor=COLOR_GRID, width=1000, height=800,
        xaxis=dict(scaleanchor="y", scaleratio=1, side='top'),
        yaxis=dict(autorange="reversed"),
        legend=dict(
            bgcolor="rgba(255, 255, 255, 0.9)", bordercolor="DarkSlateGrey",
            borderwidth=1, tracegroupgap=80, itemsizing='constant',
            itemwidth=40, font=dict(family="Arial", size=18, color="black")
        )
    )
    st.plotly_chart(fig_map, use_container_width=True)

else:
    st.warning("No tile map data found.")


## Removed Tile picker from here, don't need this picker below the visual tilemap

st.divider()


# ════════════════════════════════════════════════════════════════════
#  💬  COMMENTS TABLE  (#3)
# ════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════
#  💬  COMMENTS TABLE
# ════════════════════════════════════════════════════════════════════

st.subheader("💬 Artist Comments")
st.caption("Comments sheet columns: Date | Artist Name | Tile | Comment")

COMMENT_COLS = ["Date", "Artist Name", "Tile", "Comment"]

def get_comments_ws():
    """Return the Comments worksheet (write access)."""
    c = get_creds()
    cl = gspread.authorize(c)
    ws_list = cl.open_by_key(SHEET_ID).worksheets()
    return next((s for s in ws_list if "Comment" in s.title), None)

# ── Display existing comments with per-row delete button (#3) ─────────────────────
if raw_comments and len(raw_comments) > 1:
    header = raw_comments[0]
    col_names = (
        [h.strip() if h.strip() else COMMENT_COLS[i] for i, h in enumerate(header[:4])]
        if len(header) >= 4 and any(h.strip() for h in header)
        else COMMENT_COLS
    )

    # Build display rows — each gets a Delete button in an extra column
    data_rows = [
        r[:4] if len(r) >= 4 else r + [''] * (4 - len(r))
        for r in raw_comments[1:]
    ]
    # Filter blank rows but keep track of original sheet row index (1-based, +1 for header)
    non_blank = [
        (sheet_row_idx + 2, row)   # +2: 1-based + skip header
        for sheet_row_idx, row in enumerate(data_rows)
        if any(str(v).strip() for v in row)
    ]

    if non_blank:
        # Header row
        hdr_cols = st.columns([1, 1, 1, 3, 0.4])
        for col, name in zip(hdr_cols[:4], col_names):
            col.markdown(f"**{name}**")

        st.divider()

        for sheet_row, row in non_blank:
            row_cols = st.columns([1, 1, 1, 3, 0.4])
            for col, val in zip(row_cols[:4], row):
                col.write(val)

            with row_cols[4]:
                if st.button("🗑️", key=f"del_{sheet_row}", help="Delete this comment"):
                    st.session_state.delete_confirm_row = sheet_row

        # ── Confirmation dialog (#3) ──────────────────────────────────────────────
        if st.session_state.delete_confirm_row is not None:
            target_row = st.session_state.delete_confirm_row
            # Find the row content for display
            row_content = next(
                (row for sr, row in non_blank if sr == target_row), ["?", "?", "?", "?"]
            )
            st.warning(
                f"⚠️ Delete comment by **{row_content[1]}** on tile **{row_content[2]}**? "
                f"*\"{row_content[3]}\"*"
            )
            conf_cols = st.columns([1, 1, 6])
            with conf_cols[0]:
                if st.button("✅ Yes, delete", key="confirm_delete"):
                    try:
                        ws = get_comments_ws()
                        if ws:
                            ws.delete_rows(target_row)
                            st.success("Comment deleted.")
                        else:
                            st.error("Comments sheet not found.")
                    except Exception as e:
                        st.error(f"Delete failed: {e}")
                    st.session_state.delete_confirm_row = None
                    st.cache_data.clear()
                    st.rerun()
            with conf_cols[1]:
                if st.button("❌ Cancel", key="cancel_delete"):
                    st.session_state.delete_confirm_row = None
                    st.rerun()
    else:
        st.info("No comments yet.")
else:
    st.info("No comments yet. Add the first one below.")

# ── Add new comment form (#2 — fields clear after save via key counter) ───────────
st.markdown("**Add a Comment**")

fk = st.session_state.comment_form_key   # incrementing this resets all keyed widgets

comment_cols = st.columns([1, 1, 2, 1])
with comment_cols[0]:
    comment_artist = st.selectbox("Artist", options=[""] + KNOWN_ARTISTS, key=f"c_artist_{fk}")
with comment_cols[1]:
    comment_tile   = st.selectbox("Tile",   options=[""] + sorted(df_map['name'].tolist()), key=f"c_tile_{fk}")
with comment_cols[2]:
    comment_text   = st.text_input("Comment", placeholder="Enter your comment here...", key=f"c_text_{fk}")
with comment_cols[3]:
    st.markdown("<br>", unsafe_allow_html=True)
    save_comment = st.button("💾 Save Comment")

if save_comment:
    if not comment_artist or not comment_tile or not comment_text.strip():
        st.warning("Please fill in Artist, Tile, and Comment before saving.")
    else:
        try:
            ws = get_comments_ws()
            if ws is None:
                st.error("Comments sheet not found.")
            else:
                new_row = [
                    today.strftime("%d/%m/%Y"),
                    comment_artist,
                    comment_tile,
                    comment_text.strip()
                ]
                ws.append_row(new_row, value_input_option="USER_ENTERED")
                st.success("✅ Comment saved!")
                st.session_state.comment_form_key += 1   # clears the form widgets (#2)
                st.cache_data.clear()
                st.rerun()
        except Exception as e:
            st.error(f"Failed to save comment: {e}")
            
st.caption("When adding/deleting comments it can take a few seconds to update")
st.divider()
st.divider()
