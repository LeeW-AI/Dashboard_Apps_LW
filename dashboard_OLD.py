"""
Tilemap Dashboard — dashboard.py
─────────────────────────────────
Run with:  streamlit run dashboard.py

Reads the CSVs produced by tilemap_tracker.py and renders:
  • A live-updating per-artist progress bar panel
  • An interactive plotly tilemap recreation
  • A raw data explorer
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from pathlib import Path

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
        background: #1a1d27;
        border: 1px solid #2a2d3a;
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 0.75rem;
    }
    .metric-card h4 {
        margin: 0 0 0.5rem 0;
        font-size: 0.85rem;
        color: #8b8fa8;
        font-family: 'Space Mono', monospace;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .metric-card .value {
        font-size: 2.2rem;
        font-weight: 600;
        color: #e8eaf0;
        line-height: 1;
    }
    .metric-card .sub {
        font-size: 0.78rem;
        color: #6b6f85;
        margin-top: 0.3rem;
    }

    .progress-row {
        background: #1a1d27;
        border: 1px solid #2a2d3a;
        border-radius: 10px;
        padding: 0.9rem 1.2rem;
        margin-bottom: 0.5rem;
    }
    .progress-row .artist-name {
        font-weight: 600;
        font-size: 0.95rem;
        margin-bottom: 0.4rem;
    }
    .progress-bar-bg {
        background: #2a2d3a;
        border-radius: 4px;
        height: 8px;
        width: 100%;
    }
    .progress-bar-fill {
        border-radius: 4px;
        height: 8px;
        transition: width 0.5s ease;
    }

    .section-header {
        font-family: 'Space Mono', monospace;
        font-size: 0.7rem;
        text-transform: uppercase;
        letter-spacing: 0.12em;
        color: #555870;
        border-bottom: 1px solid #2a2d3a;
        padding-bottom: 0.5rem;
        margin: 1.5rem 0 1rem 0;
    }
</style>
""", unsafe_allow_html=True)


# ── Data Loading ─────────────────────────────────────────────────────────────────

@st.cache_data(ttl=60)  # Auto-refresh every 60 seconds
def load_data():
    tile_path    = Path("output/progress_report.csv")
    summary_path = Path("output/artist_summary.csv")

    if not tile_path.exists():
        return None, None

    tiles   = pd.read_csv(tile_path)
    summary = pd.read_csv(summary_path) if summary_path.exists() else None
    return tiles, summary


tiles, summary = load_data()


# ── Header ───────────────────────────────────────────────────────────────────────

st.markdown("# 🗺️ Tilemap Tracker")
st.markdown('<p style="color:#6b6f85;margin-top:-0.5rem;font-size:0.9rem;">UE4 Level Tile Assignment & Progress Dashboard</p>', unsafe_allow_html=True)

if tiles is None:
    st.warning("No data found. Run `python tilemap_tracker.py` first to generate output/progress_report.csv")
    st.stop()


# ── Top Metrics ──────────────────────────────────────────────────────────────────

