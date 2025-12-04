#!/usr/bin/env python3
"""
Open-Meteo historical backfill (one-off).

This script fetches historical weather data from Open-Meteo's archive API
for a specified date range and updates Airtable using a *separate*
backfill-specific record-prep function.

It does NOT modify or depend on OpenMeteoFetcher.prepare_records,
and it does NOT change your existing 6-hour Open-Meteo updater.
"""

import sys
import os
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any

import requests

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

# Network behavior for backfill (override via env if needed)
BACKFILL_TIMEOUT = float(os.getenv("OM_BACKFILL_TIMEOUT", "60"))  # seconds
BACKFILL_RETRY_DELAY = float(os.getenv("OM_BACKFILL_RETRY_DELAY_SECONDS", "10"))


def parse_date(env_var: str, default: str) -> datetime:
    """Parse YYYY-MM-DD from environment env_var, or use default."""
    value = os.getenv(env_var, default)
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(
            f"Invalid date for {env_var}={value!r}, expected YYYY-MM-DD"
        ) from e


def _daily_average(
    hourly_data: Dict[str, List[Any]],
    variable: str,
    hourly_times: List[str],
    target_date: str,
):
    """Daily average of an hourly variable for a given date."""
    try:
        variable_data = hourly_data.get(variable, [])
        if not variable_data or not hourly_times:
            return None

        total = 0.0
        count = 0
        for i, time_str in enumerate(hourly_times):
            if i < len(variable_data) and time_str.startswith(target_date):
                value = variable_data[i]
                if value is not None:
                    total += float(value)
                    count += 1

        return (total / count) if count > 0 else None
    except Exception:
        return None


def _daily_sum(
    hourly_data: Dict[str, List[Any]],
    variable: str,
    hourly_times: List[str],
    target_date: str,
):
    """Daily sum of an hourly variable for a given date."""
    try:
        variable_data = hourly_data.get(variable, [])
        if not variable_data or not hourly_times:
            return None

        total = 0.0
        found = False
        for i, time_str in enumerate(hourly_times):
            if i < len(variable_data) and time_str.startswith(target_date):
                value = variable_data[i]
                if value is not None:
                    total += float(value)
                    found = True

        return total if found else None
    except Exception:
        return None


