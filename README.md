# Weather Fetcher

A comprehensive Python weather service that fetches data from multiple sources and stores it in Airtable for analysis and comparison.

## Features

### Core Weather Data (Visual Crossing)
- Fetches 45 days of weather data (30 historical + 15 forecast)
- Runs every 6 hours via cron
- Handles API rate limits and batch processing
- Deduplicates and updates existing records

### Comparative Weather Data (Open-Meteo)
- Elevation-corrected weather data (549m vs airport data)
- 7-day forecast with hourly resolution
- Automatic temperature difference calculation
- Independent update process for data comparison

## Data Sources

| Source | API | Location | Elevation | Update Frequency |
|--------|-----|----------|-----------|------------------|
| Visual Crossing | Weather API | ZIP 12439 (airports) | Various | Every 6 hours |
| Open-Meteo | Free API | 42.28°N, -74.21°W | 549m (1,801ft) | Every 6 hours |

## Project Structure

```
/Users/plex/Projects/weather_fetcher/
├── .env                    # API keys and configuration
├── .gitignore             # Git ignore patterns
├── weather_fetcher.py     # Main VC script + OM integration methods
├── openmeteo_fetcher.py   # Open-Meteo data fetcher
├── update_openmeteo.py    # OM update script
├── run_weather.sh         # VC cron script
├── run_openmeteo.sh       # OM cron script
├── requirements.txt       # Python dependencies
├── output.log            # VC application log
└── openmeteo_update.log  # OM application log
```

## Setup

### 1. Create virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Configuration
Create `.env` file with:
```env
WEATHER_API_KEY=your_visual_crossing_key
AIRTABLE_API_KEY=your_airtable_key
AIRTABLE_BASE_ID=your_base_id
```

### 3. Airtable Schema

#### Required Fields in WX Table
**Visual Crossing Fields (existing):**
- `datetime` (Date)
- `temp`, `tempmax`, `tempmin` (Number, 1 decimal)
- `humidity`, `pressure`, `windspeed` (Number, 1 decimal)
- `precip` (Number, 2 decimal)
- `conditions`, `description` (Single line text)

**Open-Meteo Fields (new):**
- `om_temp`, `om_temp_f`, `om_humidity`, `om_pressure`, `om_wind_speed`, `om_wind_speed_mph`, `temp_difference` (Number, 1 decimal)
- `om_weather_code`, `om_elevation` (Number, integer)
- `om_precipitation` (Number, 2 decimal)
- `om_data_timestamp` (Date)

### 4. Cron Setup
```bash
crontab -e
# Add these lines:
0 */6 * * * /Users/plex/Projects/weather_fetcher/run_weather.sh
30 */6 * * * /Users/plex/Projects/weather_fetcher/run_openmeteo.sh
```

## Usage

### Manual Execution
```bash
# Test Visual Crossing fetch
./run_weather.sh

# Test Open-Meteo integration
python openmeteo_fetcher.py

# Test full OM update
python update_openmeteo.py
```

### Monitoring
```bash
# View Visual Crossing logs
tail -f output.log

# View Open-Meteo logs
tail -f openmeteo_update.log

# Check cron jobs
crontab -l

# View temperature comparison stats
grep "Temperature comparison" openmeteo_update.log
```

## Data Analysis

### Temperature Differences
The system automatically calculates temperature differences between Visual Crossing and Open-Meteo:
- **Visual Crossing**: Airport-based data (typically warmer due to heat island effect)
- **Open-Meteo**: Elevation-corrected data (549m, closer to actual location)
- **Expected**: VC temperatures 2-4°F higher than OM

### Weather Code Mapping
Open-Meteo uses WMO weather codes (0-99):
- `0-3`: Clear to overcast conditions
- `45-48`: Fog conditions  
- `51-67`: Rain and drizzle
- `71-86`: Snow conditions
- `95-99`: Thunderstorms

## API Usage

### Visual Crossing
- ~180 API calls daily
- 1000/day limit
- Historical + forecast data

### Open-Meteo  
- ~4 API calls daily
- No rate limits
- Free tier
- 7-day forecast only

## Troubleshooting

### Common Issues

**Open-Meteo update fails:**
```bash
# Check prerequisites
python update_openmeteo.py
# Verify VC data exists first
tail output.log
```

**Temperature differences seem wrong:**
- Verify Airtable field types (Number with 1 decimal)
- Check for missing data in either source
- Review logs for calculation errors

**Cron jobs not running:**
```bash
# Check cron service
sudo systemctl status cron
# Verify script permissions
ls -la run_*.sh
```

### Log Analysis
```bash
# Count successful OM updates
grep "Successfully updated" openmeteo_update.log | wc -l

# View recent temperature stats
grep "Temperature comparison stats" openmeteo_update.log | tail -5

# Check for API errors
grep "Error" *.log
```

## Development

### Testing New Features
```bash
# Test OM fetcher
python openmeteo_fetcher.py

# Test temperature comparison
python -c "
from weather_fetcher import AirtableAPI
api = AirtableAPI()
stats = api.get_temperature_comparison_stats()
print(stats)
"
```

### Adding New Data Sources
1. Create new fetcher class (follow `openmeteo_fetcher.py` pattern)
2. Add fields to Airtable schema
3. Create update methods in `AirtableAPI`
4. Add cron job for regular updates

## Support

- **Setup Date**: November 23, 2024
- **Open-Meteo Integration**: June 22, 2025
- **Backup**: Available on GitHub
- **Location**: Hensonville, NY (ZIP 12439)
- **Coordinates**: 42.28°N, -74.21°W
- **Elevation**: ~1,972ft actual

## License

Private project for weather data collection and analysis.
