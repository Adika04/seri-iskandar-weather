# Project settings for Seri Iskandar, Perak.
# Coordinates are approximate town-centre coordinates; adjust if your lecturer
# expects a specific campus or sensor location.
LATITUDE = 4.35955
LONGITUDE = 100.97607
TIMEZONE = "Asia/Kuala_Lumpur"

API_URL = "https://api.open-meteo.com/v1/forecast"

# Local fallback database (used only when the Turso variables below are NOT set).
DATABASE_NAME = "weather.db"
LOG_FILE = "logs/collector.log"

# Hosted database (set as environment variables / GitHub Secrets, never hard-code):
#   TURSO_DATABASE_URL   e.g. libsql://weather-yourname.turso.io
#   TURSO_AUTH_TOKEN     token created with `turso db tokens create`
#   REQUIRE_TURSO=1      make the collector refuse to run without Turso
#                        (set in the GitHub workflow so a missing secret can never
#                        silently write to a throw-away local file)

# Only used by `py main.py` (continuous local mode). In the cloud, the cadence is
# set by the cron line in .github/workflows/collect.yml.
COLLECTION_INTERVAL_SECONDS = 15 * 60
FORECAST_DAYS = 2

# Ask the API for yesterday's hourly values too. If a scheduled run is skipped,
# the next run back-fills the missing hours into weather_observations.
PAST_DAYS = 1

REQUEST_TIMEOUT_SECONDS = 20
MAX_RETRIES = 3
