# app_v36 - Gemini's latest version with v6_07 (top stats section) and v35 (visual tilemap) combined

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

# --- CONFIGURABLE SETTINGS ---
totalTiles = 107
MAN_DAY_MULTIPLIER = 1.85

# UI COLORS
COLOR_25  = '#ff0000' # Red
COLOR_50  = '#ff9900' # Amber
COLOR_75  = '#ffff00' # Yellow
COLOR_100 = '#00ff00' # Green
COLOR_GRID = '#f8f9fb'

# --- 1. Authenticate ---
@st.cache_resource
def get_creds():
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly"]
    if "gcp_service_account" in st.secrets:
        return Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes)
    return Credentials.from_service_account_file("credentials.json", scopes=scopes)

creds = get_creds()
client = gspread.authorize(creds)
SHEET_ID = '1DHW5uoNu02xpdsp6PB8OXlSNtD3Ig9PKXThZ5BGDg6g'
sheet = client.open_by_key(SHEET_ID).sheet1

@st.cache_data(ttl=60)
def get_dashboard_data():
    data = sheet.get_all_values()
    session = AuthorizedSession(creds)
    # Fetching effectiveFormat and userEnteredFormat for maximum compatibility between v6 and v35
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}?ranges={sheet.title}!A1:AZ100&fields=sheets(data(rowData(values(effectiveFormat(backgroundColor),userEnteredFormat(backgroundColor),effectiveValue))))"
    response = session.get(url).json()
    return data, response

st.set_page_config(page_title="TileMap Dashboard v36", layout="wide")
st.title("🗺️ Combined TileMap Live Dashboard v36")

with st.spinner('Syncing data and calibrating colors...'):
    try:
        raw_data, formatting_response = get_dashboard_data()
        st.success("Dashboard Synchronized 🟢")
    except Exception as e:
        st.error(f"Failed to connect: {e}"); st.stop()

# --- 2. Processing Engine ---
legend_colors = {"25": None, "50": None, "75": None, "100": None}
map_points = [] 
tiles_25 = tiles_50 = tiles_75 = tiles_100 = tiles_0 = 0

try:
    row_data = formatting_response.get('sheets', [{}])[0].get('data', [{}])[0].get('rowData', [])
except:
    row_data = []

def colors_match(rgb1, rgb2, tol=0.15): 
    if rgb1 is None or rgb2 is None: return False
    return all(abs(a - b) < tol for a, b in zip(rgb1, rgb2))

def clean_coord(val):
    cleaned = re.sub(r'[^0-9/-]', '', str(val))
    parts = cleaned.split("/")
    return (int(parts[0]), int(parts[1])) if len(parts) == 2 else None


# --- STEP A: Legend Calibration (v6_07 Logic) ---
legend_colors = {"25": None, "50": None, "75": None, "100": None}
target_labels = ["0.25", ".25", "25%", "0.5", "0.50", ".5", "50%", "0.75", ".75", "75%", "1", "1.0", "100%"]

for r_idx in range(0, 20): # Scan first 20 rows
    if r_idx < len(raw_data):
        for col_idx, text_val in enumerate(raw_data[r_idx]):
            clean_val = str(text_val).strip()
            
            if clean_val in target_labels:
                # Map label to key
                label_key = "25" if "25" in clean_val else \
                            "50" if "5" in clean_val else \
                            "75" if "75" in clean_val else "100"
                
                # Check 1 or 2 cells to the LEFT for the color sample
                for offset in [1, 2]:
                    if col_idx - offset >= 0:
                        cell_fmt = row_data[r_idx]['values'][col_idx - offset]
                        # Use userEnteredFormat specifically for counting logic (v6 style)
                        bg = cell_fmt.get('userEnteredFormat', {}).get('backgroundColor')
                        if bg and not (bg.get('red', 1) == 1 and bg.get('green', 1) == 1 and bg.get('blue', 1) == 1):
                            legend_colors[label_key] = (bg.get('red', 0), bg.get('green', 0), bg.get('blue', 0))
                            break

# --- STEP B: Split Logic (v6 Stats + v35 Visuals) ---
tiles_25 = tiles_50 = tiles_75 = tiles_100 = tiles_0 = 0
map_points = []

