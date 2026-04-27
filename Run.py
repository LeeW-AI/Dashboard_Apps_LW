"""
run.py — Tilemap Tracker Launcher
──────────────────────────────────
Runs the data pipeline then launches the Streamlit dashboard.

Usage:
    python run.py              # fetch fresh data + open dashboard
    python run.py --dash-only  # skip fetch, just open dashboard
"""

import sys
import subprocess

def run_tracker():
    print("🗺️  Running tilemap tracker...\n")
    result = subprocess.run([sys.executable, "tilemap_tracker.py"])
    if result.returncode != 0:
        print("\n❌ Tracker failed. Fix the errors above before launching the dashboard.")
        sys.exit(1)
    print("\n✅ Data ready.\n")

def launch_dashboard():
    print("🚀 Launching dashboard — opening in your browser...\n")
    subprocess.run([sys.executable, "-m", "streamlit", "run", "dashboard.py"])

if __name__ == "__main__":
    dash_only = "--dash-only" in sys.argv

    if not dash_only:
        run_tracker()

    launch_dashboard()
