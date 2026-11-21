"""Streamlit dashboard: Seri Iskandar weather, forecast vs actual.

Run locally:   streamlit run dashboard.py
Demo data:     python make_demo_data.py   then   DASHBOARD_DEMO=1 streamlit run dashboard.py
Streamlit Cloud: add TURSO_DATABASE_URL and TURSO_AUTH_TOKEN under the app's Secrets.
"""
import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Streamlit secrets -> environment variables, BEFORE importing database
for _key in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN"):
    try:
        if _key in st.secrets:
            os.environ[_key] = st.secrets[_key]
    except Exception:
        pass

import database  # noqa: E402

if os.environ.get("DASHBOARD_DEMO") == "1":
    database.DATABASE_NAME = "demo_weather.db"

import dashboard_data as dd  # noqa: E402

st.set_page_config(page_title="Seri Iskandar Weather Monitor", page_icon="🌦️", layout="wide")


@st.cache_data(ttl=300, show_spinner="Loading data...")
def load_all(backend):
    obs = dd.load_observations()
    fc = dd.load_forecasts()
    runs = dd.load_runs()
    actuals = dd.hourly_actuals(obs)
    return obs, fc, runs, actuals, dd.join_forecast_actual(fc, actuals)


try:
    obs, fc, runs, actuals, joined = load_all(database.backend_name())
except Exception as error:
    st.error(f"Could not read the database: {error}")
    st.info("Check the Turso secrets, or run make_demo_data.py and set DASHBOARD_DEMO=1.")
    st.stop()

st.title("🌦️ Seri Iskandar Weather Monitor")
st.caption("Open-Meteo forecast vs actual • " + database.backend_name())

if obs.empty:
    st.warning("No observations yet. Wait for the collector to run.")
    st.stop()

# ---------------------------------------------------------------- sidebar
st.sidebar.header("Filters")
# Live collection starts at the first 'current' reading. Earlier rows are the API's
# one-day back-fill, not real-time collection, so they are excluded by default.
live = obs[obs["source"] == database.CURRENT_SOURCE]
first_live = live["observed_at"].min() if not live.empty else obs["observed_at"].min()
last_live = live["observed_at"].max() if not live.empty else obs["observed_at"].max()
only_live = st.sidebar.checkbox("Official collection window only", value=True,
                                help=f"Start from the first live reading ({first_live:%d %b %H:%M}).")
window_start = first_live if only_live else obs["observed_at"].min()
d_min, d_max = window_start.date(), obs["observed_at"].max().date()
picked = st.sidebar.date_input("Date range", (d_min, d_max), min_value=d_min, max_value=d_max)
if len(picked) == 2:
    start, end = pd.Timestamp(picked[0]), pd.Timestamp(picked[1]) + pd.Timedelta(days=1)
else:
    start, end = pd.Timestamp(d_min), pd.Timestamp(d_max) + pd.Timedelta(days=1)
start = max(start, window_start)

variable = st.sidebar.selectbox("Variable", list(dd.VARIABLES), format_func=dd.VARIABLES.get)
lead = st.sidebar.slider("Forecast lead time (hours ahead)", 1, 48, 6)

obs_f = obs[(obs["observed_at"] >= start) & (obs["observed_at"] < end)]
joined_f = joined[(joined["forecast_for"] >= start) & (joined["forecast_for"] < end)] if not joined.empty else joined

# ---------------------------------------------------------------- KPI cards
latest = obs.iloc[-1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Temperature", f"{latest.temperature:.1f} °C")
c2.metric("Humidity", f"{latest.humidity:.0f} %")
c3.metric("Rainfall (last 15 min)", f"{latest.precipitation:.1f} mm")
c4.metric("Wind speed", f"{latest.wind_speed:.1f} km/h")
st.caption(f"Latest reading: {latest.observed_at:%d %b %Y %H:%M} (model-based current conditions)")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Forecast vs Actual", "Accuracy", "Rain Forecast", "Data Collection", "Raw Data"])

# ---------------------------------------------------------------- tab 1
with tab1:
    st.subheader(f"{dd.VARIABLES[variable]}: forecast made ~{lead} h ahead vs actual")
    act = actuals[(actuals["forecast_for"] >= start) & (actuals["forecast_for"] < end)]
    sel = joined_f[joined_f["lead_h"] == lead] if not joined_f.empty else joined_f
    if act.empty:
        st.info("No hourly actuals in this range yet.")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=act["forecast_for"], y=act[variable], name="Actual", line=dict(width=3)))
        if not sel.empty:
            by_hour = sel.groupby("forecast_for")[f"{variable}_fc"].mean()
            fig.add_trace(go.Scatter(x=by_hour.index, y=by_hour.values,
                                     name=f"Forecast ({lead} h ahead)", line=dict(dash="dash")))
        fig.update_layout(hovermode="x unified", height=430, margin=dict(t=20),
                          yaxis_title=dd.VARIABLES[variable])
        st.plotly_chart(fig, use_container_width=True)
        if not sel.empty:
            pair = sel.groupby("forecast_for")[[f"{variable}_fc", f"{variable}_act"]].mean().reset_index()
            sc = px.scatter(pair, x=f"{variable}_act", y=f"{variable}_fc",
                            labels={f"{variable}_act": "Actual", f"{variable}_fc": "Forecast"},
                            title="Forecast vs actual (points on the diagonal = perfect)")
            lo = min(pair[f"{variable}_act"].min(), pair[f"{variable}_fc"].min())
            hi = max(pair[f"{variable}_act"].max(), pair[f"{variable}_fc"].max())
            sc.add_shape(type="line", x0=lo, y0=lo, x1=hi, y1=hi, line=dict(dash="dot"))
            st.plotly_chart(sc, use_container_width=True)

