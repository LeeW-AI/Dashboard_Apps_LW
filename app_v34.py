####### ---  Tilemap Stats Dashboard Web App  v6_06 ------########

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

# --- Run this using the command streamlit run app_v6_06.py

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

# --- 1. Authenticate with Google Sheets ---
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

# Replace with your actual Google Sheet ID
## SHEET_ID = '1ajduQT0CmoM-gfAyaa5iLfun5p-sN-SOf0ybL960XIY' -- this is the old google sheet on my personal account, below is work account sheet
SHEET_ID = '1DHW5uoNu02xpdsp6PB8OXlSNtD3Ig9PKXThZ5BGDg6g'
sheet = client.open_by_key(SHEET_ID).sheet1

# --- 2. Fetch Live Data and Colors ---
@st.cache_data(ttl=60)
def get_dashboard_data():
    # Fetch all raw text values using gspread
    data = sheet.get_all_values()
    
    # Fetch formatting data using a direct API session (most robust method)
    session = AuthorizedSession(creds)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}?ranges={sheet.title}!A1:AZ100&fields=sheets(data(rowData(values(userEnteredFormat(backgroundColor)))))"
    
    response = session.get(url).json()
    return data, response

# --- UI Header ---
st.set_page_config(page_title="Game Map Tile Tracker v6_06", layout="wide")
st.title("🗺️ TileMap Live Progress Dashboard v6_06")

with st.spinner('Syncing with Google Sheets...'):
    try:
        raw_data, formatting_response = get_dashboard_data()
        st.success("Data synced successfully! 🟢")
    except Exception as e:
        st.error(f"Failed to connect: {e}")
        st.stop()

# --- 3. Process Data (Auto-calibrate Colors & Count) ---

legend_colors = {"25": None, "50": None, "75": None, "100": None}
debug_info = []
tiles_25, tiles_50, tiles_75, tiles_100, tiles_0 = 0, 0, 0, 0, 0




# Extract row data
try:
    row_data = formatting_response.get('sheets', [{}])[0].get('data', [{}])[0].get('rowData', [])
except (IndexError, KeyError):
    row_data = []

# --- STEP A: Search for the Legend labels ---
# We now include "25%", "50%", etc.
target_labels = ["0.25", ".25", "25%", "0.5", "0.50", ".5", "50%", "0.75", ".75", "75%", "1", "1.0", "100%"]

for r_idx in range(0, 15): # Scan first 15 rows
    if r_idx < len(raw_data):
        row_text_values = raw_data[r_idx]
        
        for col_idx, text_val in enumerate(row_text_values):
            clean_val = str(text_val).strip()
            txt = str(text_val).strip()
            
            cell_data = row_data[r_idx]['values'][col_idx] if 'values' in row_data[r_idx] and col_idx < len(row_data[r_idx]['values']) else {}
            num_val = cell_data.get('effectiveValue', {}).get('numberValue', -1)

            
            if clean_val in target_labels:
                # Map label to our key (25, 50, 75, 100)
                label_key = "25" if "25" in clean_val else \
                            "50" if "50" in clean_val or clean_val in ["0.5", ".5"] else \
                            "75" if "75" in clean_val else "100"
                
                # Check the cell to the LEFT, and if that has no color, check the one before it
                # (Handles cases where there might be a small gap or merged cells)
                found_color = None
                for offset in [1, 2]: # Look 1 cell back, then 2 cells back
                    color_col_idx = col_idx - offset
                    if color_col_idx >= 0:
                        row_fmt = row_data[r_idx]
                        if 'values' in row_fmt and len(row_fmt['values']) > color_col_idx:
                            cell = row_fmt['values'][color_col_idx]
                            if 'userEnteredFormat' in cell and 'backgroundColor' in cell['userEnteredFormat']:
                                bg = cell['userEnteredFormat']['backgroundColor']
                                # Only count it if it's not white (1,1,1)
                                if not (bg.get('red', 0) == 1 and bg.get('green', 0) == 1 and bg.get('blue', 0) == 1):
                                    found_color = (bg.get('red', 0), bg.get('green', 0), bg.get('blue', 0))
                                    break # Found a colored cell!
                
                if found_color:
                    legend_colors[label_key] = found_color
                    debug_info.append(f"✅ Found '{clean_val}' at Col {col_idx+1}. Sampled color from Col {col_idx+1-offset}: {found_color}")
                else:
                    debug_info.append(f"❌ Found '{clean_val}' at Col {col_idx+1}, but no background color found in nearby cells to the left.")

