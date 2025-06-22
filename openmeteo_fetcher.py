import requests
from datetime import datetime, timedelta
import logging
import os
from typing import Dict, List, Optional, Union
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

    def fetch_weather_data(self) -> Optional[Dict]:
        """
        Fetch 7-day weather forecast from Open-Meteo API
        Returns data compatible with existing system structure
        """
        params = {
            'latitude': self.lat,
            'longitude': self.lon,
            'hourly': 'temperature_2m,relative_humidity_2m,precipitation,weather_code,surface_pressure,wind_speed_10m',
            'daily': 'temperature_2m_max,temperature_2m_min,temperature_2m_mean,precipitation_sum,weather_code,wind_speed_10m_max',
            'timezone': 'America/New_York',
            'forecast_days': 7
        }
        
        try:
            logger.info(f"Fetching Open-Meteo data for coordinates: {self.lat}, {self.lon}", 
                       extra={'context': 'OpenMeteo Data Retrieval'})
            
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            logger.info(f"Successfully fetched Open-Meteo data ({len(data.get('daily', {}).get('time', []))} days)", 
                       extra={'context': 'OpenMeteo Data Retrieval'})
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching Open-Meteo data: {e}", 
                        extra={'context': 'OpenMeteo Data Retrieval Error'})
            if hasattr(response, 'text'):
                logger.error(f"API Response: {response.text}", 
                           extra={'context': 'OpenMeteo API Error'})
            raise

    def prepare_daily_records(self, raw_data: Dict) -> List[Dict]:
        """
        Convert Open-Meteo data to format compatible with Airtable updates
        Returns list of records with datetime keys for matching with existing VC data
        Uses daily data where available, calculates daily averages from hourly data for other parameters
        """
        records = []
        
        try:
            daily_data = raw_data.get('daily', {})
            hourly_data = raw_data.get('hourly', {})
            daily_times = daily_data.get('time', [])
            hourly_times = hourly_data.get('time', [])
            
            if not daily_times:
                logger.warning("No daily time data found in Open-Meteo response", 
                             extra={'context': 'OpenMeteo Data Preparation'})
                return records
            
            for i, date_str in enumerate(daily_times):
                # Get temperature from daily data (more accurate)
                temp_c = daily_data.get('temperature_2m_mean', [])[i] if i < len(daily_data.get('temperature_2m_mean', [])) else None
                temp_f = (temp_c * 9/5) + 32 if temp_c is not None else None
                
                # Calculate daily averages from hourly data for humidity and pressure
                daily_humidity = self._calculate_daily_average(hourly_data, 'relative_humidity_2m', hourly_times, date_str)
                daily_pressure = self._calculate_daily_average(hourly_data, 'surface_pressure', hourly_times, date_str)
                
                # Prepare fields for Airtable update
                om_fields = {
                    'datetime': date_str,  # This will be used to match existing VC records
                    'om_temp': temp_c,  # Celsius
                    'om_temp_f': temp_f,  # Fahrenheit for comparison
                    'om_humidity': daily_humidity,  # Daily average from hourly data
                    'om_precipitation': daily_data.get('precipitation_sum', [])[i] if i < len(daily_data.get('precipitation_sum', [])) else None,
                    'om_weather_code': daily_data.get('weather_code', [])[i] if i < len(daily_data.get('weather_code', [])) else None,
                    'om_pressure': daily_pressure,  # Daily average from hourly data
                    'om_wind_speed': daily_data.get('wind_speed_10m_max', [])[i] if i < len(daily_data.get('wind_speed_10m_max', [])) else None,
                    'om_elevation': self.elevation,
                    'om_data_timestamp': datetime.now().isoformat()
                }
                
                # Convert wind speed from km/h to mph (Open-Meteo default is km/h)
                if om_fields['om_wind_speed'] is not None:
                    om_fields['om_wind_speed_mph'] = om_fields['om_wind_speed'] * 0.621371
                
                # Clean fields (remove None values and ensure proper types)
                cleaned_fields = {}
                for k, v in om_fields.items():
                    if v is not None and v != "":
                        # Round numeric values appropriately
                        if k in ['om_temp', 'om_temp_f', 'om_humidity', 'om_pressure', 'om_wind_speed', 'om_wind_speed_mph']:
                            cleaned_fields[k] = round(float(v), 1) if v is not None else None
                        elif k in ['om_weather_code', 'om_elevation']:
                            cleaned_fields[k] = int(v) if v is not None else None
                        elif k == 'om_precipitation':
                            cleaned_fields[k] = round(float(v), 2) if v is not None else None
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

    def _calculate_daily_average(self, hourly_data: Dict, variable: str, hourly_times: List[str], target_date: str) -> float:
        """
        Calculate daily average from hourly data for a specific variable and date
        """
        try:
            variable_data = hourly_data.get(variable, [])
            if not variable_data or not hourly_times:
                return None
            
            # Find hourly values for the target date
            daily_values = []
            for i, time_str in enumerate(hourly_times):
                if i < len(variable_data) and time_str.startswith(target_date):
                    value = variable_data[i]
                    if value is not None:
                        daily_values.append(float(value))
            
            # Calculate average
            if daily_values:
                return sum(daily_values) / len(daily_values)
            else:
                return None
                
        except Exception as e:
            logger.warning(f"Error calculating daily average for {variable}: {e}", 
                         extra={'context': 'OpenMeteo Data Calculation'})
            return None

    def get_weather_code_description(self, code: int) -> str:
        """
        Convert WMO weather codes to human-readable descriptions
        """
        code_map = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy", 
            3: "Overcast",
            45: "Fog",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            56: "Light freezing drizzle",
            57: "Dense freezing drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            66: "Light freezing rain",
            67: "Heavy freezing rain",
            71: "Slight snow fall",
            73: "Moderate snow fall",
            75: "Heavy snow fall",
            77: "Snow grains",
            80: "Slight rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            85: "Slight snow showers",
            86: "Heavy snow showers",
            95: "Thunderstorm",
            96: "Thunderstorm with slight hail",
            99: "Thunderstorm with heavy hail"
        }
        return code_map.get(code, f"Unknown code: {code}")

def test_openmeteo_fetch():
    """Test function to verify Open-Meteo API integration"""
    try:
        fetcher = OpenMeteoFetcher()
        raw_data = fetcher.fetch_weather_data()
        
        if raw_data:
            records = fetcher.prepare_daily_records(raw_data)
            print(f"✅ Successfully fetched {len(records)} days of Open-Meteo data")
            
            # Display sample record
            if records:
                sample = records[0]
                print(f"📊 Sample record for {sample['datetime']}:")
                print(f"   Temperature: {sample.get('om_temp_f', 'N/A')}°F ({sample.get('om_temp', 'N/A')}°C)")
                print(f"   Humidity: {sample.get('om_humidity', 'N/A')}%")
                print(f"   Precipitation: {sample.get('om_precipitation', 'N/A')}mm")
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
    # Test the Open-Meteo fetcher
    test_openmeteo_fetch()
