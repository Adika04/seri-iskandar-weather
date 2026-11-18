from datetime import datetime
from zoneinfo import ZoneInfo
import logging
import time
import requests

from config import (
    API_URL, LATITUDE, LONGITUDE, TIMEZONE, FORECAST_DAYS, PAST_DAYS,
    REQUEST_TIMEOUT_SECONDS, MAX_RETRIES
)
from database import save_collection

LOCAL_TZ = ZoneInfo(TIMEZONE)
_sleep = time.sleep  # indirection so tests can skip the waits

VARIABLES = ("temperature_2m", "relative_humidity_2m", "precipitation", "wind_speed_10m")


def local_now_iso():
    return datetime.now(LOCAL_TZ).isoformat(timespec="seconds")


def request_weather_data():
    params = {
        "latitude": LATITUDE,
        "longitude": LONGITUDE,
        "timezone": TIMEZONE,
        "temperature_unit": "celsius",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "current": ",".join(VARIABLES),
        "hourly": ",".join(VARIABLES),
        "forecast_days": FORECAST_DAYS,
        "past_days": PAST_DAYS,
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(
                API_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("error"):
                raise RuntimeError(payload.get("reason", "API returned an error"))
            return payload
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            logging.warning("API attempt %s/%s failed: %s", attempt, MAX_RETRIES, exc)
            if attempt < MAX_RETRIES:
                _sleep(2 ** attempt)

    raise RuntimeError(f"Could not retrieve weather data after retries: {last_error}")


def build_rows(payload, collected_at):
    """Split an API payload into: the current observation, back-filled past hours,
    and genuine forecasts (hours strictly after the current reading).

    Hours up to "now" are not forecasts any more, so they go to weather_observations
    (marked as back-fill in `source`). This keeps every forecast row truly ahead of
    its retrieval time, which makes forecast-horizon analysis well defined.
    Times are local strings like 2026-11-18T14:15, so plain string comparison works.
    """
    current = payload.get("current") or {}
    if not current.get("time"):
        raise ValueError("API response did not contain current weather data.")
    current_time = current["time"]

    observation = {
        "observed_at": current_time,
        "temperature": current.get("temperature_2m"),
        "humidity": current.get("relative_humidity_2m"),
        "precipitation": current.get("precipitation"),
        "wind_speed": current.get("wind_speed_10m"),
        "collected_at": collected_at,
    }

    hourly = payload.get("hourly") or {}

    def value_or_none(key, i):
        values = hourly.get(key, [])
        return values[i] if i < len(values) else None

    backfill_rows, forecast_rows = [], []
    for i, hour in enumerate(hourly.get("time", [])):
        values = {
            "temperature": value_or_none("temperature_2m", i),
            "humidity": value_or_none("relative_humidity_2m", i),
            "precipitation": value_or_none("precipitation", i),
            "wind_speed": value_or_none("wind_speed_10m", i),
        }
        if hour <= current_time:
            if all(v is None for v in values.values()):
                continue
            backfill_rows.append({"observed_at": hour, **values,
                                  "collected_at": collected_at})
        else:
            forecast_rows.append({
                # When our collector retrieved the forecast, not necessarily the
                # weather model's internal initialisation time.
                "forecast_retrieved_at": collected_at,
                "forecast_for": hour,
                **values,
                "collected_at": collected_at,
            })
    return observation, backfill_rows, forecast_rows


def collect_once():
    payload = request_weather_data()
    collected_at = local_now_iso()
    observation, backfill_rows, forecast_rows = build_rows(payload, collected_at)

    save_collection(observation, backfill_rows, forecast_rows, collected_at)

    logging.info(
        "Collection successful. Observation time=%s; forecast rows=%s; backfill rows=%s",
        observation["observed_at"], len(forecast_rows), len(backfill_rows)
    )
    print(
        f"Saved observation for {observation['observed_at']}, "
        f"{len(forecast_rows)} forecast rows, "
        f"{len(backfill_rows)} hourly back-fill rows."
    )
    return {"observed_at": observation["observed_at"],
            "forecast_rows": len(forecast_rows),
            "backfill_rows": len(backfill_rows)}
