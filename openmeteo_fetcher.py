"""
CHANGELOG
2025-12-04: Added Open-Meteo snowfall + snow depth support.
- Requests hourly snowfall and snow_depth.
- Computes historical daily snowfall total (om_snowfall) by summing hourly snowfall per date.
- Computes rolling last-6-hours snowfall for today only (om_snowfall_6h).
- Computes daily average snow depth (om_snow_depth).
- Added fetch_weather_data() alias for backwards compatibility.
"""

import requests
from datetime import datetime, timedelta
import logging
import os
from typing import Dict, List
import time
...

logger = logging.getLogger("openmeteo_fetcher")
logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(context)s - %(message)s'
)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


class OpenMeteoFetcher:
    def __init__(self, latitude: float = 42.28, longitude: float = -74.21):
        """
        Initialize the Open-Meteo fetcher.

        Default location is Hensonville, NY (42.28, -74.21).
        """
        self.base_url = "https://api.open-meteo.com/v1/forecast"
        self.lat = latitude
        self.lon = longitude

    def fetch_weather_data(
        self,
        latitude: float = None,
        longitude: float = None,
        start_time: datetime = None,
        end_time: datetime = None
    ) -> Dict:
        """
        Backwards-compatible alias for get_weather_data, used by update_openmeteo.py.
        """
        return self.get_weather_data(
            latitude=latitude,
            longitude=longitude,
            start_time=start_time,
            end_time=end_time,
        )

    def get_weather_data(
        self,
        latitude: float = None,
        longitude: float = None,
        start_time: datetime = None,
        end_time: datetime = None
    ) -> Dict:
        """
        Fetch weather data from Open-Meteo API.
        """
        lat = latitude if latitude is not None else self.lat
        lon = longitude if longitude is not None else self.lon

        params = {
            'latitude': lat,
            'longitude': lon,
            'hourly': (
                'temperature_2m,relative_humidity_2m,precipitation,'
                'snowfall,snow_depth,weather_code,surface_pressure,wind_speed_10m'
            ),
            'daily': (
                'temperature_2m_max,temperature_2m_min,temperature_2m_mean,'
                'precipitation_sum,weather_code,wind_speed_10m_max'
            ),
            'timezone': 'America/New_York',
            'forecast_days': 7
        }

        # Handle optional time range if provided
        if start_time is not None:
            params['start_date'] = start_time.strftime('%Y-%m-%d')
        if end_time is not None:
            params['end_date'] = end_time.strftime('%Y-%m-%d')

        try:
            logger.info(
                f"Fetching Open-Meteo data for coordinates ({lat}, {lon})",
                extra={'context': 'OpenMeteo API Request'}
            )
            response = requests.get(self.base_url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if not data:
                logger.error(
                    "Empty response from Open-Meteo API",
                    extra={'context': 'OpenMeteo API Error'}
                )
                return {}

            logger.info(
                "Successfully fetched data from Open-Meteo",
                extra={'context': 'OpenMeteo API Success'}
            )
            return data

        except requests.RequestException as e:
            logger.error(
                f"Error fetching Open-Meteo data: {e}",
                extra={'context': 'OpenMeteo API Error'}
            )
            raise

    def prepare_records(self, data: Dict) -> List[Dict]:
        """
        Prepare records for Airtable update from Open-Meteo data.
        """
        try:
            records: List[Dict] = []

            daily_data = data.get('daily', {})
            hourly_data = data.get('hourly', {})
            daily_times = daily_data.get('time', [])
            hourly_times = hourly_data.get('time', [])

            if not daily_times:
                logger.warning(
                    "No daily data available from Open-Meteo",
                    extra={'context': 'OpenMeteo Data Preparation'}
                )
                return records

            today_str = datetime.now().strftime('%Y-%m-%d')

            for i, date_str in enumerate(daily_times):
                # Get temperature from daily data (more accurate)
                temp_c = daily_data.get('temperature_2m_mean', [... if i < len(daily_data.get('temperature_2m_mean', [])) else None
                temp_f = (temp_c * 9 / 5) + 32 if temp_c is not None else None

                # Calculate daily averages/sums from hourly data
                daily_humidity = self._calculate_daily_average(
                    hourly_data, 'relative_humidity_2m', hourly_times, date_str
                )
                daily_pressure = self._calculate_daily_average(
                    hourly_data, 'surface_pressure', hourly_times, date_str
                )
                daily_wind_speed = self._calculate_daily_average(
                    hourly_data, 'wind_speed_10m', hourly_times, date_str
                )

                daily_precip = self._calculate_daily_sum(
                    hourly_data, 'precipitation', hourly_times, date_str
                )

                # New snowfall & snow depth metrics
                daily_snowfall = self._calculate_daily_sum(
                    hourly_data, 'snowfall', hourly_times, date_str
                )
                daily_snow_depth = self._calculate_daily_average(
                    hourly_data, 'snow_depth', hourly_times, date_str
                )

                # Rolling last-6-hours snowfall for today only
                snowfall_6h = None
                if date_str == today_str:
                    snowfall_6h = self._calculate_rolling_snowfall_6h(
                        hourly_data, hourly_times
                    )

                record = {
                    'date': date_str,
                    'om_temp': temp_f,
                    'om_humidity': daily_humidity,
                    'om_pressure': daily_pressure,
                    'om_wind': daily_wind_speed,
                    'om_precip': daily_precip,
                    'om_snowfall': daily_snowfall,
                    'om_snowfall_6h': snowfall_6h,
                    'om_snow_depth': daily_snow_depth,
                }

                records.append(record)

            logger.info(
                f"Prepared {len(records)} Open-Meteo records",
                extra={'context': 'OpenMeteo Data Preparation'}
            )
            return records

        except Exception as e:
            logger.error(
                f"Error preparing Open-Meteo records: {e}",
                extra={'context': 'OpenMeteo Data Preparation Error'}
            )
            raise

    def prepare_daily_records(self, data: Dict) -> List[Dict]:
        """Backwards compatibility alias for prepare_records."""
        return self.prepare_records(data)

    def _calculate_daily_sum(
        self,
        hourly_data: Dict,
        variable: str,
        hourly_times: List[str],
        target_date: str
    ):
        """
        Calculate daily sum from hourly data for a specific variable and date.
        """
        try:
            variable_data = hourly_data.get(variable, [])
            if not variable_data or not hourly_times:
                return None

            total = 0.0
            found = False

            for value, time_str in zip(variable_data, hourly_times):
                if not time_str.startswith(target_date):
                    continue
                if value is None:
                    continue
                found = True
                total += value

            return total if found else None
        except Exception as e:
            logger.error(
                f"Error calculating daily sum for {variable}: {e}",
                extra={'context': 'OpenMeteo Data Calculation Error'}
            )
            return None

    def _calculate_daily_average(
        self,
        hourly_data: Dict,
        variable: str,
        hourly_times: List[str],
        target_date: str
    ):
        """
        Calculate daily average from hourly data for a specific variable and date.
        """
        try:
            variable_data = hourly_data.get(variable, [])
            if not variable_data or not hourly_times:
                return None

            values = []
            for value, time_str in zip(variable_data, hourly_times):
                if not time_str.startswith(target_date):
                    continue
                if value is None:
                    continue
                values.append(value)

            if not values:
                return None

            return sum(values) / len(values)
        except Exception as e:
            logger.error(
                f"Error calculating daily average for {variable}: {e}",
                extra={'context': 'OpenMeteo Data Calculation Error'}
            )
            return None

    def _calculate_rolling_snowfall_6h(
        self,
        hourly_data: Dict,
        hourly_times: List[str]
    ):
        """
        Calculate rolling last-6-hours snowfall (inches) for "now".
        Uses the most recent 6 hourly entries in the hourly snowfall series.
        """
        try:
            snowfall_data = hourly_data.get('snowfall', [])
            if not snowfall_data or not hourly_times:
                return None

            # Take the last 6 values that are not None
            non_null_values = [v for v in snowfall_data if v is not None]
            if not non_null_values:
                return None

            last_6 = non_null_values[-6:]
            return sum(last_6)
        except Exception as e:
            logger.error(
                f"Error calculating rolling 6h snowfall: {e}",
                extra={'context': 'OpenMeteo Data Calculation Error'}
            )
            return None


def test_openmeteo_fetch():
    """
    Simple test function to verify that Open-Meteo fetch
    and record preparation are working.
    """
    try:
        fetcher = OpenMeteoFetcher()
        data = fetcher.get_weather_data()

        if not data:
            print("❌ No data received from Open-Meteo API")
            return False

        print("✅ Successfully fetched data from Open-Meteo API")

        records = fetcher.prepare_records(data)
        print(f"Prepared {len(records)} records")

        if records:
            print("Sample record:")
            print(records[0])

        return True
    except Exception as e:
        print(f"❌ Error testing Open-Meteo fetch: {e}")
        return False


if __name__ == "__main__":
    # Test the Open-Meteo fetcher
    test_openmeteo_fetch()
