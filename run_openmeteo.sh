#!/bin/bash

# Open-Meteo Weather Data Update Script
# Runs every 6 hours, 30 minutes after main weather fetch
# Updates existing Airtable records with Open-Meteo data for comparison

# Set PATH for cron environment
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Project directory
PROJECT_DIR="/Users/plex/Projects/weather_fetcher"

# Change to project directory
cd "$PROJECT_DIR"

# Log script start
echo "$(date): Starting Open-Meteo update script" >> "$PROJECT_DIR/openmeteo_update.log"

# Activate virtual environment and run the Open-Meteo updater
"$PROJECT_DIR/venv/bin/python" "$PROJECT_DIR/update_openmeteo.py" >> "$PROJECT_DIR/openmeteo_update.log" 2>&1

# Capture exit code
EXIT_CODE=$?

# Log completion
if [ $EXIT_CODE -eq 0 ]; then
    echo "$(date): Open-Meteo update completed successfully" >> "$PROJECT_DIR/openmeteo_update.log"
else
    echo "$(date): Open-Meteo update failed with exit code $EXIT_CODE" >> "$PROJECT_DIR/openmeteo_update.log"
fi

exit $EXIT_CODE