# Show debugging help
with st.expander("🛠️ Calibration Debugger"):
    if not debug_info:
        st.error("Could not find any labels (25%, 50%, etc.) in the first 15 rows.")
    else:
        for info in debug_info:
            st.write(info)
    st.write("### Final Color Map:", legend_colors)

# --- STEP B: Count Tiles (Same as before) ---
tiles_25, tiles_50, tiles_75, tiles_100 = 0, 0, 0, 0

def colors_match(rgb1, rgb2, tol=0.1): 
    if rgb1 is None or rgb2 is None: return False
    return all(abs(a - b) < tol for a, b in zip(rgb1, rgb2))

for r_idx, row in enumerate(row_data):
    if r_idx < 14: continue 
    
    if 'values' in row:
        for c_idx, cell in enumerate(row['values']):
            if 'userEnteredFormat' in cell and 'backgroundColor' in cell['userEnteredFormat']:
                bg = cell['userEnteredFormat']['backgroundColor']
                current_rgb = (bg.get('red', 0), bg.get('green', 0), bg.get('blue', 0))
                
                if sum(current_rgb) > 2.9 or sum(current_rgb) == 0: continue

                if colors_match(current_rgb, legend_colors["25"]): tiles_25 += 1
                elif colors_match(current_rgb, legend_colors["50"]): tiles_50 += 1
                elif colors_match(current_rgb, legend_colors["75"]): tiles_75 += 1
                elif colors_match(current_rgb, legend_colors["100"]): tiles_100 += 1

total_started = tiles_25 + tiles_50 + tiles_75 + tiles_100

# --- 4. Build the UI ---

# --- 4.1 Calculations ---
# Man Day Calculation: (Remaining Work Units) * Multiplier
# We treat 100% as 0 work left, 75% as 0.25 work left, etc.
remaining_work_units = (totalTiles - tiles_100) - ((tiles_25 * 0.25) + (tiles_50 * 0.5) + (tiles_75 * 0.75))
man_days = round(remaining_work_units * MAN_DAY_MULTIPLIER)


# Top Metric Cards
m1, m2, m3, m4 = st.columns(4)
##m1.metric("Tiles in Progress (25%+)", f"{total_started} Tiles")
##m2.metric("In Progress", f"{tiles_25 + tiles_50 + tiles_75}")
##m3.metric("Complete & Polished", f"{tiles_100}")
##m4.metric("Target", "107 Tiles")


m_cols = st.columns(7)
m_cols[0].metric("Total Tiles", f"{totalTiles}")
m_cols[1].metric("Tiles In Progress", f"{tiles_25 + tiles_50 + tiles_75}")
m_cols[2].metric("Tiles at 25%", f"{tiles_25}")
m_cols[3].metric("Tiles at 50%", f"{tiles_50}")
m_cols[4].metric("Tiles at 75%", f"{tiles_75}")
m_cols[5].metric("Tiles 100% (Complete)", f"{tiles_100}")
m_cols[6].metric("Man Days Left", f"{man_days} d")



st.divider()

# Process Station Table
df_raw = pd.DataFrame(raw_data)
stations = []
if not df_raw.empty:
    for i in range(10, min(45, len(df_raw))):
        if len(df_raw.columns) > 4:
            name = str(df_raw.iloc[i, 2]).strip()
            if name and name not in ['nan', 'None', 'Tile'] and 'OUT OF SCOPE' not in name:
                stations.append({
                    'Station': name,
                    'Tile': str(df_raw.iloc[i, 3]).strip(),
                    'Assignee': str(df_raw.iloc[i, 4]).strip()
                })