total_tiles  = len(tiles)
assigned     = tiles[~tiles["artist"].isin(["UNASSIGNED", "IN_PROGRESS", "Empty"])]
done_tiles   = int(tiles["is_done"].sum())
overall_pct  = round(done_tiles / total_tiles * 100, 1) if total_tiles else 0

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <h4>Total Tiles</h4>
        <div class="value">{total_tiles:,}</div>
        <div class="sub">in tracked region</div>
    </div>""", unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card">
        <h4>Assigned</h4>
        <div class="value">{len(assigned):,}</div>
        <div class="sub">across {summary['artist'].nunique() if summary is not None else '—'} artists</div>
    </div>""", unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <h4>Completed</h4>
        <div class="value">{done_tiles:,}</div>
        <div class="sub">tiles marked 100%</div>
    </div>""", unsafe_allow_html=True)

with col4:
    colour = "#00C896" if overall_pct >= 75 else "#FFB800" if overall_pct >= 40 else "#FF4B4B"
    st.markdown(f"""
    <div class="metric-card">
        <h4>Overall Progress</h4>
        <div class="value" style="color:{colour}">{overall_pct}%</div>
        <div class="sub">of assigned tiles done</div>
    </div>""", unsafe_allow_html=True)


# ── Main Layout ──────────────────────────────────────────────────────────────────

left_col, right_col = st.columns([1, 2])

# ── LEFT: Artist Progress Bars ────────────────────────────────────────────────

with left_col:
    st.markdown('<div class="section-header">Artist Progress</div>', unsafe_allow_html=True)

    if summary is not None:
        for _, row in summary.sort_values("progress_pct", ascending=False).iterrows():
            pct  = row["progress_pct"]
            done = int(row["completed"])
            total = int(row["total_tiles"])

            # Colour the bar by progress
            if pct >= 100:
                bar_colour = "#00C896"
            elif pct >= 75:
                bar_colour = "#4CAF50"
            elif pct >= 50:
                bar_colour = "#FFB800"
            elif pct >= 25:
                bar_colour = "#FF8C00"
            else:
                bar_colour = "#FF4B4B"

            st.markdown(f"""
            <div class="progress-row">
                <div class="artist-name">{row['artist']}</div>
                <div style="display:flex;justify-content:space-between;font-size:0.78rem;color:#8b8fa8;margin-bottom:0.35rem;">
                    <span>{done}/{total} tiles</span>
                    <span style="color:{bar_colour};font-weight:600">{pct}%</span>
                </div>
                <div class="progress-bar-bg">
                    <div class="progress-bar-fill" style="width:{pct}%;background:{bar_colour}"></div>
                </div>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("Run the tracker to generate artist summaries.")


# ── RIGHT: Interactive Tilemap ────────────────────────────────────────────────

with right_col:
    st.markdown('<div class="section-header">Tilemap View</div>', unsafe_allow_html=True)

    # Build colour map for the scatter plot
    # Use background_hex directly — it reflects both artist and completion colours
    fig = go.Figure()

    # Group by colour for efficient rendering
    colour_groups = tiles.groupby("background_hex")

    for colour, group in colour_groups:
        if colour == "#FFFFFF":
            continue  # Skip empty cells

        # Build hover text
        hover = group.apply(
            lambda r: f"<b>{r['tile']}</b><br>Artist: {r['artist']}<br>Completion: {r['completion_label']}",
            axis=1
        )

        fig.add_trace(go.Scatter(
            x=group["x"],
            y=group["y"],
            mode="markers",
            marker=dict(
                color=colour,
                size=10,
                symbol="square",
                line=dict(color="#0f1117", width=0.5)
            ),
            hovertemplate="%{text}<extra></extra>",
            text=hover,
            showlegend=False
        ))

    fig.update_layout(
        paper_bgcolor="#0f1117",
        plot_bgcolor="#1a1d27",
        font=dict(color="#e8eaf0", family="Space Mono"),
        xaxis=dict(
            showgrid=True, gridcolor="#2a2d3a",
            zeroline=False, title="X Coordinate"
        ),
        yaxis=dict(
            showgrid=True, gridcolor="#2a2d3a",
            zeroline=False, title="Y Coordinate",
            autorange=True
        ),
        margin=dict(l=20, r=20, t=20, b=20),
        height=480,
        hovermode="closest"
    )

    st.plotly_chart(fig, use_container_width=True)


# ── Raw Data Explorer ─────────────────────────────────────────────────────────

st.markdown('<div class="section-header">Data Explorer</div>', unsafe_allow_html=True)

filter_artist = st.multiselect(
    "Filter by Artist",
    options=sorted(tiles["artist"].unique()),
    default=[]
)

display_df = tiles if not filter_artist else tiles[tiles["artist"].isin(filter_artist)]

st.dataframe(
    display_df[["tile", "artist", "completion_pct", "completion_label", "background_hex"]],
    use_container_width=True,
    height=280
)

# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown(
    f'<p style="color:#333650;font-size:0.75rem;text-align:center;margin-top:2rem;">'
    f'Last data refresh: run tilemap_tracker.py to update · {total_tiles} cells parsed</p>',
    unsafe_allow_html=True
)
