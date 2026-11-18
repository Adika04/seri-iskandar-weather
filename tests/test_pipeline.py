import contextlib
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

import requests  # noqa: E402
import collector  # noqa: E402
import database  # noqa: E402
import run_summary  # noqa: E402
from fake_turso import FakeTurso, TOKEN  # noqa: E402


def canned_payload(current_time="2026-11-18T14:15", temp_offset=0.0):
    start = datetime(2026, 11, 17, 0, 0)
    hours = [(start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(72)]
    return {
        "current": {"time": current_time, "temperature_2m": 30.1 + temp_offset,
                    "relative_humidity_2m": 70, "precipitation": 0.0,
                    "wind_speed_10m": 5.5},
        "hourly": {
            "time": hours,
            "temperature_2m": [25.0 + i * 0.1 for i in range(72)],
            "relative_humidity_2m": [80] * 72,
            "precipitation": [0.0] * 72,
            "wind_speed_10m": [4.0] * 72,
        },
    }


def clean_env():
    for key in ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "REQUIRE_TURSO"):
        os.environ.pop(key, None)


class CollectionFlow:
    """Shared assertions, run against both backends."""

    def run_once(self, current_time, collected_at):
        with mock.patch.object(collector, "request_weather_data",
                               return_value=canned_payload(current_time)), \
             mock.patch.object(collector, "local_now_iso", return_value=collected_at), \
             contextlib.redirect_stdout(io.StringIO()):
            return collector.collect_once()

    def test_split_and_idempotency(self):
        database.initialise_database()

        summary = self.run_once("2026-11-18T14:15", "2026-11-18T14:16:00+08:00")
        self.assertEqual(summary["backfill_rows"], 39)   # 17th 00:00 .. 18th 14:00
        self.assertEqual(summary["forecast_rows"], 33)   # 18th 15:00 .. 19th 23:00

        count = lambda t: database.query(f"SELECT COUNT(*) FROM {t}")[0][0]  # noqa: E731
        self.assertEqual(count("weather_observations"), 40)
        self.assertEqual(count("weather_forecasts"), 33)

        # Every stored forecast is strictly ahead of the reading it was retrieved with.
        self.assertEqual(database.query(
            "SELECT COUNT(*) FROM weather_forecasts WHERE forecast_for <= '2026-11-18T14:15'"
        )[0][0], 0)

        # Sources are labelled.
        sources = dict(database.query(
            "SELECT source, COUNT(*) FROM weather_observations GROUP BY source"))
        self.assertEqual(sources[database.CURRENT_SOURCE], 1)
        self.assertEqual(sources[database.BACKFILL_SOURCE], 39)

        # Next run 15 minutes later: 1 new observation, a new forecast snapshot.
        self.run_once("2026-11-18T14:30", "2026-11-18T14:31:00+08:00")
        self.assertEqual(count("weather_observations"), 41)   # backfill rows ignored
        self.assertEqual(count("weather_forecasts"), 33 + 33)
        self.assertEqual(count("collector_runs"), 2)

        # Re-running the identical collection must not duplicate anything.
        self.run_once("2026-11-18T14:30", "2026-11-18T14:31:00+08:00")
        self.assertEqual(count("weather_observations"), 41)
        self.assertEqual(count("weather_forecasts"), 66)

    def test_backfill_does_not_overwrite_real_reading(self):
        database.initialise_database()
        # A real current reading exactly on the hour...
        self.run_once("2026-11-18T14:00", "2026-11-18T14:01:00+08:00")
        real = database.query(
            "SELECT temperature, source FROM weather_observations "
            "WHERE observed_at='2026-11-18T14:00'")[0]
        self.assertEqual(real[1], database.CURRENT_SOURCE)
        # ...is not replaced by a later run's hourly back-fill of that same hour.
        self.run_once("2026-11-18T14:15", "2026-11-18T14:16:00+08:00")
        again = database.query(
            "SELECT temperature, source FROM weather_observations "
            "WHERE observed_at='2026-11-18T14:00'")[0]
        self.assertEqual(real, again)

    def test_failure_is_recorded(self):
        database.initialise_database()
        database.log_failure("2026-11-18T14:20:00+08:00", "boom")
        row = database.query("SELECT status, message FROM collector_runs")[0]
        self.assertEqual(tuple(row), ("failure", "boom"))

    def test_summary_runs(self):
        database.initialise_database()
        self.run_once("2026-11-18T14:15", "2026-11-18T14:16:00+08:00")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            run_summary.main()
        out = buf.getvalue()
        self.assertIn("current readings: 1, hourly back-fill: 39", out)
        self.assertIn("NOT yet met", out)

    def test_atomic_transaction(self):
        database.initialise_database()
        with self.assertRaises(Exception):
            database.run_statements([
                ("INSERT INTO collector_runs (run_at, status) VALUES ('x', 'success')", ()),
                ("INSERT INTO no_such_table VALUES (1)", ()),
            ])
        self.assertEqual(database.query("SELECT COUNT(*) FROM collector_runs")[0][0], 0)


