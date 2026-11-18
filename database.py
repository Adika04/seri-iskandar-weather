"""Storage layer.

Uses a local SQLite file by default. When TURSO_DATABASE_URL and TURSO_AUTH_TOKEN
are set, the same SQL is sent to Turso (hosted SQLite) over HTTPS instead. Only the
`requests` package is needed, so nothing extra has to be installed.

Teammates building the dashboard can reuse this module:
    import database
    rows = database.query("SELECT * FROM weather_observations ORDER BY observed_at DESC LIMIT 10")
"""
import contextlib
import logging
import os
import sqlite3
import time
from pathlib import Path

import requests

from config import DATABASE_NAME

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

CURRENT_SOURCE = "Open-Meteo Forecast API current conditions"
BACKFILL_SOURCE = "Open-Meteo Forecast API hourly values (backfill)"

HTTP_TIMEOUT_SECONDS = 30
HTTP_RETRIES = 3
_sleep = time.sleep  # indirection so tests can skip the waits


# --------------------------------------------------------------------------- backend

def turso_configured():
    return bool(
        os.environ.get("TURSO_DATABASE_URL", "").strip()
        and os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    )


def backend_name():
    if turso_configured():
        return "Turso (remote) " + os.environ["TURSO_DATABASE_URL"].strip()
    return f"local SQLite file {Path(DATABASE_NAME).resolve()}"


def _check_backend_allowed():
    if os.environ.get("REQUIRE_TURSO") == "1" and not turso_configured():
        raise RuntimeError(
            "REQUIRE_TURSO=1 but TURSO_DATABASE_URL / TURSO_AUTH_TOKEN are missing. "
            "Check the repository secrets."
        )


# ------------------------------------------------------------------- local SQLite

def _run_sqlite(statements):
    results = []
    with contextlib.closing(sqlite3.connect(DATABASE_NAME)) as conn:
        with conn:  # one transaction: commit on success, rollback on error
            for sql, params in statements:
                results.append(conn.execute(sql, params).fetchall())
    return results


# ------------------------------------------------------------------ Turso over HTTP

def _pipeline_url():
    url = os.environ["TURSO_DATABASE_URL"].strip()
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    return url.rstrip("/") + "/v2/pipeline"


def _encode(value):
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": value}
    return {"type": "text", "value": str(value)}


def _decode(cell):
    kind = cell.get("type")
    if kind == "null":
        return None
    if kind == "integer":
        return int(cell["value"])
    if kind == "float":
        return float(cell["value"])
    return cell.get("value")


