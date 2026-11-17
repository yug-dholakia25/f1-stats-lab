import requests
import pandas as pd
import streamlit as st
import plotly.express as px
from functools import lru_cache

API = "https://api.jolpi.ca/ergast/f1"

st.set_page_config(page_title="F1 Stats Lab", page_icon="🏎️", layout="wide")
st.title("🏎️ F1 Stats Lab")
st.caption("Explore Formula 1 results, championships, laps led and retirements across the last 10 seasons.")

@st.cache_data(ttl=3600, show_spinner=False)
def api_get(path, params=None):
    url = f"{API}/{path.strip('/')}.json"
    headers = {"User-Agent": "F1StatsLab/1.0 (personal statistics dashboard)"}
    r = requests.get(url, params=params or {"limit": 100}, headers=headers, timeout=30)
    r.raise_for_status()
    payload = r.json()["MRData"]
    return payload

def fetch_season_results(year):
    # Jolpica caps page sizes; walk offsets so a full season is not silently truncated.
    merged = {}
    offset = 0
    while True:
        data = api_get(f"{year}/results", {"limit": 100, "offset": offset})
        page = data["RaceTable"]["Races"]
        for race in page:
            key = race["round"]
            if key not in merged:
                merged[key] = {**race, "Results": []}
            merged[key]["Results"].extend(race.get("Results", []))
        total = int(data.get("total", 0))
        offset += int(data.get("limit", 100))
        if offset >= total or not page:
            break
    races = list(merged.values())
    rows = []
    for race in races:
        for result in race.get("Results", []):
            rows.append({
                "Year": year,
                "Round": int(race["round"]),
                "Race": race["raceName"],
                "Date": race["date"],
                "Driver": f'{result["Driver"]["givenName"]} {result["Driver"]["familyName"]}',
                "DriverId": result["Driver"]["driverId"],
                "Constructor": result["Constructor"]["name"],
                "ConstructorId": result["Constructor"]["constructorId"],
                "Grid": result.get("grid"),
                "Position": result.get("position"),
                "PositionText": result.get("positionText"),
                "Status": result.get("status", ""),
                "Laps": int(result.get("laps", 0)),
                "Points": float(result.get("points", 0)),
            })
    return pd.DataFrame(rows), races

def fetch_standings(year, kind):
    data = api_get(f"{year}/{kind}Standings", {"limit": 1000})
    lists = data["StandingsTable"]["StandingsLists"]
    if not lists:
        return pd.DataFrame()
    key = "DriverStandings" if kind == "driver" else "ConstructorStandings"
    rows = []
    for item in lists[-1].get(key, []):
        if kind == "driver":
            rows.append({"Position": int(item["position"]), "Name": f'{item["Driver"]["givenName"]} {item["Driver"]["familyName"]}',
                         "Team": item.get("Constructors", [{}])[0].get("name", ""), "Points": float(item["points"]),
                         "Wins": int(item["wins"])})
        else:
            rows.append({"Position": int(item["position"]), "Name": item["Constructor"]["name"],
                         "Points": float(item["points"]), "Wins": int(item["wins"])})
    return pd.DataFrame(rows)

def fetch_laps_leader(year, races):
    # Jolpica's Ergast-compatible lap endpoint exposes the driver in P1 on each lap.
    counts = {}
    unavailable = []
    for race in races:
        rnd = race["round"]
        try:
            # Lap timings are paginated by timing row (maximum page size is 100).
            offset = 0
            leader_by_lap = {}
            while True:
                data = api_get(f"{year}/{rnd}/laps", {"limit": 100, "offset": offset})
                lap_rows = data["RaceTable"]["Races"]
                if not lap_rows:
                    break
                for lap in lap_rows[0].get("Laps", []):
                    for timing in lap.get("Timings", []):
                        if timing.get("position") == "1":
                            leader_by_lap[int(lap["number"])] = timing["driverId"]
                total = int(data.get("total", 0))
                offset += int(data.get("limit", 100))
                if offset >= total:
                    break
            for did in leader_by_lap.values():
                counts[did] = counts.get(did, 0) + 1
        except Exception:
            unavailable.append(race.get("raceName", f"Round {rnd}"))
    return counts, unavailable

