####### ---  Tilemap Stats Dashboard Web App v35  ------########

## Script Working Status - Still not working as good as v6 with the top colour counting stats - still fixing this
## Have updated the top Stats to show the variable for tile count, percentage breakdown and man days properly calculated.

## v34 will be just the bottom visual tilemap working, I want to separate this out to see what it needs to work.
## Next I will combine the v34 with the top stats from v6_03 
## The Station list is better in v33, contains all the tiles, even the branch we aren't doing

## v14 to v32 is combining the top stats from v6, and the visual tilemap from v11 - still working on this
## Some versions were not kept due to iterating through the updates with Gemini



## NOTES FOR BUGS:
## Tile numbers must be the correct format -94/-263 or they will not be counted/coloured in the Dashboard



## -------------------------------------------------------------------------------------------- ##

## New Features to add:




## For this to work I have shared TileMap_DashboardTest_LW with the email account in the credentials.json as a viewer
## This allows the script to access the google sheet.
## This script is using my own personal gmail account for API access, might need to share with that account too.

## You can refresh the Web App once loaded to refresh the stats when you update the sheet.

## When running the script in windows, if you CTRL+C a few times in the command prompt it will exit the script running
## you can then hit the up arrow to get the run command from history to run it again quickly
## This saves opening a new command window to test it again.


## This script requires the following installed: 
## py -m pip install streamlit pandas gspread gspread-formatting google-auth matplotlib plotly

# --- Run this using the command streamlit run app_v35.py

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

# --- CONFIGURABLE SETTINGS ---
totalTiles = 107
MAN_DAY_MULTIPLIER = 1.85

# EDIT THESE HEX CODES TO CHANGE UI COLORS
COLOR_25  = '#ff0000' # Red
COLOR_50  = '#ff9900' # Amber
COLOR_75  = '#ffff00' # Yellow
COLOR_100 = '#00ff00' # Green
COLOR_GRID = '#f8f9fb'

# --- 1. Authenticate ---

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



# commented out PC code for credentials, not needed at the moment
#def get_creds():
#    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly"]
#    return Credentials.from_service_account_file("credentials.json", scopes=scopes)

creds = get_creds()
client = gspread.authorize(creds)
SHEET_ID = '1DHW5uoNu02xpdsp6PB8OXlSNtD3Ig9PKXThZ5BGDg6g'
sheet = client.open_by_key(SHEET_ID).sheet1

@st.cache_data(ttl=60)
def get_dashboard_data():
    data = sheet.get_all_values()
    session = AuthorizedSession(creds)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}?ranges={sheet.title}!A1:AZ100&fields=sheets(data(rowData(values(effectiveFormat(backgroundColor),effectiveValue))))"
    response = session.get(url).json()
    return data, response

st.set_page_config(page_title="Game Map Tile Tracker v35", layout="wide")
st.title("🗺️ TileMap Live Progress Dashboard v35")

with st.spinner('Calibrating all progress colors...'):
    try:
        raw_data, formatting_response = get_dashboard_data()
        st.success("Data synced and calibrated! 🟢")
    except Exception as e:
        st.error(f"Failed to connect: {e}"); st.stop()

# --- 3. Process Data ---
legend_colors = {"25": None, "50": None, "75": None, "100": None}
map_points = [] 
tiles_25, tiles_50, tiles_75, tiles_100, tiles_0 = 0, 0, 0, 0, 0

try:
    row_data = formatting_response.get('sheets', [{}])[0].get('data', [{}])[0].get('rowData', [])
except:
    row_data = []

# --- STEP A: Legend Calibration ---
target_labels = ["0.25", ".25", "25%", "0.5", "0.50", ".5", "50%", "0.75", ".75", "75%", "1", "1.0", "100%"]
for r_idx in range(0, 15):
    if r_idx < len(raw_data):
        for col_idx, text_val in enumerate(raw_data[r_idx]):
            txt = str(text_val).strip()
            cell_data = row_data[r_idx]['values'][col_idx] if 'values' in row_data[r_idx] and col_idx < len(row_data[r_idx]['values']) else {}
            num_val = cell_data.get('effectiveValue', {}).get('numberValue', -1)

            if txt in target_labels or num_val in [0.25, 0.5, 0.75, 1.0]:
                label_key = "25" if ("25" in txt or num_val == 0.25) else \
                            "50" if ("5" in txt or num_val == 0.5) else \
                            "75" if ("75" in txt or num_val == 0.75) else "100"
                
                for offset in [1, 2]:
                    if col_idx - offset >= 0:
                        prev_cell = row_data[r_idx]['values'][col_idx - offset]
                        bg = prev_cell.get('effectiveFormat', {}).get('backgroundColor', {})
                        if bg and not (bg.get('red', 1) == 1 and bg.get('green', 1) == 1 and bg.get('blue', 1) == 1):
                            legend_colors[label_key] = (bg.get('red', 0), bg.get('green', 0), bg.get('blue', 0))
                            break

# --- STEP B: Universal Processing Engine ---
def colors_match(rgb1, rgb2, tol=0.15): 
    if rgb1 is None or rgb2 is None: return False
    return all(abs(a - b) < tol for a, b in zip(rgb1, rgb2))

def clean_coord(val):
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
            
            coords = clean_coord(tile_name)
            if coords:
                bg = cell.get('effectiveFormat', {}).get('backgroundColor', {'red': 1, 'green': 1, 'blue': 1})
                curr_rgb = (bg.get('red', 0), bg.get('green', 0), bg.get('blue', 0))
                actual_hex = mcolors.to_hex(curr_rgb)

                is_colored = False
                if colors_match(curr_rgb, legend_colors["25"]): 
                    tiles_25 += 1; is_colored = True
                elif colors_match(curr_rgb, legend_colors["50"]): 
                    tiles_50 += 1; is_colored = True
                elif colors_match(curr_rgb, legend_colors["75"]): 
                    tiles_75 += 1; is_colored = True
                elif colors_match(curr_rgb, legend_colors["100"]): 
                    tiles_100 += 1; is_colored = True
                
                if not is_colored:
                    tiles_0 += 1

                x, y = coords
                map_points.append({'x': x, 'y': y, 'color': actual_hex, 'name': tile_name})


# --- 5. Build UI ---


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
