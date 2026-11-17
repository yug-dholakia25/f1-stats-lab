# F1 Stats Lab

A Python + Streamlit dashboard for Formula 1 season statistics.

## Features
- Drivers' World Champion by season
- Constructors' World Champion by season
- Every race podium (P1, P2, P3) and race winners
- Laps led by driver per season (derived from lap-by-lap P1 timing)
- DNF counts by driver and constructor
- Filterable raw race results and CSV export

## Run locally

Python 3.10+ recommended.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

The dashboard opens in your browser, usually at http://localhost:8501.

## Data source and notes
Uses the public Jolpica-F1 API, an Ergast-compatible Formula 1 results API:
https://api.jolpi.ca/ergast/f1/

No API key is required for the public endpoints used here. Requests are cached for one hour, use a descriptive User-Agent, and page through the API's capped response sizes. A first full 10-season laps-led load can be slow and may approach the provider's hourly request limit.

- The default view is the latest 10 calendar seasons, including the current season (which may be incomplete).
- Lap counts are calculated by counting each lap where the API's lap timing feed records a driver in P1. Missing lap timing feeds are reported in the app's "Data notes / API gaps" section.
- DNF is defined as a result status other than `Finished` or a classified `+N Laps` result. This intentionally includes non-finish classifications such as disqualifications; inspect the status field for detail.
- Provider data can be corrected after races. The app is for exploration and learning, not official classification.
