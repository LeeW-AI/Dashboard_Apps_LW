####### ---  Tilemap Stats Dashboard Web App  v6_05 ------########

## Script Working Status - This works, now using a google sheet from my work account.


## This version is a branch of v6, I preferred the stats bar graph count in v6 as it worked.
## I have branched this v6_02 to try and get this working with the improvements in v33


## For this to work I have shared TileMap_DashboardTest_LW with the email account in the credentials.json as a viewer
## This allows the script to access the google sheet.
## This script is using my own personal gmail account for API access, might need to share with that account too.

## You can refresh the Web App once loaded to refresh the stats when you update the sheet.

## When running the script in windows, if you CTRL+C a few times in the command prompt it will exit the script running
## you can then hit the up arrow to get the run command from history to run it again quickly
## This saves opening a new command window to test it again.


## This script requires the following installed: 
## py -m pip install streamlit pandas gspread gspread-formatting google-auth matplotlib

# --- Run this using the command streamlit run app_v6_05.py

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

# EDIT THESE HEX CODES TO CHANGE UI COLORS
COLOR_25  = '#ff0000' # Red
COLOR_50  = '#ff9900' # Amber
COLOR_75  = '#ffff00' # Yellow
COLOR_100 = '#00ff00' # Green
COLOR_GRID = '#f8f9fb'

# --- 1. Authenticate with Google Sheets ---
@st.cache_resource

# This is the new method of loading credentials from Streamlit Cloud using a secret box to hide the details as it's on a public repo

def get_creds():
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly"]
    
    # 1. Try to load from Streamlit Secrets (for iPad/Web)
    if "gcp_service_account" in st.secrets:
        return Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], 
            scopes=scopes
        )
    
    # 2. Fallback to local file (for PC)
    return Credentials.from_service_account_file("credentials.json", scopes=scopes)



creds = get_creds()
client = gspread.authorize(creds)
SHEET_ID = '1DHW5uoNu02xpdsp6PB8OXlSNtD3Ig9PKXThZ5BGDg6g'
sheet = client.open_by_key(SHEET_ID).sheet1

# --- 2. Fetch Live Data and Colors ---
@st.cache_data(ttl=60)
def get_dashboard_data():
    data = sheet.get_all_values()
    session = AuthorizedSession(creds)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}?ranges={sheet.title}!A1:AZ100&fields=sheets(data(rowData(values(userEnteredFormat(backgroundColor),effectiveFormat(backgroundColor),effectiveValue))))"
    response = session.get(url).json()
    return data, response

# --- UI Header ---
st.set_page_config(page_title="Game Map Tile Tracker v6_05", layout="wide")
st.title("🗺️ TileMap Live Progress Dashboard v6_05")

with st.spinner('Syncing with Google Sheets...'):
    try:
        raw_data, formatting_response = get_dashboard_data()
        st.success("Data synced successfully! 🟢")
    except Exception as e:
        st.error(f"Failed to connect: {e}")
        st.stop()

# --- 3. Process Data (Stats Engine) ---
legend_colors = {"25": None, "50": None, "75": None, "100": None}
tiles_25, tiles_50, tiles_75, tiles_100 = 0, 0, 0, 0

try:
    row_data = formatting_response.get('sheets', [{}])[0].get('data', [{}])[0].get('rowData', [])
except:
    row_data = []

# --- STEP A: Legend Calibration (v6 logic) ---
target_labels = ["0.25", ".25", "25%", "0.5", "0.50", ".5", "50%", "0.75", ".75", "75%", "1", "1.0", "100%"]

for r_idx in range(0, 15): 
    if r_idx < len(raw_data):
        for col_idx, text_val in enumerate(raw_data[r_idx]):
            clean_val = str(text_val).strip()
            if clean_val in target_labels:
                label_key = "25" if "25" in clean_val else \
                            "50" if "50" in clean_val or clean_val in ["0.5", ".5"] else \
                            "75" if "75" in clean_val else "100"
                
                for offset in [1, 2]:
                    color_col_idx = col_idx - offset
                    if color_col_idx >= 0:
                        row_fmt = row_data[r_idx]
                        if 'values' in row_fmt and len(row_fmt['values']) > color_col_idx:
                            cell = row_fmt['values'][color_col_idx]
                            bg = cell.get('userEnteredFormat', {}).get('backgroundColor', {})
                            if bg and not (bg.get('red', 1) == 1 and bg.get('green', 1) == 1 and bg.get('blue', 1) == 1):
                                legend_colors[label_key] = (bg.get('red', 0), bg.get('green', 0), bg.get('blue', 0))
                                break

