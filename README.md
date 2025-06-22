# Weather Fetcher

A comprehensive Python weather service that fetches data from multiple sources and stores it in Airtable for analysis and comparison.

## Features

### Core Weather Data (Visual Crossing)
- Fetches 45 days of weather data (30 historical + 15 forecast)
- Runs every 6 hours via GitHub Actions
- Handles API rate limits and batch processing
- Deduplicates and updates existing records

### Comparative Weather Data (Open-Meteo)
- Elevation-corrected weather data (549m vs airport data)
- 7-day forecast with daily aggregates from hourly data
- Automatic temperature and weather parameter updates
- Independent update process for data comparison

## Data Sources

| Source | API | Location | Elevation | Update Frequency | Cost |
|--------|-----|----------|-----------|------------------|------|
| Visual Crossing | Weather API | ZIP 12439 (airports) | Various airports | Every 6 hours | Paid |
| Open-Meteo | Free API | 42.28°N, -74.21°W | 549m (1,801ft) | Every 6 hours | Free |

## Project Structure

```
weather-fetcher/
├── .github/workflows/
│   └── weather-fetcher.yml      # GitHub Actions automation
├── .env.example                 # Environment template
├── .gitignore                   # Git ignore patterns
├── weather_fetcher.py           # Main VC script + OM integration methods
├── openmeteo_fetcher.py         # Open-Meteo data fetcher
├── update_openmeteo.py          # OM update script
├── run_weather.sh               # VC shell script (legacy)
├── run_openmeteo.sh             # OM shell script (legacy)
├── requirements.txt             # Python dependencies
└── README.md                    # This file
```

## Automation

### GitHub Actions Workflow
- **Visual Crossing**: Every 6 hours at :00 (00:00, 06:00, 12:00, 18:00 UTC)
- **Open-Meteo**: Every 6 hours at :30 (00:30, 06:30, 12:30, 18:30 UTC)
- **Manual triggers**: Available via GitHub Actions interface

### Data Flow
1. Visual Crossing fetches core weather data
2. 30 minutes later, Open-Meteo updates existing records with additional parameters
3. Temperature differences calculated via Airtable formula

## Setup

### 1. GitHub Repository
```bash
git clone https://github.com/YOUR_USERNAME/weather-fetcher.git
cd weather-fetcher
```

### 2. GitHub Secrets
Add these secrets to your GitHub repository (Settings → Secrets and variables → Actions):

```
WEATHER_API_KEY=your_visual_crossing_key
AIRTABLE_API_KEY=your_airtable_key
AIRTABLE_BASE_ID=your_base_id
```

### 3. Airtable Schema

#### Required Fields in WX Table

**Visual Crossing Fields (existing):**
- `datetime` (Date) - Primary date field for record matching
- `temp`, `tempmax`, `tempmin` (Number, 1 decimal) - Temperature data in Celsius
- `humidity`, `pressure`, `windspeed` (Number, 1 decimal) - Weather parameters
- `precip` (Number, 2 decimal) - Precipitation data
- `conditions`, `description` (Single line text) - Weather descriptions
- `Loc` (Single line text) - Location identifier

**Open-Meteo Fields (added):**
- `om_temp` (Number, 1 decimal) - Temperature in Celsius
- `om_temp_f` (Number, 1 decimal) - Temperature in Fahrenheit
- `om_humidity` (Number, 1 decimal) - Daily average humidity
- `om_pressure` (Number, 1 decimal) - Daily average pressure
- `om_wind_speed` (Number, 1 decimal) - Wind speed in km/h
- `om_wind_speed_mph` (Number, 1 decimal) - Wind speed in mph
- `om_weather_code` (Number, integer) - WMO weather code
- `om_elevation` (Number, integer) - Elevation in meters (549m)
- `om_precipitation` (Number, 2 decimal) - Daily precipitation sum
- `om_data_timestamp` (Date) - When OM data was fetched

**Temperature Comparison (calculated in Airtable):**
- `temp_diff_celsius` (Formula) - Temperature difference: `{temp} - {om_temp}`

## Usage

### Manual Execution
GitHub Actions can be triggered manually:
1. Go to your repository → Actions tab
2. Select "Weather Data Fetcher" workflow
3. Click "Run workflow"
4. Choose which job to run or run both

### Monitoring
View workflow runs in the GitHub Actions tab:
- **Success indicators**: ✅ All steps complete
- **Logs**: Click on workflow runs to see detailed logs
- **Failure notifications**: GitHub will email you if workflows fail

