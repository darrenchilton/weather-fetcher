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

### Home Assistant Rollup Execution Model (Credentials & Environment)

Home Assistant rollup scripts (thermostat rollups, indoor environment rollups) **require runtime environment variables** to authenticate against the Home Assistant API.

These variables are:

- `HA_BASE` — Base URL of the Home Assistant API (typically `http://127.0.0.1:8123`)
- `HA_TOKEN` — Long-lived access token used for HA API authentication

**Important:**  
These variables are **not globally available** inside the Home Assistant container.

They are injected **only at execution time**, using one of the following mechanisms:

1. **Production path (normal operation)**  
   Environment variables are injected inline via `shell_command` entries defined in `configuration.yaml`, and executed by Home Assistant automations.

2. **Manual troubleshooting path**  
   Environment variables must be explicitly provided when running scripts via `docker exec` (either inline or via `-e` flags).

Running a rollup script **without** these variables will fail immediately with:


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

### Home Assistant Ingestion Readiness (“I’m Done” Signal)

Because Home Assistant ingestion may run multiple passes overnight, downstream Airtable automations must not assume completion based on time alone.

The WX table includes a readiness guard:

Field: HA Rollup Present? (Formula, numeric 0/1)

IF(
  OR(
    COUNTA({Thermostat Settings (Auto)}) > 0,
    COUNTA({Data Source}) > 0
  ),
  1,
  0
)


Semantics:

1 → Home Assistant has written at least one authoritative artifact for the day

0 → HA ingestion missing or failed

This field is treated as the system’s canonical “HA ingestion complete” signal.

A dedicated Airtable view (ALERT — HA Rollup Missing) filters for:

{datetime} = yesterday (America/New_York)

{HA Rollup Present?} = 0

An automation monitors this view and sends a Slack alert if HA ingestion did not occur.

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

## Thermostat Efficiency Monitoring

This project also supports thermostat efficiency analytics built on Airtable:

- **Therm SP enrichment (06:00 AM local):** derives per-zone setpoint timelines, degree-hours, and an **Efficiency Index** (kWh per degree-hour) and writes results into **WX**.
- **Therm Zone Daily projection (08:00 AM local):** explodes derived per-zone maps into **Therm Zone Daily** (one row per date and zone) for charting and Interfaces.

Dashboards/Interfaces read exclusively from **Therm Zone Daily** (not from JSON fields in WX).

See **architecture_and_runbook.md** for the full technical specification and runbook.

### Daily Thermostat Analytics Schedule (EST)

Thermostat analytics run after Home Assistant ingestion has had time to complete:

Time (EST)	Automation	Description
03:15	Therm State Changes	Build per-zone setpoint timelines and derived metrics
03:30	Derive Usage Type	Classify daily usage context from timelines
03:45	Data Quality	Validate presence and integrity of HA kWh data
04:15	Therm Zone Daily	Explode per-zone daily records

Home Assistant ingestion typically begins around 02:30am and may retry.
The above schedule intentionally prioritizes correctness over immediacy.

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

### Operational Recovery Notes

If a Slack alert indicates missing HA ingestion for yesterday:
Verify Home Assistant ingestion status and logs
Allow HA to complete additional passes if still running
Once {HA Rollup Present?} flips to 1, re-run the following Airtable automations in order:
Therm State Changes
Derive Usage Type
Data Quality
Therm Zone Daily

All thermostat-related automations are idempotent and safe to re-run.

Performance note (future)

Some Airtable automations currently load full tables using selectRecordsAsync().
This is acceptable at current scale but may be optimized with filtered queries or views if table sizes grow materially.

Full details, field contracts, and scripts are documented in:

➡ **architecture_and_runbook.md**

