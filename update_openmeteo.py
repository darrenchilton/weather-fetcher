#!/usr/bin/env python3
"""
Open-Meteo Weather Data Updater

This script fetches weather data from Open-Meteo API and updates existing 
Airtable records with additional weather data for comparison with Visual Crossing.

Designed to run every 6 hours, 30 minutes after the main weather_fetcher.py
to ensure Visual Crossing data is already in place.

Author: Weather System Integration
Date: June 2025
"""

import sys
import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import traceback

# Add the parent directory to the path to allow importing modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from weather_shared.airtable_client import AirtableWeatherClient
from weather_shared.location_config import LOCATION_CONFIG
from openmeteo_fetcher import OpenMeteoFetcher

# Configure logging
logger = logging.getLogger("openmeteo_updater")
logger.setLevel(logging.INFO)

# Create console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Create formatter and add to console handler
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(context)s - %(message)s'
)
console_handler.setFormatter(formatter)

# Add console handler to logger
logger.addHandler(console_handler)


def get_time_range(hours_back: int = 24, hours_forward: int = 72) -> Dict[str, datetime]:
    """
    Get a time range for fetching Open-Meteo data.
    
    Args:
        hours_back: How many hours back from now to include
        hours_forward: How many hours forward from now to include
        
    Returns:
        Dict with 'start' and 'end' datetime objects in UTC
    """
    now = datetime.utcnow()
    
    # Align to the hour for consistency
    now_aligned = now.replace(minute=0, second=0, microsecond=0)
    
    start_time = now_aligned - timedelta(hours=hours_back)
    end_time = now_aligned + timedelta(hours=hours_forward)
    
    return {"start": start_time, "end": end_time}


def fetch_and_update_openmeteo_data(
    location_config: Dict[str, Any],
    airtable_client: AirtableWeatherClient,
    om_fetcher: OpenMeteoFetcher,
    hours_back: int = 24,
    hours_forward: int = 72
) -> bool:
    """
    Fetch Open-Meteo data and update Airtable records.
    
    Args:
        location_config: Configuration for the location
        airtable_client: Airtable client instance
        om_fetcher: OpenMeteoFetcher instance
        hours_back: How many hours back from now to include
        hours_forward: How many hours forward from now to include
        
    Returns:
        True if successful, False otherwise
    """
    try:
        location_name = location_config["name"]
        
        logger.info(f"Starting Open-Meteo data fetch for {location_name}", 
                    extra={'context': 'OpenMeteo Fetch Start'})
        
        # Get the time range
        time_range = get_time_range(hours_back, hours_forward)
        start_time = time_range["start"]
        end_time = time_range["end"]
        
        logger.info(f"Fetching data from {start_time} to {end_time} UTC", 
                    extra={'context': 'OpenMeteo Time Range'})
        
        # Fetch data from Open-Meteo
        om_raw_data = om_fetcher.fetch_weather_data(
            latitude=location_config["latitude"],
            longitude=location_config["longitude"],
            start_time=start_time,
            end_time=end_time
        )
        
        if not om_raw_data:
            logger.error("No data received from Open-Meteo API", 
                        extra={'context': 'OpenMeteo Data Retrieval Error'})
            return False
        
        # Prepare Open-Meteo records for update
        logger.info("Preparing Open-Meteo data for Airtable update", 
                   extra={'context': 'OpenMeteo Data Preparation'})
        
        try:
            # CHANGED: use prepare_records instead of prepare_daily_records
            om_records = om_fetcher.prepare_records(om_raw_data)
        except Exception as e:
            logger.error(f"Failed to prepare Open-Meteo records: {e}", 
                        extra={'context': 'OpenMeteo Data Preparation Error'})
            return False
        
        if not om_records:
            logger.warning("No Open-Meteo records prepared for update", 
                         extra={'context': 'OpenMeteo Data Preparation Warning'})
            return False
        
        logger.info(f"Prepared {len(om_records)} Open-Meteo records for update", 
                   extra={'context': 'OpenMeteo Data Prepared'})
        
        # Fetch existing Airtable records for the same period
        logger.info("Fetching existing Airtable records for matching", 
                   extra={'context': 'Airtable Fetch'})
        
        airtable_records = airtable_client.get_records_by_time_range(
            start_time=start_time,
            end_time=end_time,
            location_name=location_name
        )
        
        if not airtable_records:
            logger.warning("No Airtable records found for the time range", 
                         extra={'context': 'Airtable Fetch Warning'})
            return False
        
        logger.info(f"Retrieved {len(airtable_records)} existing Airtable records", 
                   extra={'context': 'Airtable Records Retrieved'})
        
        # Match Open-Meteo records to Airtable records and prepare updates
        logger.info("Matching Open-Meteo data to Airtable records", 
                   extra={'context': 'Record Matching'})
        
        update_payloads = airtable_client.prepare_openmeteo_updates(
            airtable_records=airtable_records,
            om_records=om_records
        )
        
        if not update_payloads:
            logger.warning("No updates prepared after matching Open-Meteo to Airtable records", 
                         extra={'context': 'Update Preparation Warning'})
            return False
        
        logger.info(f"Prepared {len(update_payloads)} Airtable update payloads", 
                   extra={'context': 'Update Prepared'})
        
        # Apply updates to Airtable
        logger.info("Applying updates to Airtable records", 
                   extra={'context': 'Airtable Update'})
        
        successful_updates = airtable_client.batch_update_records(update_payloads)
        
        logger.info(f"Successfully updated {successful_updates} Airtable records with Open-Meteo data", 
                   extra={'context': 'Update Complete'})
        
        return True
        
    except Exception as e:
        logger.error(f"Error in Open-Meteo fetch and update process: {e}", 
                    extra={'context': 'OpenMeteo Process Error'})
        logger.error(f"Traceback: {traceback.format_exc()}", 
                    extra={'context': 'OpenMeteo Process Error'})
        return False


