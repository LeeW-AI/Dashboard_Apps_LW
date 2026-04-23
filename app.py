####### ---  Tilemap Stats Dashboard Web App v46  ------########

## Script Working Status - 


## v37 updated to now uses either a Streamlit Community Cloud Secrets file, or a local file in .streamlit\secrets.toml
## v38 added in some additional tweaks from v33 for the bar graph legend and number at the top of the bar
## v39 Adding Filter by Artist and additional Stats in the Visual tilemap - Doesn't really work well.
## v40 Rolled back to v38 then added Additional stats to the Visual tilemap hover over, 
## v41 Rolled back to v38 then added the Assignment key to the visual tilemap at the bottom so you can see which artist is which colour - didn't work well
## v42 Rolled back to v38 then added 2 Legends to the visual tilemap specifying the colours and text to use as variables
## v43 Used v42 as the baseline, adding Milestone tracking functionaliy to the Stats, this worked, but lost other stats and Legends, re-add in v44
## v44 Adding Milestone tracking to v42 for complete Dashboard - nearly working.
## v45 Fixing the Milestone tracking to add the missing colours.
## v46 Some minor UI cleanup


## NOTES FOR BUGS:
## Tile numbers must be the correct format -94/-263 or they will not be counted/coloured in the Dashboard
## Hast to be Sheet1 on the Google Sheet, has to be shared with the email in the credentials file as a Viewer.


## -------------------------------------------------------------------------------------------- ##

## New Features to add:
## Add Station Name to hover stats on Visual Tilemap if tile has a Station
## Update Man Days Count to be a better reflection of what's left (Should we add the other tasks done after scenery)
## Improve the look of the UI
## 



## For this to work I have shared TileMap_DashboardTest_LW with the email account in the credentials.json as a viewer
## This allows the script to access the google sheet.
## This script is using my own personal gmail account for API access, might need to share with that account too.

## You can refresh the Web App once loaded to refresh the stats when you update the sheet.

## When running the script in windows, if you CTRL+C a few times in the command prompt it will exit the script running
## you can then hit the up arrow to get the run command from history to run it again quickly
## This saves opening a new command window to test it again.


## This script requires the following installed: 
## py -m pip install streamlit pandas gspread gspread-formatting google-auth matplotlib plotly

# --- Run this using the command streamlit run app_v46.py

####### ---  Tilemap Stats Dashboard Web App v46  ------########

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
    "JamesH": "#ea9999",
    "TomH": "#ffe599",
    "Unassigned": "#c6d9f0",
    "Not Included": "#b7b7b7"
}

# Sync legacy variables for bar graph logic
COLOR_25 = COMPLETION_KEY["25%"]
COLOR_50 = COMPLETION_KEY["50%"]
COLOR_75 = COMPLETION_KEY["75%"]
COLOR_100 = COMPLETION_KEY["100%"]
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



# --- 2. Fetch Data (Fixed Scope Error) ---
@st.cache_data(ttl=60)
def get_dashboard_data():
    # Re-establish connection inside the function to avoid NameError/Scope issues
    creds = get_creds()
    client = gspread.authorize(creds)
    SHEET_ID = '1DHW5uoNu02xpdsp6PB8OXlSNtD3Ig9PKXThZ5BGDg6g'
    
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
    
    # Formatting Fetch
    session = AuthorizedSession(creds)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}?ranges={sheet.title}!A1:AZ100&fields=sheets(data(rowData(values(userEnteredFormat(backgroundColor),effectiveFormat(backgroundColor),effectiveValue))))"
    response = session.get(url).json()
    return raw_main, raw_milestone, response

st.set_page_config(page_title="TileMap Stats Dashboard v46", layout="wide")
st.title("📊 TileMap Stats Dashboard v46")

raw_main, raw_milestone, formatting_response = get_dashboard_data()
row_data = formatting_response.get('sheets', [{}])[0].get('data', [{}])[0].get('rowData', [])

# --- 3. Step A: Calibration (v6 Logic) ---
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
    # Change: return the string "X/Y" instead of (X, Y)
    return cleaned if len(parts) == 2 else None