def _post_pipeline(body):
    headers = {"Authorization": "Bearer " + os.environ["TURSO_AUTH_TOKEN"].strip()}
    last_error = None
    for attempt in range(1, HTTP_RETRIES + 1):
        try:
            response = requests.post(
                _pipeline_url(), json=body, headers=headers,
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            if response.status_code >= 500:
                raise requests.RequestException(f"HTTP {response.status_code}")
            if response.status_code >= 400:
                # Auth / bad request: retrying will not help.
                raise RuntimeError(
                    f"Turso rejected the request (HTTP {response.status_code}): "
                    f"{response.text[:200]}"
                )
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            logging.warning("Turso request attempt %s/%s failed: %s",
                            attempt, HTTP_RETRIES, exc)
            if attempt < HTTP_RETRIES:
                _sleep(2 ** attempt)
    raise RuntimeError(f"Could not reach Turso after retries: {last_error}")


def _run_turso(statements):
    """Run all statements in ONE transaction via a single HTTPS request."""
    n = len(statements)
    steps = [{"stmt": {"sql": "BEGIN"}}]
    for i, (sql, params) in enumerate(statements):
        steps.append({
            "stmt": {"sql": sql, "args": [_encode(p) for p in params]},
            "condition": {"type": "ok", "step": i},  # only if the previous step worked
        })
    steps.append({"stmt": {"sql": "COMMIT"},
                  "condition": {"type": "ok", "step": n}})
    steps.append({"stmt": {"sql": "ROLLBACK"},
                  "condition": {"type": "not", "cond": {"type": "ok", "step": n + 1}}})

    data = _post_pipeline({"requests": [
        {"type": "batch", "batch": {"steps": steps}},
        {"type": "close"},
    ]})

    first = data["results"][0]
    if first.get("type") == "error":
        raise RuntimeError("Turso error: " + first["error"].get("message", "unknown"))
    result = first["response"]["result"]
    for err in result["step_errors"]:
        if err:
            raise RuntimeError("Turso SQL error: " + err.get("message", "unknown"))

    out = []
    for i in range(n):
        step = result["step_results"][i + 1]
        out.append([[_decode(c) for c in row] for row in step["rows"]])
    return out


# ------------------------------------------------------------------ public helpers

def run_statements(statements):
    """statements: list of (sql, params). Returns one list of rows per statement."""
    _check_backend_allowed()
    statements = [(sql, tuple(params)) for sql, params in statements]
    if turso_configured():
        return _run_turso(statements)
    return _run_sqlite(statements)


def query(sql, params=()):
    return run_statements([(sql, params)])[0]


def _schema_statements():
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    return [(part.strip(), ()) for part in text.split(";") if part.strip()]


def initialise_database():
    run_statements(_schema_statements())
    print(f"Database ready: {backend_name()}")


# --------------------------------------------------------------------- SQL / writes

_OBSERVATION_SQL = """
INSERT INTO weather_observations
(observed_at, temperature, humidity, precipitation, wind_speed, collected_at, source)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(observed_at) DO UPDATE SET
    temperature=excluded.temperature,
    humidity=excluded.humidity,
    precipitation=excluded.precipitation,
    wind_speed=excluded.wind_speed,
    collected_at=excluded.collected_at,
    source=excluded.source
"""

# Back-filled hours never overwrite a real "current" reading already stored.
_BACKFILL_SQL = """
INSERT OR IGNORE INTO weather_observations
(observed_at, temperature, humidity, precipitation, wind_speed, collected_at, source)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""

_FORECAST_SQL = """
INSERT OR IGNORE INTO weather_forecasts
(forecast_retrieved_at, forecast_for, temperature, humidity,
 precipitation, wind_speed, collected_at)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""

_RUN_SQL = """
INSERT INTO collector_runs
(run_at, status, observed_at, forecast_rows, backfill_rows, message)
VALUES (?, ?, ?, ?, ?, ?)
"""


def _obs_params(r, source):
    return (r["observed_at"], r["temperature"], r["humidity"],
            r["precipitation"], r["wind_speed"], r["collected_at"], source)


def _forecast_params(r):
    return (r["forecast_retrieved_at"], r["forecast_for"], r["temperature"],
            r["humidity"], r["precipitation"], r["wind_speed"], r["collected_at"])


def save_collection(observation, backfill_rows, forecast_rows, collected_at):
    """Save one whole collection run atomically (one transaction, one request)."""
    statements = [(_OBSERVATION_SQL, _obs_params(observation, CURRENT_SOURCE))]
    statements += [(_BACKFILL_SQL, _obs_params(r, BACKFILL_SOURCE)) for r in backfill_rows]
    statements += [(_FORECAST_SQL, _forecast_params(r)) for r in forecast_rows]
    statements.append((_RUN_SQL, (
        collected_at, "success", observation["observed_at"],
        len(forecast_rows), len(backfill_rows), None,
    )))
    run_statements(statements)


def log_failure(run_at, message):
    """Best-effort: record a failed run. Never raises (the DB may be the problem)."""
    try:
        run_statements([(_RUN_SQL, (run_at, "failure", None, None, None, str(message)[:500]))])
    except Exception:
        logging.exception("Could not record the failure in collector_runs")


# Thin wrappers kept so older code that imports these names keeps working.
def save_observation(data):
    run_statements([(_OBSERVATION_SQL, _obs_params(data, CURRENT_SOURCE))])


def save_forecasts(rows):
    run_statements([(_FORECAST_SQL, _forecast_params(r)) for r in rows])


def print_record_counts():
    results = run_statements([
        ("SELECT COUNT(*) FROM weather_observations", ()),
        ("SELECT COUNT(*) FROM weather_forecasts", ()),
        ("SELECT COUNT(*) FROM collector_runs", ()),
    ])
    obs, fc, runs = (r[0][0] for r in results)
    print(f"Database records - observations: {obs}, forecasts: {fc}, runs: {runs}")