## Data Analysis

### Temperature Differences
The system provides comprehensive temperature comparison:
- **Visual Crossing**: Airport-based data (typically warmer due to heat island effect)
- **Open-Meteo**: Elevation-corrected data (549m, closer to actual location)
- **Expected Range**: 0.5-3°C difference (VC typically higher)
- **Calculation**: Done via Airtable formula for easy adjustment

### Weather Code Mapping
Open-Meteo uses WMO weather codes (0-99):
- `0-3`: Clear to overcast conditions
- `45-48`: Fog conditions  
- `51-67`: Rain and drizzle
- `71-86`: Snow conditions
- `95-99`: Thunderstorms

### Data Quality Indicators
- **Record matching**: Monitor how many OM records match existing VC data
- **API success rates**: Track successful API calls vs failures
- **Temperature variance**: Unusual differences may indicate data quality issues

## API Usage

### Visual Crossing
- **Daily calls**: ~180 API calls
- **Rate limit**: 1000/day
- **Data**: Historical + forecast (45 days total)
- **Cost**: Paid service

### Open-Meteo  
- **Daily calls**: ~4 API calls
- **Rate limit**: None (free tier)
- **Data**: 7-day forecast only
- **Cost**: Free

## Troubleshooting

### Common Issues

**Workflow fails with "422 Unprocessable Entity":**
- Check Airtable field names match exactly
- Verify field types (Number vs Text vs Date)
- Ensure all required OM fields exist in Airtable

**Open-Meteo data missing:**
- Check if OM update ran 30 minutes after VC fetch
- Verify no API errors in workflow logs
- Confirm Visual Crossing data exists first (OM updates existing records)

**Temperature differences seem wrong:**
- Verify both sources are in same units (Celsius)
- Check Airtable formula: `{temp} - {om_temp}`
- Ensure no unit conversion errors

**No recent data:**
- Check GitHub Actions workflow status
- Verify secrets are set correctly
- Look for API key expiration or rate limiting

### Log Analysis
```bash
# View workflow history
GitHub → Actions → Weather Data Fetcher

# Check specific run details
Click on individual workflow run → View logs

# Common success indicators
✅ "Successfully fetched weather data"
✅ "Successfully updated X records with Open-Meteo data"
✅ "Matched X/X OM records with existing VC data"
```

## Development

### Local Testing (Optional)
If you want to test locally:
```bash
# Set up environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file
cp .env.example .env
# Add your API keys to .env

# Test components
python openmeteo_fetcher.py  # Test OM fetcher
python update_openmeteo.py   # Test full OM update
```

### Adding New Data Sources
1. Create new fetcher class (follow `openmeteo_fetcher.py` pattern)
2. Add fields to Airtable schema with prefix (e.g., `source_field_name`)
3. Create update methods in `AirtableAPI` class
4. Add new job to GitHub Actions workflow
5. Update documentation

## System Status

- **Setup Date**: November 23, 2024
- **Open-Meteo Integration**: June 22, 2025
- **Current Status**: ✅ Fully operational
- **Location**: Hensonville, NY (ZIP 12439)
- **Coordinates**: 42.28°N, -74.21°W
- **Elevation**: ~1,972ft actual, 549m (Open-Meteo), various (airports)

## Data Sources Comparison

| Metric | Visual Crossing | Open-Meteo |
|--------|----------------|-------------|
| **Accuracy** | Airport-based (heat island) | Elevation-corrected |
| **Resolution** | ZIP code area | Coordinate-specific |
| **Update Frequency** | 6 hours | 6 hours |
| **Historical Data** | 30 days back | Current + 7 forecast |
| **Forecast** | 15 days ahead | 7 days ahead |
| **Cost** | Paid tier | Free |
| **API Reliability** | Commercial grade | Open source |

## Contributing

This is a personal weather monitoring system. For improvements:
1. Fork the repository
2. Create feature branch
3. Test changes thoroughly
4. Submit pull request with clear description

## License

Private project for personal weather data collection and analysis.

## Support

- **Issues**: Use GitHub Issues for bug reports
- **Documentation**: This README and inline code comments
- **APIs**: Check respective API documentation for service issues
  - [Visual Crossing Docs](https://www.visualcrossing.com/resources/documentation/)
  - [Open-Meteo Docs](https://open-meteo.com/en/docs)