for r_idx, row in enumerate(row_data):
    if r_idx < 14 or r_idx >= len(raw_main): continue 
    if 'values' in row:
        current_text_row = raw_main[r_idx]
        for c_idx, cell in enumerate(row['values']):
            # Counts for Stats
            user_bg = cell.get('userEnteredFormat', {}).get('backgroundColor')
            if user_bg:
                u_rgb = (user_bg.get('red', 0), user_bg.get('green', 0), user_bg.get('blue', 0))
                if sum(u_rgb) < 2.9 and sum(u_rgb) > 0:
                    if colors_match(u_rgb, legend_colors["25"]): tiles_25 += 1
                    elif colors_match(u_rgb, legend_colors["50"]): tiles_50 += 1
                    elif colors_match(u_rgb, legend_colors["75"]): tiles_75 += 1
                    elif colors_match(u_rgb, legend_colors["100"]): tiles_100 += 1
            
            
            
            # TileMap Points
            if c_idx < len(current_text_row):
                tile_name = str(current_text_row[c_idx]).strip()
                coords = clean_coord(tile_name)
                if coords:
                    eff_bg = cell.get('effectiveFormat', {}).get('backgroundColor', {'red': 1, 'green': 1, 'blue': 1})
                    hex_color = mcolors.to_hex((eff_bg.get('red', 0), eff_bg.get('green', 0), eff_bg.get('blue', 0)))
                    
                    # Store color using the string coordinate "X/Y"
                    tile_color_lookup[coords] = hex_color
                    
                    # Split the string back into numbers for the map coordinates
                    x_val, y_val = coords.split("/")
                    
                    map_points.append({
                        'x': int(x_val), 
                        'y': int(y_val), 
                        'color': hex_color, 
                        'name': tile_name
                    })
     

# --- 5. UI Build ---
remaining_work = (totalTiles - tiles_100) - ((tiles_25 * 0.25) + (tiles_50 * 0.5) + (tiles_75 * 0.75))
man_days = round(remaining_work * MAN_DAY_MULTIPLIER)

m_cols = st.columns(7)
m_cols[0].metric("Total", totalTiles); m_cols[1].metric("Started", tiles_25+tiles_50+tiles_75)
m_cols[2].metric("25%", tiles_25); m_cols[3].metric("50%", tiles_50)
m_cols[4].metric("75%", tiles_75); m_cols[5].metric("100%", tiles_100)
m_cols[6].metric("Man Days Left", f"{man_days}d")

st.divider()


# --- 5. Milestone Table (Updated for Column Headings) ---

st.subheader("🚩 Milestone Visual Status")
if raw_milestone:
    for row in raw_milestone[1:]: 
        # Indices updated for: [0] No., [1] Count, [2] Tiles
        if len(row) >= 3:
            m_no = str(row[0]).strip()
            m_expected_count = str(row[1]).strip()
            m_tiles_text = str(row[2]).strip()
            
            if not m_no or not m_tiles_text: continue
            
            found_coords = re.findall(r'-?\d+/-?\d+', m_tiles_text)
            actual_count = len(found_coords)
            
            if found_coords:
                # Mismatch logic
                count_display = f"({actual_count} tiles)"
                if m_expected_count.isdigit() and int(m_expected_count) != actual_count:
                    count_display = f"⚠️ Mismatch: Found {actual_count} / Expected {m_expected_count}"
                
                html_chips = f"**M{m_no}** {count_display} &nbsp; "
                
                for c in found_coords:
                    bg = tile_color_lookup.get(c, "#ffffff") 
                    is_dark = mcolors.rgb_to_hsv(mcolors.to_rgb(bg))[2] < 0.5
                    txt = "white" if is_dark else "black"
                    html_chips += f'<span style="background-color:{bg}; color:{txt}; padding:2px 6px; border-radius:4px; border:1px solid #ddd; margin-right:4px; font-family:monospace; font-size:12px;">{c}</span>'
                
                st.markdown(html_chips, unsafe_allow_html=True)
else:
    st.warning("Milestone data not found in the spreadsheet.")

st.divider()


# --- Progress and Station Assignment Tables ------------------ ######

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
    stations = [
        {'Station': str(raw_main[i][2]), 'Tile': str(raw_main[i][3]), 'Artist': str(raw_main[i][4])} 
        for i in range(10, min(45, len(raw_main))) 
        if len(raw_main[i]) > 4 and str(raw_main[i][2]).strip() not in ['nan', 'None', 'Tile'] and str(raw_main[i][2]).strip() != ""
    ]
    st.dataframe(pd.DataFrame(stations), hide_index=True, use_container_width=True, height=600)
    
st.divider()
   

# --- Visual Tilemap Display Code ------------------------------ ###

st.subheader("📍 Interactive Visual TileMap")
if map_points:
    df_map = pd.DataFrame(map_points)
    fig_map = go.Figure()

    # 1. ADD LEGEND SECTIONS (Grouped Dummy Traces)
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

    # 2. ADD ACTUAL TILE DATA
    fig_map.add_trace(go.Scatter(
        x=df_map['x'], y=df_map['y'], mode='markers',
        marker=dict(size=18, symbol='square', color=df_map['color'], line=dict(width=1, color='DarkSlateGrey')),
        text=df_map['name'], hoverinfo='text',
        showlegend=False  # Hide individual tile markers from the legend
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
            tracegroupgap=80,     # Increases space between Completion and Assignment groups
            itemsizing='constant', # Ensures legend markers stay a consistent size
            itemwidth=40,          # Increases the width of the legend items
            font=dict(
                family="Arial",
                size=18,           # ⬅️ ADJUST THIS for larger text
                color="black"
            )
        )
    )
    
    st.plotly_chart(fig_map, use_container_width=True)