df_stations = pd.DataFrame(stations)



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

    # --- THE LEGEND ADDITION ---
    st.write("---")
    st.caption("Graph Color Legend (Editable in Script)")
    leg_1, leg_2, leg_3, leg_4 = st.columns(4)
    leg_1.markdown(f"🔴 **25%:** `{COLOR_25}`")
    leg_2.markdown(f"🟠 **50%:** `{COLOR_50}`")
    leg_3.markdown(f"🟡 **75%:** `{COLOR_75}`")
    leg_4.markdown(f"🟢 **100%:** `{COLOR_100}`")


with col_right:
    st.subheader("Station Assignments")
    st.dataframe(df_stations, use_container_width=True, hide_index=True)
   




### ---------------------------- VISUAL TILEMAP FROM v33 ------------------------------- ###

legend_colorsB = {"25": None, "50": None, "75": None, "100": None}
map_points = [] 


try:
    row_data = formatting_response.get('sheets', [{}])[0].get('data', [{}])[0].get('rowData', [])
except:
    row_data = []


# --- STEP A: Legend Calibration ---


for r_idx in range(0, 15):
    if r_idx < len(raw_data):
        for col_idx, text_val in enumerate(raw_data[r_idx]):
            txt = str(text_val).strip()
            cell_dataB = row_data[r_idx]['values'][col_idx] if 'values' in row_data[r_idx] and col_idx < len(row_data[r_idx]['values']) else {}
            num_valB = cell_dataB.get('effectiveValue', {}).get('numberValue', -1)

            if txt in target_labels or num_val in [0.25, 0.5, 0.75, 1.0]:
                label_keyB = "25" if ("25" in txt or num_val == 0.25) else \
                            "50" if ("5" in txt or num_val == 0.5) else \
                            "75" if ("75" in txt or num_val == 0.75) else "100"
                
                for offset in [1, 2]:
                    if col_idx - offset >= 0:
                        prev_cell = row_data[r_idx]['values'][col_idx - offset]
                        bgB = prev_cell.get('effectiveFormat', {}).get('backgroundColor', {})
                        if bg and not (bgB.get('red', 1) == 1 and bgB.get('green', 1) == 1 and bgB.get('blue', 1) == 1):
                            legend_colorsB[label_keyB] = (bgB.get('red', 0), bgB.get('green', 0), bgB.get('blue', 0))
                            break

# --- STEP B: Universal Processing Engine ---
def colors_matchB(rgb1, rgb2, tol=0.15): 
    if rgb1 is None or rgb2 is None: return False
    return all(abs(a - b) < tol for a, b in zip(rgb1, rgb2))

def clean_coordB(val):
    try:
        cleaned = re.sub(r'[^0-9/-]', '', val)
        parts = cleaned.split("/")
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except:
        return None

for r_idx, row in enumerate(row_data):
    if r_idx < 14 or r_idx >= len(raw_data): continue 
    
    if 'values' in row:
        for c_idx, cell in enumerate(row['values']):
            tile_name = str(raw_data[r_idx][c_idx]).strip() if c_idx < len(raw_data[r_idx]) else ""
            
            coords = clean_coordB(tile_name)
            if coords:
                bgB = cell.get('effectiveFormat', {}).get('backgroundColor', {'red': 1, 'green': 1, 'blue': 1})
                curr_rgb = (bgB.get('red', 0), bgB.get('green', 0), bgB.get('blue', 0))
                actual_hex = mcolors.to_hex(curr_rgb)

                is_colored = False
                if colors_matchB(curr_rgb, legend_colorsB["25"]): 
                    tiles_25 += 1; is_colored = True
                elif colors_matchB(curr_rgb, legend_colorsB["50"]): 
                    tiles_50 += 1; is_colored = True
                elif colors_matchB(curr_rgb, legend_colorsB["75"]): 
                    tiles_75 += 1; is_colored = True
                elif colors_matchB(curr_rgb, legend_colorsB["100"]): 
                    tiles_100 += 1; is_colored = True
                
                if not is_colored:
                    tiles_0 += 1

                x, y = coords
                map_points.append({'x': x, 'y': y, 'color': actual_hex, 'name': tile_name})


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
