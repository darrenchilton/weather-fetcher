"""
CHANGELOG
2025-12-04: Added Open-Meteo snowfall + snow depth support.
- Requests hourly snowfall and snow_depth.
- Requests daily snowfall_sum (forecast fallback).
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
import json
from dotenv import load_dotenv

load_dotenv()

# Configure logging to match existing system
logger = logging.getLogger(__name__)

class OpenMeteoFetcher:
    def __init__(self):
        self.base_url = "https://api.open-meteo.com/v1/forecast"
        # Hensonville, NY coordinates
        self.lat = 42.28
        self.lon = -74.21
        self.elevation = 549  # meters (1,801 ft) - closer to actual 1,972ft than airports
        logger.info("Initialized OpenMeteoFetcher for Hensonville, NY",
                   extra={'context': 'OpenMeteo Initialization'})

    def fetch_weather_data(self, latitude: float = None, longitude: float = None,
                           start_time: datetime = None, end_time: datetime = None) -> Dict:
        """Backwards-compatible alias used by update_openmeteo.py."""
        return self.get_weather_data(latitude=latitude, longitude=longitude,
                                     start_time=start_time, end_time=end_time)

    def get_weather_data(self, latitude: float = None, longitude: float = None,
                         start_time: datetime = None, end_time: datetime = None) -> Dict:
        """
        Fetch forecast data from Open-Meteo API
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
            'forecast_days': 16
        }

        if start_time is not None:
            params['start_date'] = start_time.strftime('%Y-%m-%d')
        if end_time is not None:
            params['end_date'] = end_time.strftime('%Y-%m-%d')

        try:
            logger.info(f"Fetching Open-Meteo data for coordinates: {lat}, {lon}",
                       extra={'context': 'OpenMeteo Data Retrieval'})

            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            logger.info("Successfully retrieved Open-Meteo forecast data",
                       extra={'context': 'OpenMeteo Data Retrieved'})
            return data

        except requests.RequestException as e:
            logger.error(f"Error fetching Open-Meteo data: {e}",
                        extra={'context': 'OpenMeteo API Error'})
            raise

    def prepare_records(self, data: Dict) -> List[Dict]:
        """
        Prepare records for Airtable update from Open-Meteo data
        """
        try:
            records: List[Dict] = []

            daily_data = data.get('daily', {})
            hourly_data = data.get('hourly', {})
            daily_times = daily_data.get('time', [])
            hourly_times = hourly_data.get('time', [])

            if not daily_times:
                logger.warning("No daily data available from Open-Meteo",
                             extra={'context': 'OpenMeteo Data Preparation'})
                return records

            today_str = datetime.now().strftime('%Y-%m-%d')

            temps_c = daily_data.get('temperature_2m_mean', [])
            precip_sums = daily_data.get('precipitation_sum', [])
            snowfall_sums = daily_data.get('snowfall_sum', [])
            weather_codes = daily_data.get('weather_code', [])
            wind_max = daily_data.get('wind_speed_10m_max', [])

            for i, date_str in enumerate(daily_times):
                # Temperature from daily data
                temp_c = temps_c[i] if i < len(temps_c) else None
                temp_f = (temp_c * 9/5) + 32 if temp_c is not None else None

                daily_precip = precip_sums[i] if i < len(precip_sums) else None
                daily_code = weather_codes[i] if i < len(weather_codes) else None
                daily_wind = wind_max[i] if i < len(wind_max) else None

                # Daily averages from hourly data
                daily_humidity = self._calculate_daily_average(
                    hourly_data, 'relative_humidity_2m', hourly_times, date_str
                )
                daily_pressure = self._calculate_daily_average(
                    hourly_data, 'surface_pressure', hourly_times, date_str
                )

                # Snow fields
                daily_snow_depth = self._calculate_daily_average(
                    hourly_data, 'snow_depth', hourly_times, date_str
                )

                daily_snowfall = self._calculate_daily_sum(
                    hourly_data, 'snowfall', hourly_times, date_str
                )
                if daily_snowfall is None:
                    daily_snowfall = snowfall_sums[i] if i < len(snowfall_sums) else None

                snow_6h = None
                if date_str == today_str:
                    snow_6h = self._calculate_last_hours_sum(
                        hourly_data, 'snowfall', hourly_times, 6
                    )

                om_fields = {
                    'datetime': date_str,  # match existing VC records
                    'om_temp': temp_c,     # Celsius
                    'om_temp_f': temp_f,   # Fahrenheit for comparison
                    'om_humidity': daily_humidity,
                    'om_precipitation': daily_precip,
                    'om_weather_code': daily_code,
                    'om_pressure': daily_pressure,
                    'om_wind_speed': daily_wind,
                    'om_elevation': self.elevation,
                    'om_data_timestamp': datetime.now().isoformat(),

                    # new snow fields
                    'om_snowfall': daily_snowfall,
                    'om_snowfall_6h': snow_6h,
                    'om_snow_depth': daily_snow_depth,
                }

                # Convert wind speed from km/h to mph
                if om_fields['om_wind_speed'] is not None:
                    om_fields['om_wind_speed_mph'] = om_fields['om_wind_speed'] * 0.621371

                # Clean fields (remove None values and ensure proper types)
                cleaned_fields = {}
                for k, v in om_fields.items():
                    if v is not None and v != "":
                        if k in ['om_temp', 'om_temp_f', 'om_humidity', 'om_pressure',
                                 'om_wind_speed', 'om_wind_speed_mph', 'om_snow_depth']:
                            cleaned_fields[k] = round(float(v), 1)
                        elif k in ['om_weather_code', 'om_elevation']:
                            cleaned_fields[k] = int(v)
                        elif k in ['om_precipitation', 'om_snowfall', 'om_snowfall_6h']:
                            cleaned_fields[k] = round(float(v), 2)
                        else:
                            cleaned_fields[k] = v

                records.append(cleaned_fields)

            logger.info(f"Prepared {len(records)} Open-Meteo records for update",
                       extra={'context': 'OpenMeteo Data Preparation'})
            return records

        except Exception as e:
            logger.error(f"Error preparing Open-Meteo records: {e}",
                        extra={'context': 'OpenMeteo Data Preparation Error'})
            raise

    def prepare_daily_records(self, data: Dict) -> List[Dict]:
        """Backwards compatibility alias."""
        return self.prepare_records(data)

    def _calculate_daily_sum(self, hourly_data: Dict, variable: str, hourly_times: List[str], target_date: str):
        """
        Calculate daily sum from hourly data for a specific variable and date
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
                        total += float(value)
                        found = True

            return total if found else None

        except Exception as e:
            logger.warning(f"Error calculating daily sum for {variable}: {e}",
                         extra={'context': 'OpenMeteo Data Calculation'})
            return None

    def _calculate_last_hours_sum(self, hourly_data: Dict, variable: str, hourly_times: List[str], hours: int):
        """
        Calculate rolling sum over the last `hours` hours ending now
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
            logger.warning(f"Error calculating last-{hours}h sum for {variable}: {e}",
                         extra={'context': 'OpenMeteo Data Calculation'})
            return None

    def _calculate_daily_average(self, hourly_data: Dict, variable: str, hourly_times: List[str], target_date: str):
        """
        Calculate daily average from hourly data for a specific variable and date
        """
        try:
            variable_data = hourly_data.get(variable, [])
            if not variable_data or not hourly_times:
                return None

            daily_values = []
            for i, time_str in enumerate(hourly_times):
                if i < len(variable_data) and time_str.startswith(target_date):
                    value = variable_data[i]
                    if value is not None:
                        daily_values.append(float(value))

            if not daily_values:
                return None

            return sum(daily_values) / len(daily_values)

        except Exception as e:
            logger.warning(f"Error calculating daily average for {variable}: {e}",
                         extra={'context': 'OpenMeteo Data Calculation'})
            return None