for r_idx, row in enumerate(row_data):
    if r_idx < 14 or r_idx >= len(raw_data): continue 
    
    if 'values' in row:
        current_text_row = raw_data[r_idx]
        for c_idx, cell in enumerate(row['values']):
            if c_idx >= len(current_text_row): continue
                
            tile_name = str(current_text_row[c_idx]).strip()
            coords = clean_coord(tile_name)
            
            # --- V6_07 LOGIC: COUNTS ---
            user_bg = cell.get('userEnteredFormat', {}).get('backgroundColor')
            if user_bg:
                u_rgb = (user_bg.get('red', 0), user_bg.get('green', 0), user_bg.get('blue', 0))
                if sum(u_rgb) < 2.9: # Skip white
                    if colors_match(u_rgb, legend_colors["25"]): tiles_25 += 1
                    elif colors_match(u_rgb, legend_colors["50"]): tiles_50 += 1
                    elif colors_match(u_rgb, legend_colors["75"]): tiles_75 += 1
                    elif colors_match(u_rgb, legend_colors["100"]): tiles_100 += 1

            # --- V35 LOGIC: VISUAL MAP ---
            if coords:
                eff_bg = cell.get('effectiveFormat', {}).get('backgroundColor', {'red': 1, 'green': 1, 'blue': 1})
                map_points.append({
                    'x': coords[0], 'y': coords[1], 
                    'color': mcolors.to_hex((eff_bg.get('red', 0), eff_bg.get('green', 0), eff_bg.get('blue', 0))),
                    'name': tile_name
                })




# --- 3. UI Layout ---

# 3.1 Top Metrics (v6_07 Logic)
# v6_07 weighted calculation: treat 100% as 0 work left, 75% as 0.25 work left, etc.
remaining_work = (totalTiles - tiles_100) - ((tiles_25 * 0.25) + (tiles_50 * 0.5) + (tiles_75 * 0.75))
man_days = round(remaining_work * MAN_DAY_MULTIPLIER)

m_cols = st.columns(7)
m_cols[0].metric("Total Tiles", f"{totalTiles}")
m_cols[1].metric("In Progress", f"{tiles_25 + tiles_50 + tiles_75}")
m_cols[2].metric("25%", f"{tiles_25}")
m_cols[3].metric("50%", f"{tiles_50}")
m_cols[4].metric("75%", f"{tiles_75}")
m_cols[5].metric("100%", f"{tiles_100}")
m_cols[6].metric("Man Days Left", f"{man_days}d")

st.divider()

# 3.2 Middle Row: Bar Graph & Station Table
col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("📊 Progress Distribution")
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(['25%', '50%', '75%', '100%'], [tiles_25, tiles_50, tiles_75, tiles_100], 
           color=[COLOR_25, COLOR_50, COLOR_75, COLOR_100], edgecolor='grey')
    ax.bar_label(ax.containers[0], padding=3)
    st.pyplot(fig)

with col_right:
    st.subheader("📋 Station Assignments")
    df_raw = pd.DataFrame(raw_data)
    stations = []
    if not df_raw.empty:
        for i in range(10, min(50, len(df_raw))): # Adjusted range for station data
            if len(df_raw.columns) > 4:
                name = str(df_raw.iloc[i, 2]).strip()
                if name and name not in ['nan', 'None', 'Tile'] and 'OUT OF SCOPE' not in name:
                    stations.append({'Station': name, 'Tile': str(df_raw.iloc[i, 3]).strip(), 'Assignee': str(df_raw.iloc[i, 4]).strip()})
    st.dataframe(pd.DataFrame(stations), use_container_width=True, hide_index=True)

st.divider()

# 3.3 Bottom: Visual TileMap (v35 Logic)
st.subheader("📍 Interactive Visual TileMap")
if map_points:
    df_map = pd.DataFrame(map_points)
    fig_map = go.Figure(go.Scatter(
        x=df_map['x'], y=df_map['y'], mode='markers',
        marker=dict(size=18, symbol='square', color=df_map['color'], line=dict(width=1, color='DarkSlateGrey')),
        text=df_map['name'], hoverinfo='text'
    ))
    fig_map.update_layout(
        plot_bgcolor=COLOR_GRID, width=1000, height=800,
        xaxis=dict(scaleanchor="y", scaleratio=1, side='top'),
        yaxis=dict(autorange="reversed") 
    )
    st.plotly_chart(fig_map, use_container_width=True)
