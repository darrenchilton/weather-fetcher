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
import traceback
from datetime import datetime, timedelta

# Add the project directory to Python path
sys.path.append('/Users/plex/Projects/weather_fetcher')

# Import our custom modules
from openmeteo_fetcher import OpenMeteoFetcher
from weather_fetcher import AirtableAPI  # Import existing AirtableAPI class

# Configure logging to match existing system
log_path = os.path.join('/Users/plex/Projects/weather_fetcher', 'openmeteo_update.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s - %(context)s',
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def main():
    """
    Main function to fetch Open-Meteo data and update existing Airtable records
    """
    logger.info("Starting Open-Meteo data update process", 
               extra={'context': 'OpenMeteo Process Start'})
    
    try:
        # Initialize fetchers
        om_fetcher = OpenMeteoFetcher()
        airtable = AirtableAPI()
        
        # Fetch Open-Meteo data
        logger.info("Fetching Open-Meteo weather data", 
                   extra={'context': 'OpenMeteo Data Retrieval'})
        
        try:
            om_raw_data = om_fetcher.fetch_weather_data()
        except Exception as e:
            logger.error(f"Failed to fetch Open-Meteo data: {e}", 
                        extra={'context': 'OpenMeteo Data Retrieval Error'})
            return False
        
        if not om_raw_data:
            logger.error("No data received from Open-Meteo API", 
                        extra={'context': 'OpenMeteo Data Retrieval Error'})
            return False
        
        # Prepare Open-Meteo records for update
        logger.info("Preparing Open-Meteo data for Airtable update", 
                   extra={'context': 'OpenMeteo Data Preparation'})
        
        try:
            om_records = om_fetcher.prepare_daily_records(om_raw_data)
        except Exception as e:
            logger.error(f"Failed to prepare Open-Meteo records: {e}", 
                        extra={'context': 'OpenMeteo Data Preparation Error'})
            return False
        
        if not om_records:
            logger.warning("No Open-Meteo records prepared for update", 
                         extra={'context': 'OpenMeteo Data Preparation Warning'})
            return False
        
        logger.info(f"Prepared {len(om_records)} Open-Meteo records for update", 
                   extra={'context': 'OpenMeteo Data Preparation'})
        
        # Update Airtable records with Open-Meteo data
        logger.info("Updating Airtable records with Open-Meteo data", 
                   extra={'context': 'OpenMeteo Data Update'})
        
        try:
            success = airtable.update_records_with_openmeteo(om_records)
        except Exception as e:
            logger.error(f"Failed to update Airtable with Open-Meteo data: {e}", 
                        extra={'context': 'OpenMeteo Data Update Error'})
            return False
        
        if success:
            logger.info("Successfully completed Open-Meteo data update", 
                       extra={'context': 'OpenMeteo Data Update'})
            
            # Generate temperature comparison statistics
            try:
                stats = airtable.get_temperature_comparison_stats()
                if stats:
                    logger.info(f"Temperature comparison analysis complete: "
                              f"Mean diff: {stats.get('mean_difference', 'N/A')}°F, "
                              f"Comparisons: {stats.get('total_comparisons', 'N/A')}", 
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
    
    finally:
        logger.info("Completed Open-Meteo data update process", 
                   extra={'context': 'OpenMeteo Process Complete'})

def check_prerequisites():
    """
    Check if all prerequisites are met before running the update
    """
    logger.info("Checking prerequisites for Open-Meteo update", 
               extra={'context': 'Prerequisite Check'})
    
    issues = []
    
    # Check if main weather fetcher log exists (indicates VC data was fetched)
    vc_log_path = '/Users/plex/Projects/weather_fetcher/output.log'
    if not os.path.exists(vc_log_path):
        issues.append("Visual Crossing log file not found - main weather fetch may not have run")
    else:
        # Check if VC log has recent entries (within last 2 hours)
        try:
            stat = os.stat(vc_log_path)
            last_modified = datetime.fromtimestamp(stat.st_mtime)
            if datetime.now() - last_modified > timedelta(hours=2):
                issues.append(f"Visual Crossing log last modified {last_modified} - may be stale")
        except Exception as e:
            issues.append(f"Could not check Visual Crossing log timestamp: {e}")
    
    # Check environment variables
    required_env_vars = ['AIRTABLE_API_KEY', 'AIRTABLE_BASE_ID']
    for var in required_env_vars:
        if not os.getenv(var):
            issues.append(f"Environment variable {var} not set")
    
    if issues:
        for issue in issues:
            logger.warning(f"Prerequisite issue: {issue}", 
                         extra={'context': 'Prerequisite Check'})
        return False
    else:
        logger.info("All prerequisites met", 
                   extra={'context': 'Prerequisite Check'})
        return True

if __name__ == "__main__":
    start_time = datetime.now()
    logger.info(f"Open-Meteo update started at {start_time}", 
               extra={'context': 'Process Timing'})
    
    # Check prerequisites
    if not check_prerequisites():
        logger.error("Prerequisites not met - aborting Open-Meteo update", 
                    extra={'context': 'Prerequisite Check'})
        sys.exit(1)
    
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