def main():
    """
    Main entry point for Open-Meteo updater.
    """
    # Initialize Airtable client
    logger.info("Initializing Airtable client", 
               extra={'context': 'Initialization'})
    
    try:
        airtable_client = AirtableWeatherClient()
    except Exception as e:
        logger.error(f"Failed to initialize Airtable client: {e}", 
                    extra={'context': 'Initialization Error'})
        return False
    
    # Get location configuration for Hensonville, NY
    location_name = "Hensonville, NY"
    
    if location_name not in LOCATION_CONFIG:
        logger.error(f"Location '{location_name}' not found in configuration", 
                    extra={'context': 'Configuration Error'})
        return False
    
    location_config = LOCATION_CONFIG[location_name]
    
    # Initialize Open-Meteo fetcher
    logger.info("Initializing Open-Meteo fetcher", 
               extra={'context': 'Initialization'})
    
    try:
        om_fetcher = OpenMeteoFetcher()
    except Exception as e:
        logger.error(f"Failed to initialize Open-Meteo fetcher: {e}", 
                    extra={'context': 'Initialization Error'})
        return False
    
    # Fetch, process, and update Open-Meteo data
    logger.info(f"Starting Open-Meteo update process for {location_name}", 
               extra={'context': 'OpenMeteo Update Start'})
    
    try:
        success = fetch_and_update_openmeteo_data(
            location_config=location_config,
            airtable_client=airtable_client,
            om_fetcher=om_fetcher,
            hours_back=24,
            hours_forward=72
        )
        
        if success:
            logger.info("Open-Meteo update process completed successfully", 
                       extra={'context': 'OpenMeteo Update Complete'})
            
            # After successful update, we can optionally compute and log some stats
            try:
                logger.info("Computing temperature comparison statistics", 
                           extra={'context': 'Temperature Analysis'})
                
                stats = airtable_client.compute_temperature_comparison_stats(
                    location_name=location_name,
                    hours_back=24
                )
                
                if stats:
                    logger.info("Temperature comparison stats:", 
                               extra={'context': 'Temperature Analysis'})
                    logger.info(f"Records analyzed: {stats.get('records_analyzed', 'N/A')}", 
                               extra={'context': 'Temperature Analysis'})
                    logger.info(f"Average absolute difference: {stats.get('avg_abs_diff', 'N/A')}°", 
                               extra={'context': 'Temperature Analysis'})
                    logger.info(f"Maximum absolute difference: {stats.get('max_abs_diff', 'N/A')}°", 
                               extra={'context': 'Temperature Analysis'})
                    logger.info(f"Comparisons: {stats.get('total_comparisons', 'N/A')}", 
                               extra={'context': 'Temperature Analysis'})
            except Exception as e:
                logger.warning(f"Could not generate temperature comparison stats: {e}", 
                             extra={'context': 'Temperature Analysis Warning'})
            
            return True
        else:
            logger.error("Failed to update Airtable records with Open-Meteo data", 
                        extra={'context': 'OpenMeteo Data Update Error'})
            return False
    
    except Exception as e:
        logger.error(f"Unexpected error in Open-Meteo update process: {e}", 
                    extra={'context': 'OpenMeteo Process Error'})
        logger.error(f"Traceback: {traceback.format_exc()}", 
                    extra={'context': 'OpenMeteo Process Error'})
        return False


if __name__ == "__main__":
    # Add a file handler when running as a script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(script_dir, "logs")
    
    # Create logs directory if it doesn't exist
    os.makedirs(logs_dir, exist_ok=True)
    
    log_file = os.path.join(logs_dir, "openmeteo_update.log")
    
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    
    start_time = datetime.now()
    logger.info(f"Open-Meteo update started at {start_time}", 
               extra={'context': 'Process Timing'})
    
    # Run the update
    success = main()
    
    end_time = datetime.now()
    duration = end_time - start_time
    
    if success:
        logger.info(f"Open-Meteo update completed successfully in {duration}", 
                   extra={'context': 'Process Timing'})
        sys.exit(0)
    else:
        logger.error(f"Open-Meteo update failed after {duration}", 
                    extra={'context': 'Process Timing'})
        sys.exit(1)
