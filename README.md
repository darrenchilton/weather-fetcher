# Weather Fetcher

A Python service that fetches weather data from Visual Crossing Weather API and stores it in Airtable.

## Features
- Fetches 45 days of weather data (30 historical + 15 forecast)
- Runs automatically via GitHub Actions every 6 hours
- Comprehensive logging and error handling
- Handles API rate limits and batch processing
- Deduplicates and updates existing records

## Setup

### GitHub Actions Setup
1. Go to your repository Settings → Secrets and variables → Actions
2. Add the following repository secrets:
   - `WEATHER_API_KEY`: Your Visual Crossing API key
   - `AIRTABLE_API_KEY`: Your Airtable API key  
   - `AIRTABLE_BASE_ID`: Your Airtable base ID

## Usage

### Automatic Execution
The GitHub Action runs automatically every 6 hours. You can also trigger it manually:
1. Go to the Actions tab in your repository
2. Select "Weather Data Fetcher" workflow
3. Click "Run workflow"

## API Usage
- Visual Crossing Weather API
- ~180 API calls daily (4 runs × 45 days)
- 1000/day limit
- Fetches data for ZIP code 12439
