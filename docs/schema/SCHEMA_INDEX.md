# Schema Index — Weather Fetcher + Home Assistant Rollups (Airtable WX)

Generated: 2026-01-09T00:19:24Z

## Purpose
This document set defines the **data contracts** for the Albert Court “WX” daily record system:
- Weather ingestion creates and updates daily WX records (including future forecast days).
- Open-Meteo enrichment updates existing WX records (never creates).
- Home Assistant rollups update existing WX records (never create).
- Airtable Automations derive secondary tables/fields (e.g., Therm Zone Daily).

System timezone: **America/New_York**  
Daily grain: **one Airtable WX record per local day**, keyed by `datetime` (date).

## Base and tables
- Airtable Base ID: `appoTbBi5JDuMvJ9D`

Tables in scope:
- **WX** (`tblhUuES8IxQyoBqe`) — daily fact table (weather + heating + indoor environment).
- **Thermostat Events** (`tblvd80WJDrMLCUfm`) — event log of setpoint changes.
- **Therm Zone Daily** (`tbld4NkVaJZMXUDcZ`) — derived per-(Date, Zone) daily facts (Airtable Automation).

## Producer map (authoritative)
### Creates WX records
- **Visual Crossing ingestion** (`weather_fetcher.py`)
  - Creates missing `WX` records for each `datetime` in the ingestion window.
  - Updates existing records only when values differ.

### Updates WX records (never creates)
- **Open-Meteo enrichment** (`openmeteo_fetcher.py` and updater)
  - Writes `om_*` fields; may also write `temp_difference` when VC temp is present.
- **Home Assistant thermostat rollup** (`homeassistant/scripts/thermostat_rollup_write_yesterday.py`)
  - Writes `Thermostat Settings (Auto)`, `Data Source`, and `* KWH (Auto)` zone fields.
- **Home Assistant indoor environment rollup** (`homeassistant/scripts/ha_indoor_env_daily_write_yesterday.py`)
  - Writes HA Indoor Env JSON stats and summaries.

### Derived-only (Airtable Automations)
- **Therm Zone Daily** population and “Derived” fields in WX are produced by Airtable Automations.
  - These are explicitly out of scope for Phase 6.5 schema generation and will be documented separately.

## Contract documents
- `DAILY_DATA_CONTRACT.md` — daily record identity, create/update authority, idempotency.
- `AIRTABLE_WX_SCHEMA.md` — contractual field subset across WX + related tables.
- `WEATHER_INGESTION_SCHEMA.md` — Visual Crossing + Open-Meteo field contracts and horizons.
- `HA_RECORDER_SCHEMA.md` — HA API + HA SQLite recorder DB contracts.

## Change control (global)
Breaking changes require a doc update + review:
- rename/remove any producer-owned field
- change `datetime` identity semantics
- change units for core weather fields (e.g., VC metric → US)
- change rollup window semantics (local midnight boundaries)

Non-breaking:
- additive new fields (document and pin when relied upon)
- additive new entities (document and pin when relied upon)
