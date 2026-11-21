"""Fills demo_weather.db with 3 days of fake data (same schema as the real collector)
so the dashboard can be tested before the real 3-day run is finished.

    python make_demo_data.py
    DASHBOARD_DEMO=1 streamlit run dashboard.py      (PowerShell: $env:DASHBOARD_DEMO="1")
"""
import os
from datetime import datetime, timedelta

import numpy as np

import database

database.DATABASE_NAME = "demo_weather.db"
if os.path.exists(database.DATABASE_NAME):
    os.remove(database.DATABASE_NAME)
database.initialise_database()
rng = np.random.default_rng(7)
fmt = "%Y-%m-%dT%H:%M"


def truth(t):
    hour = t.hour + t.minute / 60
    wave = np.sin((hour - 9) / 24 * 2 * np.pi)
    rainy = 14 <= t.hour <= 18
    return 27 + 5 * wave, 80 - 15 * wave, 0.6 if rainy else 0.0


end = datetime.now().replace(minute=0, second=0, microsecond=0)
start = end - timedelta(days=3)
statements = []

t = start
while t <= end:                                   # 15-minute "current" readings
    temp, hum, rain = truth(t)
    statements.append((
        "INSERT OR IGNORE INTO weather_observations (observed_at,temperature,humidity,"
        "precipitation,wind_speed,collected_at,source) VALUES (?,?,?,?,?,?,?)",
        (t.strftime(fmt), temp + rng.normal(0, .4), hum + rng.normal(0, 2),
         round(max(0, rng.normal(rain / 4, .1)), 2), abs(rng.normal(8, 2)),
         t.strftime(fmt), database.CURRENT_SOURCE)))
    t += timedelta(minutes=15)

t = start
while t < end:                                    # hourly forecasts, 48 h ahead
    for lead in range(1, 49):
        target = t + timedelta(hours=lead)
        if target > end:
            break
        temp, hum, rain = truth(target)
        sd = 0.12 * lead ** 0.5
        statements.append((
            "INSERT OR IGNORE INTO weather_forecasts (forecast_retrieved_at,forecast_for,"
            "temperature,humidity,precipitation,wind_speed,collected_at) VALUES (?,?,?,?,?,?,?)",
            (t.strftime("%Y-%m-%dT%H:%M:%S+08:00"), target.strftime(fmt),
             temp + rng.normal(0.4, sd), hum + rng.normal(-2, sd * 2 + 1),
             round(max(0, rng.normal(rain, 0.5)), 2), abs(rng.normal(8, 2)), t.strftime(fmt))))
    statements.append((
        "INSERT INTO collector_runs (run_at,status,observed_at,forecast_rows,backfill_rows,message) "
        "VALUES (?,?,?,?,?,?)", (t.strftime(fmt), "success", t.strftime(fmt), 48, 0, None)))
    t += timedelta(hours=1)

for i in range(0, len(statements), 400):
    database.run_statements(statements[i:i + 400])
database.print_record_counts()