def prepare_backfill_records(data: Dict) -> List[Dict]:
    """
    Prepare Airtable-ready records for historical backfill only.

    This does NOT touch or reuse OpenMeteoFetcher.prepare_records, so your
    existing behavior for the 6-hour job stays exactly as-is.
    """
    records: List[Dict] = []

    daily_data = data.get("daily", {})
    hourly_data = data.get("hourly", {})
    daily_times = daily_data.get("time", [])
    hourly_times = hourly_data.get("time", [])

    if not daily_times:
        logger.warning(
            "No daily data available from Open-Meteo archive",
            extra={"context": "OpenMeteo Backfill Prep"}
        )
        return records

    # Elevation is static for this location (549m), but we also read from API
    elevation = data.get("elevation", 549)

    # "When OM data was fetched" – using current UTC time for the backfill run
    data_timestamp = datetime.utcnow().isoformat()

    for i, date_str in enumerate(daily_times):
        # Daily mean temperature (C) and derived F
        temps_c = daily_data.get("temperature_2m_mean", [])
        temp_c = temps_c[i] if i < len(temps_c) else None
        temp_f = (temp_c * 9.0 / 5.0 + 32.0) if temp_c is not None else None

        # Daily averages from hourly data
        daily_humidity = _daily_average(
            hourly_data, "relative_humidity_2m", hourly_times, date_str
        )
        daily_pressure = _daily_average(
            hourly_data, "surface_pressure", hourly_times, date_str
        )
        daily_snow_depth = _daily_average(
            hourly_data, "snow_depth", hourly_times, date_str
        )
        daily_wind_speed = _daily_average(
            hourly_data, "wind_speed_10m", hourly_times, date_str
        )

        # Daily sums from hourly data
        daily_snowfall = _daily_sum(
            hourly_data, "snowfall", hourly_times, date_str
        )

        # Daily precipitation from daily data
        precip_list = daily_data.get("precipitation_sum", [])
        daily_precip = precip_list[i] if i < len(precip_list) else None

        # Weather code from daily data
        wc_list = daily_data.get("weather_code", [])
        daily_weather_code = wc_list[i] if i < len(wc_list) else None

        # Wind speed mph (km/h → mph)
        wind_speed_mph = None
        if daily_wind_speed is not None:
            wind_speed_mph = float(daily_wind_speed) * 0.621371

        om_fields = {
            # This "datetime" key is what AirtableAPI uses to match existing records
            "datetime": date_str,
            "om_temp": temp_c,
            "om_temp_f": temp_f,
            "om_humidity": daily_humidity,
            "om_pressure": daily_pressure,
            "om_wind_speed": daily_wind_speed,
            "om_wind_speed_mph": wind_speed_mph,
            "om_elevation": elevation,
            "om_precipitation": daily_precip,
            "om_data_timestamp": data_timestamp,
            "om_weather_code": daily_weather_code,
            "om_snowfall": daily_snowfall,
            "om_snow_depth": daily_snow_depth,
            # intentionally NOT setting om_snowfall_6h in backfill
        }

        cleaned: Dict[str, Any] = {}
        for k, v in om_fields.items():
            if v is None:
                cleaned[k] = None
                continue

            try:
                if k in [
                    "om_temp", "om_temp_f", "om_humidity", "om_pressure",
                    "om_wind_speed", "om_wind_speed_mph"
                ]:
                    cleaned[k] = round(float(v), 1)
                elif k in ["om_precipitation", "om_snowfall"]:
                    cleaned[k] = round(float(v), 2)
                elif k in ["om_elevation", "om_weather_code"]:
                    cleaned[k] = int(v)
                else:
                    cleaned[k] = v
            except Exception:
                cleaned[k] = v

        records.append(cleaned)

    logger.info(
        f"Prepared {len(records)} Open-Meteo backfill records",
        extra={"context": "OpenMeteo Backfill Prep"}
    )
    return records


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

    # Only using this to get lat/lon; not touching its prepare_records
    om_fetcher = OpenMeteoFetcher()
    airtable = AirtableAPI()

    current_start = start_date

    while current_start <= end_date:
        current_end = min(current_start + timedelta(days=chunk_days - 1), end_date)

        logger.info(
            f"Fetching historical data for {current_start.date()} to {current_end.date()}",
            extra={"context": "OM Archive Fetch"}
        )

        # Infinite retry loop for this chunk: never skip
        params = {
            "latitude": om_fetcher.lat,
            "longitude": om_fetcher.lon,
            "hourly": (
                "temperature_2m,relative_humidity_2m,precipitation,"
                "snowfall,snow_depth,weather_code,surface_pressure,wind_speed_10m"
            ),
            "daily": (
                "temperature_2m_max,temperature_2m_min,temperature_2m_mean,"
                "precipitation_sum,weather_code,wind_speed_10m_max"
            ),
            "timezone": "America/New_York",
            "start_date": current_start.strftime("%Y-%m-%d"),
            "end_date": current_end.strftime("%Y-%m-%d"),
        }

        while True:
            try:
                logger.info(
                    f"Archive API request for {params['start_date']} → {params['end_date']} "
                    f"(timeout={BACKFILL_TIMEOUT}s)",
                    extra={"context": "OM Archive Fetch"}
                )
                response = requests.get(
                    "https://archive-api.open-meteo.com/v1/archive",
                    params=params,
                    timeout=BACKFILL_TIMEOUT,
                )
                response.raise_for_status()
                raw = response.json()

                # Basic sanity: ensure we got daily data
                daily = raw.get("daily", {})
                if not daily.get("time"):
                    logger.warning(
                        "Archive API returned empty/invalid daily data; "
                        f"retrying in {BACKFILL_RETRY_DELAY}s",
                        extra={"context": "OM Archive Fetch Retry"}
                    )
                    time.sleep(BACKFILL_RETRY_DELAY)
                    continue

                break  # success, exit retry loop

            except requests.RequestException as e:
                logger.warning(
                    f"Archive fetch failed for {params['start_date']} → {params['end_date']}: {e}; "
                    f"retrying in {BACKFILL_RETRY_DELAY}s",
                    extra={"context": "OM Archive Fetch Retry"}
                )
                time.sleep(BACKFILL_RETRY_DELAY)

        try:
            records = prepare_backfill_records(raw)
        except Exception as e:
            logger.error(
                f"Failed to prepare backfill records: {e}",
                extra={"context": "Backfill Prep Error"}
            )
            return False

        if not records:
            logger.warning(
                "No records prepared; skipping Airtable write for this range",
                extra={"context": "Backfill Prep Empty"}
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