# ---------------------------------------------------------------- tab 2
with tab2:
    st.subheader("Forecast error by variable and lead time")
    metrics = dd.error_metrics(joined_f)
    if metrics.empty:
        st.info("Not enough forecast/actual overlap yet.")
    else:
        metric = st.radio("Metric", ["MAE", "RMSE", "Bias"], horizontal=True)
        st.plotly_chart(px.bar(metrics, x="lead_bucket", y=metric, color="variable", barmode="group",
                               labels={"lead_bucket": "Lead time (hours)"}), use_container_width=True)
        pivot = metrics.pivot(index="variable", columns="lead_bucket", values=metric)
        st.plotly_chart(px.imshow(pivot, text_auto=".2f", aspect="auto",
                                  color_continuous_scale="Blues", title=f"{metric} heatmap"),
                        use_container_width=True)
        st.dataframe(metrics.round(3), use_container_width=True)

# ---------------------------------------------------------------- tab 3
with tab3:
    st.subheader("Rain forecast quality (yes/no)")
    st.caption("Actual rain = at least 0.1 mm in the hour. The collector stores forecast rainfall in mm "
               "(no probability), so a rain alert is 'forecast rainfall above the threshold'.")
    threshold = st.select_slider("Forecast rain threshold (mm)", [0.1, 0.2, 0.5, 1.0, 2.0], value=0.1)
    rain = dd.rain_metrics(joined_f, threshold)
    if not rain:
        st.info("No data yet.")
    else:
        r1, r2, r3 = st.columns(3)
        r1.metric("Hit rate", f"{rain['hit_rate']:.0%}")
        r2.metric("False alarm ratio", f"{rain['false_alarm_ratio']:.0%}")
        r3.metric("Overall accuracy", f"{rain['accuracy']:.0%}")
        table = pd.DataFrame(
            [[rain["hits"], rain["misses"]], [rain["false_alarms"], rain["correct_negatives"]]],
            index=["Forecast: rain", "Forecast: no rain"], columns=["Actual: rain", "Actual: no rain"])
        st.plotly_chart(px.imshow(table, text_auto=True, color_continuous_scale="Blues",
                                  title="Rain contingency table"), use_container_width=True)

# ---------------------------------------------------------------- tab 4
with tab4:
    st.subheader("Collection progress (3-day requirement)")
    hours = (last_live - first_live).total_seconds() / 3600
    st.caption(f"Live collection: {first_live:%d %b %Y %H:%M} to {last_live:%d %b %Y %H:%M}")
    k1, k2, k3 = st.columns(3)
    k1.metric("Data span", f"{hours:.1f} h", "3-day requirement met" if hours >= 72 else "below 72 h")
    k2.metric("Observation rows", len(obs))
    k3.metric("Forecast rows", len(fc))
    per_day = (obs[obs["source"] == database.CURRENT_SOURCE]
               .groupby(obs["observed_at"].dt.date).size().rename("current readings").reset_index())
    per_day.columns = ["date", "current readings"]
    if not per_day.empty:
        st.plotly_chart(px.bar(per_day, x="date", y="current readings",
                               title="Current readings per day (96 = every 15 min)"),
                        use_container_width=True)
    if not runs.empty:
        st.write("Collector runs:", runs["status"].value_counts().to_dict())

# ---------------------------------------------------------------- tab 5
with tab5:
    st.subheader("Observations")
    st.dataframe(obs_f, use_container_width=True)
    st.download_button("Download observations (CSV)", obs_f.to_csv(index=False), "observations.csv")
    if not joined_f.empty:
        st.download_button("Download forecast vs actual (CSV)", joined_f.to_csv(index=False),
                           "forecast_vs_actual.csv")