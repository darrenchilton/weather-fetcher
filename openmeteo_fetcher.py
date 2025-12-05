"""
CHANGELOG
2025-12-04: Added Open-Meteo snowfall + snow depth support.
- Requests hourly snowfall and snow_depth.
- Requests daily snowfall_sum (forecast fallback).
- Computes daily snowfall total (om_snowfall) from hourly snowfall per date, fallback to daily snowfall_sum.
- Computes rolling last-6-hours snowfall for today only (om_snowfall_6h).
- Computes daily average snow depth (om_snow_depth).
- Added fetch_weather_data() alias for backwards compatibility.
"""

import requests
from datetime import datetime, timedelta
import logging
from typing import Dict, List

# Configure logger
logger = logging.getLogger("openmeteo_fetcher")
logger.setLevel(logging.INFO)

if not logger.handlers:
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
        self.elevation = 549  # meters

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
        Fetch weather data from Open-Meteo API (forecast endpoint).
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
                'precipitation_sum,snowfall_sum,weather_code,wind_speed_10m_max'
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

            # pull daily arrays once for speed/clarity
            temps_c = daily_data.get('temperature_2m_mean', [])
            precip_sums = daily_data.get('precipitation_sum', [])
            weather_codes = daily_data.get('weather_code', [])
            wind_max = daily_data.get('wind_speed_10m_max', [])
            snowfall_sums = daily_data.get('snowfall_sum', [])

            for i, date_str in enumerate(daily_times):
                # Daily temp
                temp_c = temps_c[i] if i < len(temps_c) else None
                temp_f = (temp_c * 9 / 5) + 32 if temp_c is not None else None

                # Other daily values direct from daily block
                daily_precip = precip_sums[i] if i < len(precip_sums) else None
                daily_code = weather_codes[i] if i < len(weather_codes) else None
                daily_wind = wind_max[i] if i < len(wind_max) else None

                # Daily averages/sums from hourly
                daily_humidity = self._calculate_daily_average(
                    hourly_data, 'relative_humidity_2m', hourly_times, date_str
                )
                daily_pressure = self._calculate_daily_average(
                    hourly_data, 'surface_pressure', hourly_times, date_str
                )

                # --- snow fields ---
                daily_snow_depth = self._calculate_daily_average(
                    hourly_data, 'snow_depth', hourly_times, date_str
                )

                daily_snowfall = self._calculate_daily_sum(
                    hourly_data, 'snowfall', hourly_times, date_str
                )
                if daily_snowfall is None:
                    # Forecast fallback if hourly snowfall missing
                    daily_snowfall = snowfall_sums[i] if i < len(snowfall_sums) else None

                # Rolling last-6-hours snowfall, only on today's record
                snow_6h = None
                if date_str == today_str:
                    snow_6h = self._calculate_last_hours_sum(
                        hourly_data, 'snowfall', hourly_times, 6
                    )

                # Prepare fields for Airtable update (regular fields + snow trio)
                om_fields = {
                    'datetime': date_str,  # match existing VC records
                    'om_temp': temp_c,
                    'om_temp_f': temp_f,
                    'om_humidity': daily_humidity,
                    'om_precipitation': daily_precip,
                    'om_weather_code': daily_code,
                    'om_pressure': daily_pressure,
                    'om_wind_speed': daily_wind,
                    'om_elevation': self.elevation,
                    'om_data_timestamp': datetime.now().isoformat(),

                    # ✅ always included when present
                    'om_snowfall': daily_snowfall,
                    'om_snowfall_6h': snow_6h,
                    'om_snow_depth': daily_snow_depth,
                }

                # Convert wind speed km/h -> mph
                if om_fields['om_wind_speed'] is not None:
                    om_fields['om_wind_speed_mph'] = om_fields['om_wind_speed'] * 0.621371

                # Clean up / normalize numeric fields
                cleaned_fields: Dict[str, object] = {}
                for k, v in om_fields.items():
                    if v is None or v == "":
                        continue  # skip None so we don't overwrite Airtable with blanks

                    try:
                        if k in [
                            'om_temp', 'om_temp_f', 'om_humidity', 'om_pressure',
                            'om_wind_speed', 'om_wind_speed_mph', 'om_snow_depth'
                        ]:
                            cleaned_fields[k] = round(float(v), 1)
                        elif k in ['om_precipitation', 'om_snowfall', 'om_snowfall_6h']:
                            cleaned_fields[k] = round(float(v), 2)
                        elif k in ['om_weather_code', 'om_elevation']:
                            cleaned_fields[k] = int(v)
                        else:
                            cleaned_fields[k] = v
                    except Exception:
                        cleaned_fields[k] = v

                records.append(cleaned_fields)

            logger.info(
                f"Prepared {len(records)} Open-Meteo records for update",
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
            for i, time_str in enumerate(hourly_times):
                if i < len(variable_data) and time_str.startswith(target_date):
                    value = variable_data[i]
                    if value is not None:
                        found = True
                        total += float(value)

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
            for i, time_str in enumerate(hourly_times):
                if i < len(variable_data) and time_str.startswith(target_date):
                    value = variable_data[i]
                    if value is not None:
                        values.append(float(value))

            if not values:
                return None

            return sum(values) / len(values)
        except Exception as e:
            logger.error(
                f"Error calculating daily average for {variable}: {e}",
                extra={'context': 'OpenMeteo Data Calculation Error'}
            )
            return None

    def _calculate_last_hours_sum(
        self,
        hourly_data: Dict,
        variable: str,
        hourly_times: List[str],
        hours: int
    ):
        """
        Calculate rolling sum over the last N hours ending now,
        aligned to timestamps (not just "last N non-nulls").
        """
        try:
            variable_data = hourly_data.get(variable, [])
            if not variable_data or not hourly_times:
                return None

            now = datetime.now()
            window_start = now - timedelta(hours=hours)

            total = 0.0
            found = False

            for i, time_str in enumerate(hourly_times):
                if i >= len(variable_data):
                    continue
                try:
                    t = datetime.fromisoformat(time_str)
                except ValueError:
                    continue

                if window_start < t <= now:
                    value = variable_data[i]
                    if value is not None:
                        total += float(value)
                        found = True

            return total if found else None
        except Exception as e:
            logger.error(
                f"Error calculating last {hours} hours sum for {variable}: {e}",
                extra={'context': 'OpenMeteo Data Calculation Error'}
            )
            return None


def test_openmeteo_fetch():
    """
    Simple test function to verify that Open-Meteo fetch
    and record preparation are working.
    """
    try:
        print("🌤️  Testing Open-Meteo Weather Fetcher...")
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
    test_openmeteo_fetch()