class LocalSqliteTests(CollectionFlow, unittest.TestCase):
    def setUp(self):
        clean_env()
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(database, "DATABASE_NAME",
                                    str(Path(self.tmp.name) / "weather.db"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)


class TursoHttpTests(CollectionFlow, unittest.TestCase):
    def setUp(self):
        self.fake = FakeTurso()
        self.addCleanup(self.fake.stop)
        os.environ["TURSO_DATABASE_URL"] = self.fake.url
        os.environ["TURSO_AUTH_TOKEN"] = TOKEN
        self.addCleanup(clean_env)
        patcher = mock.patch.object(database, "_sleep", lambda s: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_one_request_per_collection(self):
        database.initialise_database()
        before = self.fake.requests_seen
        self.run_once("2026-11-18T14:15", "2026-11-18T14:16:00+08:00")
        self.assertEqual(self.fake.requests_seen - before, 1)

    def test_retries_then_succeeds(self):
        database.initialise_database()
        self.fake.fail_next = 2
        before = self.fake.requests_seen
        self.run_once("2026-11-18T14:15", "2026-11-18T14:16:00+08:00")
        self.assertEqual(self.fake.requests_seen - before, 3)
        self.assertEqual(database.query("SELECT COUNT(*) FROM collector_runs")[0][0], 1)

    def test_gives_up_after_retries(self):
        database.initialise_database()
        self.fake.fail_next = 10
        with self.assertRaises(RuntimeError):
            database.query("SELECT 1")

    def test_bad_token_not_retried(self):
        os.environ["TURSO_AUTH_TOKEN"] = "wrong"
        before = self.fake.requests_seen
        with self.assertRaises(RuntimeError) as ctx:
            database.query("SELECT 1")
        self.assertEqual(self.fake.requests_seen - before, 1)
        self.assertNotIn("wrong", str(ctx.exception))

    def test_libsql_scheme_is_converted(self):
        os.environ["TURSO_DATABASE_URL"] = "libsql://my-db-me.turso.io"
        self.assertEqual(database._pipeline_url(), "https://my-db-me.turso.io/v2/pipeline")


class SafetyTests(unittest.TestCase):
    def setUp(self):
        clean_env()
        self.addCleanup(clean_env)

    def test_require_turso_blocks_local_fallback(self):
        os.environ["REQUIRE_TURSO"] = "1"
        with self.assertRaises(RuntimeError):
            database.query("SELECT 1")


class ApiRetryTests(unittest.TestCase):
    def test_api_retries_then_succeeds(self):
        calls = {"n": 0}
        good = mock.Mock()
        good.raise_for_status.return_value = None
        good.json.return_value = canned_payload()

        def fake_get(*a, **k):
            calls["n"] += 1
            if calls["n"] < 3:
                raise requests.ConnectionError("network down")
            return good

        with mock.patch.object(collector.requests, "get", side_effect=fake_get), \
             mock.patch.object(collector, "_sleep", lambda s: None):
            payload = collector.request_weather_data()
        self.assertEqual(calls["n"], 3)
        self.assertIn("current", payload)

    def test_api_gives_up(self):
        with mock.patch.object(collector.requests, "get",
                               side_effect=requests.Timeout("slow")), \
             mock.patch.object(collector, "_sleep", lambda s: None):
            with self.assertRaises(RuntimeError):
                collector.request_weather_data()


if __name__ == "__main__":
    unittest.main()
