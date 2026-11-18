# Seri Iskandar Weather Pipeline (Phase 1: data pipeline)

## What this project does
- Retrieves current conditions and hourly forecasts from Open-Meteo every 15 minutes.
- Runs in the cloud: a GitHub Actions schedule calls `python main.py --once`.
- Stores everything in a hosted SQLite database (Turso), so the dashboard/analytics
  teammates can read it from anywhere.
- Retries failed API and database requests, logs to the console and `logs/collector.log`,
  and records every run (success or failure) in the `collector_runs` table.

```
GitHub Actions (cron */15)  ->  Open-Meteo API
        |                              |
        +--> main.py --once --> Turso (SQLite over HTTPS) --> dashboard (Streamlit etc.)
```

## One-time cloud setup

### 1. Create the Turso database (free)
Sign up at https://turso.tech (or install the CLI), then:
```
turso db create weather
turso db show weather --url          # copy this: libsql://weather-<you>.turso.io
turso db tokens create weather       # copy this: the collector's read/write token
turso db tokens create weather --read-only   # optional: give this one to the dashboard
```
The tables are created automatically on the first run.

### 2. Put the code on GitHub
Create a repository (a **public** one has unlimited free Actions minutes; a private one
has a monthly allowance, which 15-minute runs will exceed after a few days), push this
folder to the **default branch** (scheduled workflows only run from the default branch).

### 3. Add the secrets
Repository > Settings > Secrets and variables > Actions > New repository secret:
- `TURSO_DATABASE_URL` = the `libsql://...` URL
- `TURSO_AUTH_TOKEN`   = the read/write token

### 4. Start the run
Actions tab > "Collect weather data" > Run workflow (first manual run, to check it is
green). After that it runs by itself every ~15 minutes. **Note the start time: the
3-day clock starts here.** GitHub can delay scheduled runs by a few minutes; the hourly
back-fill (below) covers any skipped run.

### 5. Check on it
```
set TURSO_DATABASE_URL=libsql://...        (PowerShell: $env:TURSO_DATABASE_URL="...")
set TURSO_AUTH_TOKEN=...
py run_summary.py
```
`run_summary.py` prints the time span, rows per day, hour coverage, gaps, forecast
snapshots and failed runs. Use its output as evidence in the report.

## Running locally (optional, for development)
```
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py main.py --once
```
With no Turso variables set, data goes to a local `weather.db`. `py main.py` collects
continuously every 15 minutes. Tests: `py -m unittest discover -s tests -v`.

## Data interpretation (state this in the report)
Open-Meteo "current" values are model-based estimates, not readings from a physical
station.

- `weather_observations` holds two kinds of row, told apart by `source`:
  - `Open-Meteo Forecast API current conditions`: a 15-minute reading taken at collection time.
  - `Open-Meteo Forecast API hourly values (backfill)`: the model's hourly value for a
    past hour, added on every run for the previous day. Guarantees an hourly-aligned
    "actual" for every hour even if a scheduled run was missed. Never overwrites a real
    current reading.
- `weather_forecasts` holds only genuine forecasts: each snapshot contains hours strictly
  after the reading it was retrieved with. `forecast_retrieved_at` is when our collector
  fetched it (not the model's internal run time); `forecast_for` is the target hour.
- Forecast horizon = `forecast_for` minus `forecast_retrieved_at`.
- To compare forecast vs actual, join `forecast_for` to the observation whose
  `observed_at` is the same hour (minute `:00`).

## Database tables
### weather_observations
observed_at (unique), temperature (°C), humidity (%), precipitation (mm), wind_speed (km/h),
collected_at, source

### weather_forecasts
forecast_retrieved_at, forecast_for, temperature (°C), humidity (%), precipitation (mm),
wind_speed (km/h), collected_at, source. Unique on (forecast_retrieved_at, forecast_for).

### collector_runs
run_at, status (`success` / `failure`), observed_at, forecast_rows, backfill_rows, message

## Notes for the team
- Do not rename tables or columns without coordinating with the analytics/dashboard members.
- The dashboard and analytics code should only read the database; there must be one
  collector (the GitHub workflow). Do not also run `py main.py` against the Turso database.
- Dashboard code can reuse `database.py`:
  ```python
  import database
  rows = database.query("SELECT * FROM weather_observations ORDER BY observed_at DESC LIMIT 10")
  ```
  It only needs `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` (a read-only token is enough).
  On Streamlit Community Cloud, put these in the app's Secrets and expose them as
  environment variables (or set `os.environ` from `st.secrets` before importing `database`).
- Never commit tokens. `.gitignore` already excludes `.env`, `weather*.db` and `logs/`.