def test_openmeteo_fetch() -> bool:
    """
    Test function to verify Open-Meteo data retrieval and processing
    Returns True if successful, False otherwise
    """
    try:
        print("🌤️  Testing Open-Meteo Weather Fetcher...")
        fetcher = OpenMeteoFetcher()

        data = fetcher.get_weather_data()

        if data:
            print(f"✅ Successfully fetched data from Open-Meteo")
            records = fetcher.prepare_records(data)

            if records:
                print(f"✅ Successfully prepared {len(records)} records for Airtable")
                sample = records[0]
                print(f"📊 Sample record for {sample['datetime']}:")
                print(f"   Temperature: {sample.get('om_temp_f', 'N/A')}°F ({sample.get('om_temp', 'N/A')}°C)")
                print(f"   Humidity: {sample.get('om_humidity', 'N/A')}%")
                print(f"   Precipitation: {sample.get('om_precipitation', 'N/A')}mm")
                print(f"   Snowfall (daily): {sample.get('om_snowfall', 'N/A')}")
                print(f"   Snowfall (6h): {sample.get('om_snowfall_6h', 'N/A')}")
                print(f"   Snow depth (avg): {sample.get('om_snow_depth', 'N/A')}")
                print(f"   Weather Code: {sample.get('om_weather_code', 'N/A')}")
                print(f"   Elevation: {sample.get('om_elevation', 'N/A')}m")

            return True
        else:
            print("❌ No data received from Open-Meteo API")
            return False

    except Exception as e:
        print(f"❌ Error testing Open-Meteo fetch: {e}")
        return False


if __name__ == "__main__":
    test_openmeteo_fetch()
