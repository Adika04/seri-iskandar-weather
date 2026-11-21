"""Data loading and forecast-accuracy metrics for the dashboard.

Reads through the team's database.py, so it works with Turso (hosted) or the
local weather.db without changes. Only SELECT statements are used.
"""
import numpy as np
import pandas as pd

import database

VARIABLES = {
    "temperature": "Temperature (°C)",
    "humidity": "Humidity (%)",
    "precipitation": "Rainfall (mm)",
    "wind_speed": "Wind speed (km/h)",
}
LEAD_BINS = [0, 3, 6, 12, 24, 48]
RAIN_ACTUAL_MM = 0.1


def _local_time(series):
    """'2026-11-18T14:15:03+08:00' or '2026-11-18T14:15' -> naive local datetime."""
    return pd.to_datetime(series.str[:19])


def load_observations():
    rows = database.query(
        "SELECT observed_at, temperature, humidity, precipitation, wind_speed, source "
        "FROM weather_observations ORDER BY observed_at"
    )
    df = pd.DataFrame(rows, columns=["observed_at", "temperature", "humidity",
                                     "precipitation", "wind_speed", "source"])
    if not df.empty:
        df["observed_at"] = _local_time(df["observed_at"])
    return df


def load_forecasts():
    rows = database.query(
        "SELECT forecast_retrieved_at, forecast_for, temperature, humidity, "
        "precipitation, wind_speed FROM weather_forecasts"
    )
    df = pd.DataFrame(rows, columns=["retrieved_at", "forecast_for", "temperature",
                                     "humidity", "precipitation", "wind_speed"])
    if not df.empty:
        df["retrieved_at"] = _local_time(df["retrieved_at"])
        df["forecast_for"] = _local_time(df["forecast_for"])
        df["lead_hours"] = (df["forecast_for"] - df["retrieved_at"]).dt.total_seconds() / 3600
        df["lead_h"] = np.ceil(df["lead_hours"]).astype(int)
    return df


def load_runs():
    rows = database.query("SELECT run_at, status, message FROM collector_runs ORDER BY run_at")
    df = pd.DataFrame(rows, columns=["run_at", "status", "message"])
    if not df.empty:
        df["run_at"] = _local_time(df["run_at"])
    return df


def hourly_actuals(obs):
    """One 'actual' row per clock hour.

    Temperature, humidity and wind are instantaneous, so the reading at HH:00 is used.
    Open-Meteo's hourly rainfall is the sum over the PRECEDING hour, whereas a 'current'
    reading's rainfall covers only the preceding 15 min. So hourly rainfall is rebuilt by
    summing the four current readings (HH-45, HH-30, HH-15, HH:00); if one is missing,
    the stored back-filled hourly value is used instead (when the HH:00 row is back-fill).
    """
    if obs.empty:
        return pd.DataFrame()
    on_hour = obs[obs["observed_at"].dt.minute == 0].set_index("observed_at")
    actual = on_hour[["temperature", "humidity", "wind_speed"]].copy()

    current = obs[obs["source"] == database.CURRENT_SOURCE].copy()
    current["hour_end"] = current["observed_at"].dt.ceil("h")
    grouped = current.groupby("hour_end")["precipitation"].agg(["sum", "count"])
    rain = grouped.loc[grouped["count"] == 4, "sum"]

    backfill_rain = on_hour.loc[on_hour["source"] == database.BACKFILL_SOURCE, "precipitation"]
    actual["precipitation"] = rain.reindex(actual.index).fillna(backfill_rain.reindex(actual.index))
    actual.index.name = "forecast_for"
    return actual.reset_index()


def join_forecast_actual(forecasts, actuals):
    if forecasts.empty or actuals.empty:
        return pd.DataFrame()
    return forecasts.merge(actuals, on="forecast_for", suffixes=("_fc", "_act"))


def error_metrics(joined):
    """MAE, RMSE and bias for each variable and lead-time bucket."""
    if joined.empty:
        return pd.DataFrame()
    data = joined.copy()
    data["lead_bucket"] = pd.cut(data["lead_hours"], bins=LEAD_BINS, include_lowest=True).astype(str)
    rows = []
    for var, label in VARIABLES.items():
        data["_err"] = data[f"{var}_fc"] - data[f"{var}_act"]
        valid = data.dropna(subset=["_err"])
        for bucket, grp in valid.groupby("lead_bucket"):
            rows.append({"variable": label, "lead_bucket": bucket,
                         "MAE": grp["_err"].abs().mean(),
                         "RMSE": float(np.sqrt((grp["_err"] ** 2).mean())),
                         "Bias": grp["_err"].mean(), "n": len(grp)})
    out = pd.DataFrame(rows)
    order = {str(b): i for i, b in enumerate(
        pd.cut([0.5, 2, 5, 10, 20, 40], bins=LEAD_BINS, include_lowest=True).categories)}
    out["_o"] = out["lead_bucket"].map(order)
    return out.sort_values(["variable", "_o"]).drop(columns="_o").reset_index(drop=True)


def rain_metrics(joined, forecast_mm_threshold=0.1):
    """Yes/no rain verification: hit rate, false alarm ratio, accuracy."""
    data = joined.dropna(subset=["precipitation_fc", "precipitation_act"]) if not joined.empty else joined
    if data.empty:
        return {}
    actual = data["precipitation_act"] >= RAIN_ACTUAL_MM
    predicted = data["precipitation_fc"] >= forecast_mm_threshold
    hits = int((actual & predicted).sum())
    misses = int((actual & ~predicted).sum())
    false_alarms = int((~actual & predicted).sum())
    correct_neg = int((~actual & ~predicted).sum())
    total = len(data)
    return {
        "hits": hits, "misses": misses, "false_alarms": false_alarms,
        "correct_negatives": correct_neg, "n": total,
        "hit_rate": hits / (hits + misses) if (hits + misses) else float("nan"),
        "false_alarm_ratio": false_alarms / (hits + false_alarms) if (hits + false_alarms) else float("nan"),
        "accuracy": (hits + correct_neg) / total,
    }