# --- STEP B: Count Tiles (v6 logic) ---
def colors_match(rgb1, rgb2, tol=0.1): 
    if rgb1 is None or rgb2 is None: return False
    return all(abs(a - b) < tol for a, b in zip(rgb1, rgb2))

for r_idx, row in enumerate(row_data):
    if r_idx < 14: continue 
    if 'values' in row:
        for c_idx, cell in enumerate(row['values']):
            bg = cell.get('userEnteredFormat', {}).get('backgroundColor', {})
            current_rgb = (bg.get('red', 0), bg.get('green', 0), bg.get('blue', 0))
            if sum(current_rgb) > 2.9 or sum(current_rgb) == 0: continue

            if colors_match(current_rgb, legend_colors["25"]): tiles_25 += 1
            elif colors_match(current_rgb, legend_colors["50"]): tiles_50 += 1
            elif colors_match(current_rgb, legend_colors["75"]): tiles_75 += 1
            elif colors_match(current_rgb, legend_colors["100"]): tiles_100 += 1

# --- 4. Build UI ---
# Improved Man Day Calculation
remaining_work_units = (totalTiles - tiles_100) - ((tiles_25 * 0.25) + (tiles_50 * 0.5) + (tiles_75 * 0.75))
man_days = round(remaining_work_units * MAN_DAY_MULTIPLIER)

m_cols = st.columns(7)
m_cols[0].metric("Total Tiles", f"{totalTiles}")
m_cols[1].metric("In Progress", f"{tiles_25 + tiles_50 + tiles_75}")
m_cols[2].metric("Tiles at 25%", f"{tiles_25}")
m_cols[3].metric("Tiles at 50%", f"{tiles_50}")
m_cols[4].metric("Tiles at 75%", f"{tiles_75}")
m_cols[5].metric("Tiles 100%", f"{tiles_100}")
m_cols[6].metric("Man Days Left", f"{man_days} d")

st.divider()

col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("Progress Distribution")
    labels = ['25% Done', '50% Done', '75% Done', '100% Done']
    counts = [tiles_25, tiles_50, tiles_75, tiles_100]
    bar_colors = [COLOR_25, COLOR_50, COLOR_75, COLOR_100]
    
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(labels, counts, color=bar_colors, edgecolor='grey')
    ax.bar_label(ax.containers[0], padding=3)
    st.pyplot(fig)

    st.write("---")
    st.caption("Graph Color Legend")
    leg_1, leg_2, leg_3, leg_4 = st.columns(4)
    leg_1.markdown(f"🔴 **25%:** `{COLOR_25}`")
    leg_2.markdown(f"🟠 **50%:** `{COLOR_50}`")
    leg_3.markdown(f"🟡 **75%:** `{COLOR_75}`")
    leg_4.markdown(f"🟢 **100%:** `{COLOR_100}`")

with col_right:
    st.subheader("Station Assignments")
    stations = []
    for i in range(10, min(45, len(raw_data))):
        if len(raw_data[i]) > 4:
            name = str(raw_data[i][2]).strip()
            if name and name not in ['nan', 'None', 'Tile'] and 'OUT OF SCOPE' not in name:
                stations.append({'Station': name, 'Tile': str(raw_data[i][3]).strip(), 'Artist': str(raw_data[i][4]).strip()})
    st.dataframe(pd.DataFrame(stations), use_container_width=True, hide_index=True)

st.divider()

### --- 5. VISUAL TILEMAP (Safe Indexing) ---
st.subheader("📍 Interactive Visual TileMap")
map_points = []

def clean_coord(val):
    try:
        cleaned = re.sub(r'[^0-9/-]', '', val)
        parts = cleaned.split("/")
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except:
        return None

# Safe Loop: Checks if r_idx and c_idx exist in raw_data before accessing
for r_idx, row in enumerate(row_data):
    if r_idx < 14 or r_idx >= len(raw_data): continue  # Safety check for rows
    
    if 'values' in row:
        for c_idx, cell in enumerate(row['values']):
            # Safety check for columns
            if c_idx >= len(raw_data[r_idx]):
                tile_name = ""
            else:
                tile_name = str(raw_data[r_idx][c_idx]).strip()
            
            coords = clean_coord(tile_name)
            if coords:
                bg_eff = cell.get('effectiveFormat', {}).get('backgroundColor', {'red': 1, 'green': 1, 'blue': 1})
                hex_color = mcolors.to_hex((bg_eff.get('red', 1), bg_eff.get('green', 1), bg_eff.get('blue', 1)))
                
                map_points.append({
                    'x': coords[0],
                    'y': coords[1],
                    'color': hex_color,
                    'name': tile_name
                })

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