@st.cache_data(ttl=3600, show_spinner=False)
def load_year(year):
    results, races = fetch_season_results(year)
    drivers = fetch_standings(year, "driver")
    constructors = fetch_standings(year, "constructor")
    lap_counts, lap_unavailable = fetch_laps_leader(year, races)
    return results, drivers, constructors, lap_counts, lap_unavailable

current_year = pd.Timestamp.now().year
start_default = max(2017, current_year - 9)
years = list(range(2010, current_year + 1))
with st.sidebar:
    st.header("Season range")
    start_year = st.selectbox("From season", years, index=years.index(start_default))
    end_year = st.selectbox("To season", years, index=years.index(current_year))
    st.caption("The default range is the latest 10 calendar seasons. The current season may be incomplete.")
    if start_year > end_year:
        st.error("'From season' must be earlier than or equal to 'To season'.")

if start_year <= end_year:
    selected_years = list(range(start_year, end_year + 1))
    all_results, all_drivers, all_constructors, lap_records, issues = [], [], [], [], []
    progress = st.progress(0, text="Loading season data…")
    for i, year in enumerate(selected_years):
        try:
            results, drivers, constructors, lap_counts, lap_unavailable = load_year(year)
            if not results.empty:
                all_results.append(results)
            if not drivers.empty:
                d = drivers.copy(); d["Year"] = year; all_drivers.append(d)
            if not constructors.empty:
                c = constructors.copy(); c["Year"] = year; all_constructors.append(c)
            driver_names = {}
            if not results.empty:
                driver_names = results.drop_duplicates("DriverId").set_index("DriverId")["Driver"].to_dict()
            for did, count in lap_counts.items():
                lap_records.append({"Year": year, "Driver": driver_names.get(did, did), "Laps led": count})
            if lap_unavailable:
                issues.append(f"{year}: lap data unavailable for {len(lap_unavailable)} race(s)")
        except Exception as e:
            issues.append(f"{year}: {e}")
        progress.progress((i + 1) / len(selected_years), text=f"Loaded {year}")
    progress.empty()

    results = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()
    driver_standings = pd.concat(all_drivers, ignore_index=True) if all_drivers else pd.DataFrame()
    constructor_standings = pd.concat(all_constructors, ignore_index=True) if all_constructors else pd.DataFrame()
    laps_df = pd.DataFrame(lap_records)

    if results.empty:
        st.warning("No race results were returned. Check your internet connection or try again later.")
    else:
        latest = results["Year"].max()
        podium = results[results["Position"].isin(["1", "2", "3"])].copy()
        podium["Position"] = podium["Position"].astype(int)
        champions = driver_standings[driver_standings["Position"] == 1].sort_values("Year") if not driver_standings.empty else pd.DataFrame()
        constructors_champs = constructor_standings[constructor_standings["Position"] == 1].sort_values("Year") if not constructor_standings.empty else pd.DataFrame()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Seasons loaded", f"{len(selected_years)}")
        c2.metric("Race results", f"{len(results):,}")
        c3.metric("Podium finishes", f"{len(podium):,}")
        c4.metric("Latest season in data", str(latest))

        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🏆 Champions", "🥇 Podiums", "🟣 Laps led", "⚠️ DNFs", "📊 Explore data"
        ])

        with tab1:
            st.subheader("World Drivers' Champions")
            if not champions.empty:
                st.dataframe(champions[["Year", "Name", "Team", "Points", "Wins"]].rename(
                    columns={"Name":"Champion", "Team":"Constructor"}), hide_index=True, use_container_width=True)
            st.subheader("World Constructors' Champions")
            if not constructors_champs.empty:
                st.dataframe(constructors_champs[["Year", "Name", "Points", "Wins"]].rename(
                    columns={"Name":"Champion constructor"}), hide_index=True, use_container_width=True)
            if not champions.empty:
                fig = px.bar(champions, x="Year", y="Points", color="Name", title="Drivers' champion points by season")
                st.plotly_chart(fig, use_container_width=True)

        with tab2:
            st.subheader("Every podium finish")
            year_filter = st.selectbox("Filter podiums by season", ["All seasons"] + selected_years, key="pod_year")
            p = podium if year_filter == "All seasons" else podium[podium["Year"] == year_filter]
            p = p.sort_values(["Year", "Round", "Position"])
            st.dataframe(p[["Year", "Round", "Race", "Position", "Driver", "Constructor"]].rename(
                columns={"Position":"Place"}), hide_index=True, use_container_width=True)
            wins = podium[podium["Position"] == 1].groupby(["Driver", "Constructor"]).size().reset_index(name="Wins").sort_values("Wins", ascending=False)
            st.subheader("Race winners in selected range")
            st.dataframe(wins, hide_index=True, use_container_width=True)

        with tab3:
            st.subheader("Laps led by driver, season by season")
            if laps_df.empty:
                st.info("Lap-by-lap leader data was not available from the API for this range.")
            else:
                pivot = laps_df.pivot_table(index="Driver", columns="Year", values="Laps led", aggfunc="sum", fill_value=0)
                st.dataframe(pivot, use_container_width=True)
                chosen_year = st.selectbox("Season chart", selected_years, key="lap_year")
                year_laps = laps_df[laps_df["Year"] == chosen_year].sort_values("Laps led", ascending=False)
                if not year_laps.empty:
                    fig = px.bar(year_laps, x="Driver", y="Laps led", title=f"Laps led — {chosen_year}")
                    st.plotly_chart(fig, use_container_width=True)
            st.caption("A lap is credited to the driver recorded in P1 at the end of that lap. Lap timings are paginated, so this can make the first full load slow and may approach the API hourly request limit. Results are cached for one hour.")

        with tab4:
            st.subheader("DNFs by driver and constructor")
            # Count retirements/non-classified outcomes; exclude normal classified finishes.
            dnf = results[~results["Status"].isin(["Finished"]) & ~results["Status"].str.match(r"^\+\d+ Laps?$", na=False)].copy()
            dnf["Season"] = dnf["Year"]
            left, right = st.columns(2)
            with left:
                st.markdown("**DNFs by driver**")
                by_driver = dnf.groupby("Driver").size().reset_index(name="DNFs").sort_values("DNFs", ascending=False)
                st.dataframe(by_driver, hide_index=True, use_container_width=True)
            with right:
                st.markdown("**DNFs by constructor**")
                by_team = dnf.groupby("Constructor").size().reset_index(name="DNFs").sort_values("DNFs", ascending=False)
                st.dataframe(by_team, hide_index=True, use_container_width=True)
            st.caption("DNF definition used here: result status is not 'Finished' and is not a classified finish expressed as '+N Laps'. This includes retirements and disqualifications; use the status column in Explore data to inspect individual cases.")
            if not dnf.empty:
                fig = px.bar(by_team.head(15), x="Constructor", y="DNFs", title="Most DNFs by constructor")
                st.plotly_chart(fig, use_container_width=True)

        with tab5:
            st.subheader("Raw race-result explorer")
            q1, q2 = st.columns(2)
            with q1:
                season_pick = st.selectbox("Season", selected_years, key="raw_year")
            with q2:
                teams = ["All constructors"] + sorted(results["Constructor"].dropna().unique().tolist())
                team_pick = st.selectbox("Constructor", teams)
            raw = results[results["Year"] == season_pick]
            if team_pick != "All constructors":
                raw = raw[raw["Constructor"] == team_pick]
            st.dataframe(raw.sort_values(["Round", "Position"], na_position="last"), hide_index=True, use_container_width=True)
            st.download_button("Download filtered results CSV", raw.to_csv(index=False).encode("utf-8"), "f1_results.csv", "text/csv")

    if issues:
        with st.expander("Data notes / API gaps"):
            for issue in issues:
                st.write("• " + issue)

st.divider()
st.caption("Data source: Jolpica-F1 API (Ergast-compatible). Data is fetched live and cached for one hour. API page sizes and rate limits are respected. Historical records and current-season results may be corrected by the provider.")
