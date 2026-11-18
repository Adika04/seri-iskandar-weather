"""Evidence for the Phase 1 report: how complete is the collection run?

    py run_summary.py

Works against whichever database is configured (Turso if the env vars are set,
otherwise the local weather.db).
"""
from collections import Counter
from datetime import datetime, timedelta

import database

GAP_THRESHOLD_MINUTES = 30


def parse(ts):
    return datetime.fromisoformat(ts)  # "2026-11-18T14:15" style local strings


def main():
    print("Backend:", database.backend_name())

    obs = database.query(
        "SELECT observed_at, source FROM weather_observations ORDER BY observed_at"
    )
    if not obs:
        print("No observations yet.")
        return

    current = [parse(t) for t, s in obs if s == database.CURRENT_SOURCE]
    backfill = [parse(t) for t, s in obs if s == database.BACKFILL_SOURCE]
    everything = [parse(t) for t, _ in obs]

    first, last = everything[0], everything[-1]
    span = last - first
    print("\n== Observations ==")
    print(f"Rows: {len(obs)} (current readings: {len(current)}, hourly back-fill: {len(backfill)})")
    print(f"First: {first:%Y-%m-%d %H:%M}   Last: {last:%Y-%m-%d %H:%M}")
    print(f"Span: {span.total_seconds() / 3600:.1f} hours "
          f"-> 3-day requirement {'MET' if span >= timedelta(hours=72) else 'NOT yet met'}")

    hours_present = {t.replace(minute=0, second=0) for t in everything}
    expected = int(span.total_seconds() // 3600) + 1
    print(f"Hours with at least one observation: {len(hours_present)}/{expected} "
          f"({100 * len(hours_present) / expected:.1f}%)")

    print("\nCurrent readings per day:")
    for day, n in sorted(Counter(t.date() for t in current).items()):
        print(f"  {day}: {n}")

    gaps = sorted(
        ((b - a, a, b) for a, b in zip(current, current[1:])
         if b - a > timedelta(minutes=GAP_THRESHOLD_MINUTES)),
        reverse=True,
    )
    print(f"\nGaps longer than {GAP_THRESHOLD_MINUTES} min between current readings: {len(gaps)}")
    for gap, a, b in gaps[:5]:
        print(f"  {gap} between {a:%m-%d %H:%M} and {b:%m-%d %H:%M}")

    fc = database.query(
        "SELECT COUNT(*), COUNT(DISTINCT forecast_retrieved_at), "
        "MIN(forecast_for), MAX(forecast_for) FROM weather_forecasts"
    )[0]
    print("\n== Forecasts ==")
    print(f"Rows: {fc[0]}   Snapshots (runs): {fc[1]}   Target hours: {fc[2]} -> {fc[3]}")

    runs = database.query("SELECT status, COUNT(*) FROM collector_runs GROUP BY status")
    print("\n== Collector runs ==")
    for status, n in runs:
        print(f"  {status}: {n}")
    failures = database.query(
        "SELECT run_at, message FROM collector_runs WHERE status='failure' "
        "ORDER BY run_at DESC LIMIT 5"
    )
    for run_at, message in failures:
        print(f"  FAILED {run_at}: {message}")


if __name__ == "__main__":
    main()
