# Weather Fetcher

A comprehensive Python weather service that fetches data from multiple sources and stores it in Airtable for analysis and comparison.

## Features

### Core Weather Data (Visual Crossing)

* Fetches 45 days of weather data (30 historical + 15 forecast)
* Runs every 6 hours via GitHub Actions
* Handles API rate limits and batch processing
* Deduplicates and updates existing records

### Comparative Weather Data (Open-Meteo)

* Elevation-corrected weather data (549m vs airport data)
* 7-day forecast with daily aggregates from hourly data
* Automatic temperature and weather parameter updates
* Independent update process for data comparison

## Data Sources

| Source          | API         | Location             | Elevation        | Update Frequency | Cost |
| --------------- | ----------- | -------------------- | ---------------- | ---------------- | ---- |
| Visual Crossing | Weather API | ZIP 12439 (airports) | Various airports | Every 6 hours    | Paid |
| Open-Meteo      | Free API    | 42.28°N, -74.21°W    | 549m (1,801ft)   | Every 6 hours    | Free |

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
├── homeassistant/               # Home Assistant WX enrichers (Phase 7)
│   ├── scripts/
│   │   └── thermostat_rollup_write_yesterday.py
│   └── README.md
└── README.md                    # This file
```

## Automation

### GitHub Actions Workflow

* **Visual Crossing**: Every 6 hours at :00 (00:00, 06:00, 12:00, 18:00 UTC)
* **Open-Meteo**: Every 6 hours at :30 (00:30, 06:30, 12:30, 18:30 UTC)
* **Manual triggers**: Available via GitHub Actions interface

### Data Flow

1. Visual Crossing fetches core weather data
2. 30 minutes later, Open-Meteo updates existing records with additional parameters
3. Temperature differences calculated via Airtable formula

## Additional WX Producers — Home Assistant

In addition to the weather ingestion pipelines (Visual Crossing and Open-Meteo), the **WX table is also enriched by Home Assistant automations**.

Home Assistant updates **existing daily WX records** (keyed by `{datetime}`) with:

- `Thermostat Settings (Auto)` — daily thermostat event rollups
- `<Zone> KWH (Auto)` — per-zone daily energy usage
- `Data Source = Auto` — marker indicating automated HA writes

### Key rules

- Home Assistant **never creates WX records**.
- Records are selected using:
  ```
  IS_SAME({datetime}, 'YYYY-MM-DD', 'day')
  ```
- Field ownership is respected:
  - Weather fetchers write weather + `om_*` fields
  - Home Assistant writes thermostat and kWh fields only

Implementation details live in [`homeassistant/`](homeassistant/).

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

* `datetime` (Date) - Primary date field for record matching
* `temp`, `tempmax`, `tempmin` (Number, 1 decimal) - Temperature data in Celsius
* `humidity`, `pressure`, `windspeed` (Number, 1 decimal) - Weather parameters
* `precip` (Number, 2 decimal) - Precipitation data
* `conditions`, `description` (Single line text) - Weather descriptions
* `Loc` (Single line text) - Location identifier

**Open-Meteo Fields (added):**

* `om_temp` (Number, 1 decimal)
* `om_temp_f` (Number, 1 decimal)
* `om_humidity` (Number, 1 decimal)
* `om_pressure` (Number, 1 decimal)
* `om_wind_speed` (Number, 1 decimal)
* `om_wind_speed_mph` (Number, 1 decimal)
* `om_weather_code` (Number, integer)
* `om_elevation` (Number, integer)
* `om_precipitation` (Number, 2 decimal)
* `om_data_timestamp` (Date)

**Temperature Comparison (calculated in Airtable):**

* `temp_diff_celsius` (Formula) - `{temp} - {om_temp}`

## System Status

* **Current Status**: ✅ Fully operational
* **Location**: Hensonville, NY (ZIP 12439)

* ## Thermostat Analytics (Setpoint Timeline & Efficiency)

In addition to weather ingestion and Home Assistant rollups, the **WX table also serves as the computation surface for daily thermostat analytics**.

These analytics are implemented as **Airtable Automations**, not external services.

### What is computed

For each WX date:

- Effective thermostat **setpoint timeline** per zone
- **Setpoint-hours** and **degree-hours** (vs `{om_temp}`)
- Per-zone **heater efficiency index** (kWh / °C·hr)
- Provenance flags (Observed / CarriedForward / Stale)
- Human-readable daily summary

### How it runs

Two Airtable automations exist:

1. **Manual recompute**
   - Triggered by a checkbox on the WX record
   - Used for validation and backfills

2. **Daily scheduled recompute**
   - Runs each morning
   - Computes **yesterday (America/New_York)**
   - Updates the existing WX record for that date

### Design principles

- WX records are **never created** by thermostat analytics
- Weather ingestion and thermostat analytics are **decoupled**
- All thermostat math is **timeline-based**, not snapshot-based
- JSON fields are used for per-zone outputs; no formulas are required

Full details, field contracts, and scripts are documented in:

➡ **architecture_and_runbook.md**

