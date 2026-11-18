import argparse
import logging
import time
from pathlib import Path

from config import COLLECTION_INTERVAL_SECONDS, LOG_FILE
from database import initialise_database, print_record_counts, log_failure
from collector import collect_once, local_now_iso


def setup_logging():
    Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),  # also visible in GitHub Actions run logs
        ],
    )


def run_cycle():
    """One collection. On failure: log it, record it in the database, re-raise."""
    try:
        collect_once()
        print_record_counts()
    except Exception as exc:
        logging.exception("Collection failed")
        log_failure(local_now_iso(), repr(exc))
        raise


def main():
    parser = argparse.ArgumentParser(description="Open-Meteo weather data collector")
    parser.add_argument(
        "--once", action="store_true",
        help="Collect one batch and exit (used by the GitHub Actions workflow)."
    )
    args = parser.parse_args()

    setup_logging()
    initialise_database()

    if args.once:
        run_cycle()  # a failure exits non-zero, so the workflow run shows red
        return

    print("Continuous collection started. Press Ctrl+C to stop.")
    print(f"Collection interval: {COLLECTION_INTERVAL_SECONDS} seconds")
    try:
        while True:
            started = time.monotonic()
            try:
                run_cycle()
            except Exception:
                print("Collection failed. Details are in logs/collector.log")

            elapsed = time.monotonic() - started
            time.sleep(max(0, COLLECTION_INTERVAL_SECONDS - elapsed))
    except KeyboardInterrupt:
        print("\nCollector stopped by user.")


if __name__ == "__main__":
    main()
