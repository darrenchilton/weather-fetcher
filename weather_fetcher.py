import requests
from datetime import datetime, timedelta
import logging
import os
from typing import Dict, List, Optional, Union
import time
import json
import traceback
from dotenv import load_dotenv
load_dotenv() 

log_path = os.path.join('/Users/plex/Projects/weather_fetcher', 'output.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s - %(context)s',
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class WeatherDataFetcher:
    def __init__(self):
        self.api_key = os.getenv('WEATHER_API_KEY')
        self.base_url = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"
        logger.info("Initialized WeatherDataFetcher", extra={'context': 'Initialization'})

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
            logger.info(f"Fetching data from URL: {url}", extra={'context': 'Data Retrieval'})
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Successfully fetched weather data for {location} ({len(data.get('days', []))} days)", 
                       extra={'context': 'Data Retrieval'})
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching weather data: {e}", extra={'context': 'Data Retrieval Error'})
            if hasattr(response, 'text'):
                logger.error(f"API Response: {response.text}", extra={'context': 'API Error'})
            raise

class AirtableAPI:
    def __init__(self):
        self.api_key = os.getenv('AIRTABLE_API_KEY')
        self.base_id = os.getenv('AIRTABLE_BASE_ID')
        self.weather_table_name = "WX"
        self.weather_api_url = f"https://api.airtable.com/v0/{self.base_id}/{self.weather_table_name}"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        logger.info("Initialized Airtable API", extra={'context': 'Initialization'})

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
            logger.info(f"Found {len(existing_records)} existing records", 
                       extra={'context': 'Data Retrieval'})
            return existing_records
        except Exception as e:
            logger.error(f"Error fetching existing records: {e}", 
                        extra={'context': 'Data Retrieval Error'})
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
                logger.info(f"Prepared {len(records)} records", extra={'context': 'Data Preparation'})
            return records
        except Exception as e:
            logger.error(f"Error preparing records: {e}", extra={'context': 'Data Preparation Error'})
            raise

    def push_records(self, new_records: List[Dict], existing_records: Dict[str, Dict]) -> bool:
        if not new_records:
            logger.info("No records to process", extra={'context': 'Data Update'})
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
            logger.info(f"Creating {len(records_to_create)} new records", 
                       extra={'context': 'Data Creation'})
            success = success and self._batch_create(records_to_create)
        if records_to_update:
            logger.info(f"Updating {len(records_to_update)} existing records", 
                       extra={'context': 'Data Update'})
            success = success and self._batch_update(records_to_update)
        return success

    def _fields_have_changed(self, existing_fields: Dict, new_fields: Dict) -> bool:
        for key, new_value in new_fields.items():
            if key not in existing_fields:
                return True
            existing_value = existing_fields[key]
            if isinstance(new_value, (int, float)) and isinstance(existing_value, (int, float)):
                if abs(float(new_value) - float(existing_value)) > 0.0001:
                    logger.info(f"Field {key} changed from {existing_value} to {new_value}", 
                              extra={'context': 'Data Comparison'})
                    return True
            elif new_value != existing_value:
                logger.info(f"Field {key} changed from {existing_value} to {new_value}", 
                          extra={'context': 'Data Comparison'})
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
                logger.info(f"Created batch {i//batch_size + 1} ({len(batch)} records)", 
                          extra={'context': 'Batch Creation'})
                time.sleep(0.2)
            except requests.exceptions.RequestException as e:
                logger.error(f"Error creating batch {i//batch_size + 1}: {e}", 
                           extra={'context': 'Batch Creation Error'})
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
                logger.info(f"Updated batch {i//batch_size + 1} ({len(batch)} records)", 
                          extra={'context': 'Batch Update'})
                time.sleep(0.2)
            except requests.exceptions.RequestException as e:
                logger.error(f"Error updating batch {i//batch_size + 1}: {e}", 
                           extra={'context': 'Batch Update Error'})
                success = False
                break
        return success

def main():
    fetcher = WeatherDataFetcher()
    airtable = AirtableAPI()

    try:
        logger.info("Starting weather data fetch and update process", 
                   extra={'context': 'Process Start'})
        location = "12439"
        logger.info(f"Fetching weather data for location: {location}", 
                   extra={'context': 'Data Retrieval'})

        try:
            raw_data = fetcher.fetch_weather_data(location)
        except Exception as e:
            logger.error(f"Failed to fetch weather data: {e}", 
                        extra={'context': 'Data Retrieval Error'})
            return

        if raw_data:
            try:
                existing_records = airtable.get_existing_records()
                logger.info(f"Retrieved {len(existing_records)} existing records", 
                          extra={'context': 'Data Comparison'})
            except Exception as e:
                logger.error(f"Failed to retrieve existing records: {e}", 
                           extra={'context': 'Data Retrieval Error'})
                return

            try:
                all_records = airtable.prepare_airtable_records(raw_data)
                logger.info(f"Prepared {len(all_records)} records for update", 
                          extra={'context': 'Data Preparation'})
            except Exception as e:
                logger.error(f"Failed to prepare records: {e}", 
                           extra={'context': 'Data Preparation Error'})
                return

            try:
                success = airtable.push_records(all_records, existing_records)
                if success:
                    logger.info(f"Successfully processed {len(all_records)} records", 
                              extra={'context': 'Data Update'})
                else:
                    logger.error("Some errors occurred during processing", 
                               extra={'context': 'Data Update Error'})
            except Exception as e:
                logger.error(f"Failed to push records: {e}", 
                           extra={'context': 'Data Update Error'})
                return
        else:
            logger.warning("No weather data retrieved", 
                         extra={'context': 'Data Retrieval Warning'})

    except Exception as e:
        logger.error(f"Unexpected error in main process: {e}", 
                    extra={'context': 'Process Error'})
    finally:
        logger.info("Completed weather data fetch and update process", 
                   extra={'context': 'Process Complete'})

if __name__ == "__main__":
    main()
