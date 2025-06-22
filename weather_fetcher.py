import requests
from datetime import datetime, timedelta
import logging
import os
from typing import Dict, List, Optional, Union
import time
import json
import traceback
import sys
from dotenv import load_dotenv
load_dotenv() 

# GitHub Actions compatible logging setup
def setup_logging():
    """Setup logging configuration optimized for GitHub Actions"""
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    
    handlers = [logging.StreamHandler(sys.stdout)]
    
    # Only add file handler if we're running locally (not in GitHub Actions)
    if not os.getenv('GITHUB_ACTIONS'):
        log_path = os.path.join('/Users/plex/Projects/weather_fetcher', 'output.log')
        if os.path.exists(os.path.dirname(log_path)):
            handlers.append(logging.FileHandler(log_path))
    
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=handlers
    )
    
    return logging.getLogger(__name__)

logger = setup_logging()

class WeatherDataFetcher:
    def __init__(self):
        self.api_key = os.getenv('WEATHER_API_KEY')
        self.base_url = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"
        logger.info("Initialized WeatherDataFetcher")

    def fetch_weather_data(self, location: str) -> Optional[Dict]:
        end_date = datetime.now() + timedelta(days=15)
        start_date = datetime.now() - timedelta(days=30)
        params = {
            'key': self.api_key,
            'unitGroup': 'metric',
            'include': 'days',
            'contentType': 'json',
        }
        url = f"{self.base_url}/{location}/{start_date.strftime('%Y-%m-%d')}/{end_date.strftime('%Y-%m-%d')}"
        
        try:
            logger.info(f"Fetching data from URL: {url}")
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Successfully fetched weather data for {location} ({len(data.get('days', []))} days)")
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching weather data: {e}")
            if hasattr(response, 'text'):
                logger.error(f"API Response: {response.text}")
            raise

class AirtableAPI:
    # Add these methods to your existing AirtableAPI class in weather_fetcher.py

def update_records_with_openmeteo(self, openmeteo_records: List[Dict]) -> bool:
    """
    Update existing Airtable records with Open-Meteo data
    Matches records by datetime field and adds OM fields
    """
    if not openmeteo_records:
        logger.info("No Open-Meteo records to process", 
                   extra={'context': 'OpenMeteo Update'})
        return True

    try:
        # Get existing Visual Crossing records
        existing_records = self.get_existing_records()
        logger.info(f"Found {len(existing_records)} existing VC records for OM update", 
                   extra={'context': 'OpenMeteo Update'})

        records_to_update = []
        matched_count = 0
        
        for om_record in openmeteo_records:
            om_date = om_record['datetime']
            
            if om_date in existing_records:
                matched_count += 1
                existing_record = existing_records[om_date]
                
                # Calculate temperature difference (VC - OM)
                vc_temp = existing_record['fields'].get('temp')
                om_temp_f = om_record.get('om_temp_f')
                temp_difference = None
                
                if vc_temp is not None and om_temp_f is not None:
                    temp_difference = round(float(vc_temp) - float(om_temp_f), 1)
                
                # Prepare update record with OM fields + temperature difference
                update_fields = {k: v for k, v in om_record.items() if k != 'datetime'}
                if temp_difference is not None:
                    update_fields['temp_difference'] = temp_difference
                
                update_record = {
                    'id': existing_record['id'],
                    'fields': update_fields
                }
                records_to_update.append(update_record)
                
                logger.info(f"Matched OM data for {om_date}: temp_diff={temp_difference}°F", 
                           extra={'context': 'OpenMeteo Matching'})
            else:
                logger.warning(f"No existing VC record found for {om_date}", 
                             extra={'context': 'OpenMeteo Matching'})

        logger.info(f"Matched {matched_count}/{len(openmeteo_records)} OM records with existing VC data", 
                   extra={'context': 'OpenMeteo Update'})

        # Update records in batches
        if records_to_update:
            success = self._batch_update_openmeteo(records_to_update)
            if success:
                logger.info(f"Successfully updated {len(records_to_update)} records with Open-Meteo data", 
                           extra={'context': 'OpenMeteo Update'})
            return success
        else:
            logger.info("No records to update with Open-Meteo data", 
                       extra={'context': 'OpenMeteo Update'})
            return True

    except Exception as e:
        logger.error(f"Error updating records with Open-Meteo data: {e}", 
                    extra={'context': 'OpenMeteo Update Error'})
        raise

def _batch_update_openmeteo(self, records: List[Dict], batch_size: int = 10) -> bool:
    """
    Update records in batches specifically for Open-Meteo data
    """
    success = True
    
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        payload = {"records": batch}
        
        try:
            response = requests.patch(self.weather_api_url, headers=self.headers, json=payload)
            response.raise_for_status()
            logger.info(f"Updated OM batch {i//batch_size + 1} ({len(batch)} records)", 
                       extra={'context': 'OpenMeteo Batch Update'})
            time.sleep(0.2)  # Rate limiting
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error updating OM batch {i//batch_size + 1}: {e}", 
                        extra={'context': 'OpenMeteo Batch Update Error'})
            success = False
            break
    
    return success

