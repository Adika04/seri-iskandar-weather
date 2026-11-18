CREATE TABLE IF NOT EXISTS weather_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    observed_at TEXT NOT NULL UNIQUE,
    temperature REAL,
    humidity REAL,
    precipitation REAL,
    wind_speed REAL,
    collected_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'Open-Meteo Forecast API current conditions'
);

CREATE TABLE IF NOT EXISTS weather_forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    forecast_retrieved_at TEXT NOT NULL,
    forecast_for TEXT NOT NULL,
    temperature REAL,
    humidity REAL,
    precipitation REAL,
    wind_speed REAL,
    collected_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'Open-Meteo Forecast API hourly forecast',
    UNIQUE (forecast_retrieved_at, forecast_for)
);

-- One row per collector run (success or failure). Evidence of logging/retries for
-- the 3-day run that survives even when the GitHub Actions logs expire.
CREATE TABLE IF NOT EXISTS collector_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_at TEXT NOT NULL,
    status TEXT NOT NULL,
    observed_at TEXT,
    forecast_rows INTEGER,
    backfill_rows INTEGER,
    message TEXT
);

CREATE INDEX IF NOT EXISTS idx_observations_time
    ON weather_observations(observed_at);

CREATE INDEX IF NOT EXISTS idx_forecasts_target_time
    ON weather_forecasts(forecast_for);

CREATE INDEX IF NOT EXISTS idx_forecasts_retrieval_time
    ON weather_forecasts(forecast_retrieved_at);

CREATE INDEX IF NOT EXISTS idx_runs_time
    ON collector_runs(run_at);
