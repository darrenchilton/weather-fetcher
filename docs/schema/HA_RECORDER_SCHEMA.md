# Home Assistant Recorder Schema Contract

## Purpose
Define HA-side inputs relied on by update-only rollups into Airtable WX.

## Recorder policy (contract)

As of **2026-02-05**, Home Assistant recorder is intentionally scoped to reduce SQLite write load and keep the downstream Airtable rollups stable.

### Recorder configuration (authoritative)

```yaml
recorder:
  purge_keep_days: 7
  commit_interval: 60

  exclude:
    domains:
      - climate

  include:
    domains:
      - sensor

    entity_globs:
      - sensor.*_current_power
      - sensor.*_current_temperature
      - sensor.*_current_humidity

What is guaranteed to be recorded

Only these high-value telemetry sensors are guaranteed to be recorded long-term:

sensor.*_current_power

sensor.*_current_temperature

sensor.*_current_humidity

What is intentionally not recorded

climate.* is explicitly excluded. (The system relies on sensor telemetry; climate history is not required for energy rollups.)

Recorder validation (authoritative checks)

Last event/state timestamps (recorder alive):

SELECT
  (SELECT datetime(MAX(time_fired_ts),'unixepoch','localtime') FROM events) AS last_event,
  (SELECT datetime(MAX(last_updated_ts),'unixepoch','localtime') FROM states) AS last_state;


Domain write load in last 10 minutes (diagnostic):

SELECT substr(sm.entity_id,1,instr(sm.entity_id,'.')-1) AS domain,
       COUNT(*) AS writes
FROM states s
JOIN states_meta sm ON s.metadata_id = sm.metadata_id
WHERE s.last_updated_ts > (strftime('%s','now') - 600)
GROUP BY domain
ORDER BY writes DESC;


Authoritative climate exclusion check (since last HA start):

WITH start AS (
  SELECT MAX(time_fired_ts) AS t0
  FROM events e
  JOIN event_types et ON e.event_type_id = et.event_type_id
  WHERE et.event_type = 'homeassistant_start'
)
SELECT
  (SELECT datetime(t0,'unixepoch','localtime') FROM start) AS ha_start_local,
  (SELECT COUNT(*)
   FROM states s
   JOIN states_meta sm ON s.metadata_id = sm.metadata_id
   WHERE substr(sm.entity_id,1,instr(sm.entity_id,'.')-1)='climate'
     AND s.last_updated_ts >= (SELECT t0 FROM start)
  ) AS climate_rows_since_start;


Expected: climate_rows_since_start = 0.

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
