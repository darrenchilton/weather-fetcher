#!/usr/bin/env python3
"""
Open-Meteo historical backfill (one-off).

This script fetches historical weather data from Open-Meteo's archive API
for a specified date range and updates Airtable using your existing
AirtableAPI + prepare_records pipeline.

It does NOT modify or interfere with your 6-hour forecast updater.
"""

import sys
import os
import logging
import time
from datetime import datetime, timedelta

from openmeteo_fetcher import OpenMeteoFetcher
from weather_fetcher import AirtableAPI


# Log to its own file so it never mixes with the 6-hour updater logs
log_path = "openmeteo_backfill.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s - %(context)s",
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("openmeteo_backfill")


def parse_date(env_var: str, default: str) -> datetime:
    """Parse YYYY-MM-DD from environment env_var."""
    value = os.getenv(env_var, default)
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(
            f"Invalid date for {env_var}={value!r}, expected YYYY-MM-DD"
        ) from e


def main() -> bool:
    """
    Run a historical backfill from Open-Meteo archive API.

    Defaults (override via GitHub env or shell env):
      OM_BACKFILL_START = 2021-01-01
      OM_BACKFILL_END   = 2025-06-21  (day before your first OM record)
      OM_BACKFILL_CHUNK_DAYS = 30
      OM_BACKFILL_SLEEP_SECONDS = 5
    """

    start_date = parse_date("OM_BACKFILL_START", "2021-01-01")
    end_date = parse_date("OM_BACKFILL_END", "2025-06-21")

    if end_date < start_date:
        logger.error(
            "End date is before start date; aborting",
            extra={"context": "Backfill Config"}
        )
        return False

    chunk_days = int(os.getenv("OM_BACKFILL_CHUNK_DAYS", "30"))
    sleep_seconds = float(os.getenv("OM_BACKFILL_SLEEP_SECONDS", "5"))

    logger.info(
        f"Starting Open-Meteo historical backfill from "
        f"{start_date.date()} to {end_date.date()} using {chunk_days}-day chunks",
        extra={"context": "Backfill Start"}
    )

    # Reuse your existing class but point it at the archive endpoint
    om_fetcher = OpenMeteoFetcher()
    om_fetcher.base_url = "https://archive-api.open-meteo.com/v1/archive"

    airtable = AirtableAPI()

    current_start = start_date

    while current_start <= end_date:
        current_end = min(current_start + timedelta(days=chunk_days - 1), end_date)

        logger.info(
            f"Fetching historical data for {current_start.date()} to {current_end.date()}",
            extra={"context": "OM Archive Fetch"}
        )

        try:
            raw = om_fetcher.fetch_weather_data(
                start_time=current_start,
                end_time=current_end,
            )
        except Exception as e:
            logger.error(
                f"Failed to fetch archive data: {e}",
                extra={"context": "Archive Fetch Error"}
            )
            return False

        if not raw:
            logger.warning(
                "Empty response; skipping",
                extra={"context": "Archive Fetch Empty"}
            )
            current_start = current_end + timedelta(days=1)
            time.sleep(sleep_seconds)
            continue

        try:
            records = om_fetcher.prepare_records(raw)
        except Exception as e:
            logger.error(
                f"Failed to prepare records: {e}",
                extra={"context": "Record Prep Error"}
            )
            return False

        if not records:
            logger.warning(
                "No records prepared; skipping Airtable write",
                extra={"context": "Prep Empty"}
            )
            current_start = current_end + timedelta(days=1)
            time.sleep(sleep_seconds)
            continue

        logger.info(
            f"Updating Airtable with {len(records)} records "
            f"for {current_start.date()} → {current_end.date()}",
            extra={"context": "Airtable Write"}
        )

        try:
            success = airtable.update_records_with_openmeteo(records)
        except Exception as e:
            logger.error(
                f"Airtable update failed: {e}",
                extra={"context": "Airtable Update Error"}
            )
            return False

        if not success:
            logger.warning(
                "Airtable update returned falsy status",
                extra={"context": "Airtable Update Warning"}
            )

        current_start = current_end + timedelta(days=1)
        time.sleep(sleep_seconds)

    logger.info(
        "Historical backfill completed successfully",
        extra={"context": "Backfill Complete"}
    )
    return True


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