def get_temperature_comparison_stats(self) -> Dict:
    """
    Analyze temperature differences between Visual Crossing and Open-Meteo
    Returns statistics for monitoring data quality
    """
    try:
        existing_records = self.get_existing_records()
        
        differences = []
        valid_comparisons = 0
        
        for date, record_data in existing_records.items():
            fields = record_data['fields']
            vc_temp = fields.get('temp')
            om_temp_f = fields.get('om_temp_f')
            
            if vc_temp is not None and om_temp_f is not None:
                diff = float(vc_temp) - float(om_temp_f)
                differences.append(diff)
                valid_comparisons += 1
        
        if differences:
            stats = {
                'total_comparisons': valid_comparisons,
                'mean_difference': round(sum(differences) / len(differences), 2),
                'max_difference': round(max(differences), 2),
                'min_difference': round(min(differences), 2),
                'abs_mean_difference': round(sum(abs(d) for d in differences) / len(differences), 2)
            }
            
            logger.info(f"Temperature comparison stats: {stats}", 
                       extra={'context': 'Temperature Analysis'})
            return stats
        else:
            logger.warning("No valid temperature comparisons found", 
                         extra={'context': 'Temperature Analysis'})
            return {}
            
    except Exception as e:
        logger.error(f"Error calculating temperature comparison stats: {e}", 
                    extra={'context': 'Temperature Analysis Error'})
        return {}
    def __init__(self):
        self.api_key = os.getenv('AIRTABLE_API_KEY')
        self.base_id = os.getenv('AIRTABLE_BASE_ID')
        self.weather_table_name = "WX"
        self.weather_api_url = f"https://api.airtable.com/v0/{self.base_id}/{self.weather_table_name}"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        logger.info("Initialized Airtable API")

    def get_existing_records(self) -> Dict[str, Dict]:
        existing_records = {}
        url = self.weather_api_url
        try:
            while True:
                response = requests.get(url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                for record in data.get('records', []):
                    if 'datetime' in record.get('fields', {}):
                        existing_records[record['fields']['datetime']] = {
                            'id': record['id'],
                            'fields': record['fields']
                        }
                if 'offset' in data:
                    url = f"{self.weather_api_url}?offset={data['offset']}"
                    time.sleep(0.2)
                else:
                    break
            logger.info(f"Found {len(existing_records)} existing records")
            return existing_records
        except Exception as e:
            logger.error(f"Error fetching existing records: {e}")
            raise

    def prepare_airtable_records(self, raw_data: Dict) -> List[Dict]:
        records = []
        try:
            for day in raw_data.get('days', []):
                fields = {
                    'datetime': day.get('datetime'),
                    'temp': day.get('temp'),
                    'tempmax': day.get('tempmax'),
                    'tempmin': day.get('tempmin'),
                    'feelslike': day.get('feelslike'),
                    'feelslikemax': day.get('feelslikemax'),
                    'feelslikemin': day.get('feelslikemin'),
                    'humidity': day.get('humidity'),
                    'dew': day.get('dew'),
                    'precip': day.get('precip'),
                    'precipprob': day.get('precipprob'),
                    'precipcover': day.get('precipcover'),
                    'preciptype': ','.join(day.get('preciptype', [])) if day.get('preciptype') else None,
                    'snow': day.get('snow'),
                    'snowdepth': day.get('snowdepth'),
                    'windgust': day.get('windgust'),
                    'windspeed': day.get('windspeed'),
                    'winddir': day.get('winddir'),
                    'sealevelpressure': day.get('pressure'),
                    'cloudcover': day.get('cloudcover'),
                    'visibility': day.get('visibility'),
                    'solarradiation': day.get('solarradiation'),
                    'solarenergy': day.get('solarenergy'),
                    'uvindex': day.get('uvindex'),
                    'severerisk': day.get('severerisk'),
                    'sunrise': day.get('sunrise'),
                    'sunset': day.get('sunset'),
                    'moonphase': day.get('moonphase'),
                    'conditions': day.get('conditions'),
                    'icon': day.get('icon'),
                    'stations': ','.join(day.get('stations', [])) if day.get('stations') else None,
                    'Loc': raw_data.get('address'),
                    'description': day.get('description') or raw_data.get('description')
                }
                
                cleaned_fields = {}
                for k, v in fields.items():
                    if v is not None and v != "":
                        if isinstance(v, str) and v.replace('.', '').replace('-', '').isdigit():
                            try:
                                v = float(v)
                            except ValueError:
                                pass
                        cleaned_fields[k] = v
                
                records.append({'fields': cleaned_fields})
            
            if records:
                logger.info(f"Prepared {len(records)} records")
            return records
        except Exception as e:
            logger.error(f"Error preparing records: {e}")
            raise

    def push_records(self, new_records: List[Dict], existing_records: Dict[str, Dict]) -> bool:
        if not new_records:
            logger.info("No records to process")
            return True

        records_to_create = []
        records_to_update = []
        for record in new_records:
            date = record['fields']['datetime']
            if date in existing_records:
                if self._fields_have_changed(existing_records[date]['fields'], record['fields']):
                    update_record = {
                        'id': existing_records[date]['id'],
                        'fields': record['fields']
                    }
                    records_to_update.append(update_record)
            else:
                records_to_create.append(record)

        success = True
        if records_to_create:
            logger.info(f"Creating {len(records_to_create)} new records")
            success = success and self._batch_create(records_to_create)
        if records_to_update:
            logger.info(f"Updating {len(records_to_update)} existing records")
            success = success and self._batch_update(records_to_update)
        return success

    def _fields_have_changed(self, existing_fields: Dict, new_fields: Dict) -> bool:
        for key, new_value in new_fields.items():
            if key not in existing_fields:
                return True
            existing_value = existing_fields[key]
            if isinstance(new_value, (int, float)) and isinstance(existing_value, (int, float)):
                if abs(float(new_value) - float(existing_value)) > 0.0001:
                    logger.info(f"Field {key} changed from {existing_value} to {new_value}")
                    return True
            elif new_value != existing_value:
                logger.info(f"Field {key} changed from {existing_value} to {new_value}")
                return True
        return False

    def _batch_create(self, records: List[Dict], batch_size: int = 10) -> bool:
        success = True
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            payload = {"records": batch}
            try:
                response = requests.post(self.weather_api_url, headers=self.headers, json=payload)
                response.raise_for_status()
                logger.info(f"Created batch {i//batch_size + 1} ({len(batch)} records)")
                time.sleep(0.2)
            except requests.exceptions.RequestException as e:
                logger.error(f"Error creating batch {i//batch_size + 1}: {e}")
                success = False
                break
        return success

    def _batch_update(self, records: List[Dict], batch_size: int = 10) -> bool:
        success = True
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            payload = {"records": batch}
            try:
                response = requests.patch(self.weather_api_url, headers=self.headers, json=payload)
                response.raise_for_status()
                logger.info(f"Updated batch {i//batch_size + 1} ({len(batch)} records)")
                time.sleep(0.2)
            except requests.exceptions.RequestException as e:
                logger.error(f"Error updating batch {i//batch_size + 1}: {e}")
                success = False
                break
        return success

def main():
    fetcher = WeatherDataFetcher()
    airtable = AirtableAPI()

    try:
        logger.info("Starting weather data fetch and update process")
        location = "12439"
        logger.info(f"Fetching weather data for location: {location}")

        try:
            raw_data = fetcher.fetch_weather_data(location)
        except Exception as e:
            logger.error(f"Failed to fetch weather data: {e}")
            if os.getenv('GITHUB_ACTIONS'):
                print(f"::error title=Weather Fetch Failed::{str(e)}")
            sys.exit(1)

        if raw_data:
            try:
                existing_records = airtable.get_existing_records()
                logger.info(f"Retrieved {len(existing_records)} existing records")
            except Exception as e:
                logger.error(f"Failed to retrieve existing records: {e}")
                if os.getenv('GITHUB_ACTIONS'):
                    print(f"::error title=Airtable Access Failed::{str(e)}")
                sys.exit(1)

            try:
                all_records = airtable.prepare_airtable_records(raw_data)
                logger.info(f"Prepared {len(all_records)} records for update")
            except Exception as e:
                logger.error(f"Failed to prepare records: {e}")
                if os.getenv('GITHUB_ACTIONS'):
                    print(f"::error title=Data Preparation Failed::{str(e)}")
                sys.exit(1)

            try:
                success = airtable.push_records(all_records, existing_records)
                if success:
                    logger.info(f"Successfully processed {len(all_records)} records")
                    if os.getenv('GITHUB_ACTIONS'):
                        print(f"::notice title=Weather Fetch Complete::Successfully processed {len(all_records)} records")
                else:
                    logger.error("Some errors occurred during processing")
                    if os.getenv('GITHUB_ACTIONS'):
                        print(f"::warning title=Partial Success::Some errors occurred during processing")
            except Exception as e:
                logger.error(f"Failed to push records: {e}")
                if os.getenv('GITHUB_ACTIONS'):
                    print(f"::error title=Data Push Failed::{str(e)}")
                sys.exit(1)
        else:
            logger.warning("No weather data retrieved")
            if os.getenv('GITHUB_ACTIONS'):
                print(f"::warning title=No Data::No weather data retrieved")

    except Exception as e:
        logger.error(f"Unexpected error in main process: {e}")
        if os.getenv('GITHUB_ACTIONS'):
            print(f"::error title=Process Error::{str(e)}")
        sys.exit(1)
    finally:
        logger.info("Completed weather data fetch and update process")

if __name__ == "__main__":
    main()
