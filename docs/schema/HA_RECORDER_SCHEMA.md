# Home Assistant Recorder Schema Contract

## Purpose
Define HA-side inputs relied on by update-only rollups into Airtable WX.

---

## Environment assumptions
- HA runs in Docker on macOS
- Host config mount: `/Users/plex/homeassistant/config` → `/config` in container
- Rollups execute inside the HA container
- Required env vars at runtime:
  - `HA_BASE` (e.g., `http://127.0.0.1:8123`)
  - `HA_TOKEN`

---

## Indoor Environment Rollup (HA HTTP API)

### Script
- `homeassistant/scripts/ha_indoor_env_daily_write_yesterday.py`

### Endpoints
- `GET /api/states` — discovery of entities matching:
  - `sensor.*_current_temperature`
  - `sensor.*_current_humidity`
- `GET /api/history/period/{start_time}`
  - params include:
    - `end_time=...`
    - `filter_entity_id=...`
    - `minimal_response=1`
    - `no_attributes=1`

### Window semantics
- Local day (America/New_York) midnight → next midnight
- Converted to UTC for HA history calls (DST-safe conversion required)

### Output contract (to WX)
Writes:
- `HA Indoor Humidity Stats (Auto)` (JSON)
- `HA Indoor Temperature Stats (Auto)` (JSON)
- `HA Indoor Env Summary (Auto)` (JSON)
- `HA Indoor Env Human Summary (Auto)` (text)
- `HA Indoor Env Last Run (Auto)` (dateTime)

JSON keys (as implemented):
- stats JSON: `date_local`, `generated_utc`, `entities` (per-entity samples/min/max/avg/unit)
- summary JSON: `date_local`, `generated_utc`, `humidity_avg`, `temperature_avg`, `counts`, `min_samples`, `warnings`

---

## Thermostat Rollup (HA SQLite recorder DB + Airtable events)

### Script
- `homeassistant/scripts/thermostat_rollup_write_yesterday.py`

### HA recorder DB (SQLite)
- Path: `/config/home-assistant_v2.db`
- Tables used:
  - `states_meta` (entity_id → metadata_id)
  - `states` (states over time; uses last_updated_ts)

### Entity contract
Reads daily energy entities:
- `sensor.<zone>_energy_daily` for each zone pinned in the script’s zone map.

### Airtable input dependency
Reads Thermostat Events table (Airtable):
- `Thermostat` (singleLineText)
- `Timestamp` (dateTime)
- `Previous Setpoint` (number)
- `New Setpoint` (number)

### Output contract (to WX)
Writes:
- `Thermostat Settings (Auto)` (text summary)
- `Data Source = Auto`
- per-zone: `* KWH (Auto)` numeric fields

### Write mode
- Defaults to dry-run unless `WRITE_WX=1` is set.

---

## Change control
Breaking:
- renaming entity IDs used by rollups without updating zone maps/discovery rules
- changing daily window semantics
- changing HA history response mode (minimal_response/no_attributes) if code relies on it
