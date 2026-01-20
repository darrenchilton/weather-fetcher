Incident Report — Thermostat Telemetry & Recorder Outage

Incident ID: 2026-01-20-mysa-recorder
Date (Local): 2026-01-19 → 2026-01-20
Timezone: America/New_York
Severity: Data loss (thermostat telemetry only)
Status: Resolved

Summary

Daily thermostat rollups reported events_fetched: 0 and missing kWh for all zones.
Investigation confirmed a mysa2mqtt ingestion outage caused by an invalid .env file, compounded by Home Assistant recorder history being unavailable for backfill. The recorder database was reset to reclaim disk space and restore stability.

2026-01-19: fully missing thermostat data

2026-01-20: partially missing (midnight → ~08:07 local); valid data thereafter

Impact

No thermostat state history recorded during the outage window.

Daily kWh rollups missing for all zones on 2026-01-19.

Partial-day data on 2026-01-20 (pre-restart window missing).

No impact to non-thermostat entities after recorder reset.

Analytics system of record (Airtable) preserved prior rollups.

Root Cause
Primary

mysa2mqtt container failed to start due to an invalid environment variable line in the .env file:

vi /Users/plex/mysa2mqtt/.env


Docker rejects env files with invalid keys/whitespace:

docker: invalid env file: variable contains whitespaces


Result: no MQTT publishes from Mysa devices → no HA state updates.

Secondary / Compounding

Home Assistant recorder history was not usable for backfill and disk pressure necessitated a reset. (History loss accepted because Airtable is the analytics system of record.)

Detection

Daily rollup anomaly: events_fetched: 0

All zones reported missing kWh

Verification showed MQTT topics absent during outage; later confirmed present after fix

Timeline (Local)

Before 2026-01-19: System operating normally

2026-01-19 (all day): mysa2mqtt not running → no thermostat telemetry

2026-01-20 ~08:07:

.env corrected

mysa2mqtt restarted

Home Assistant restarted

Recorder DB reset (history wiped)

Post-08:07: Thermostat entities resumed recording; verified via recent state rows

Recovery Actions

Ingestion Fix

Cleaned /Users/plex/mysa2mqtt/.env to valid KEY=VALUE entries only.

Restarted mysa2mqtt.

Verified MQTT publishing on mysa2mqtt/# (temperature, humidity, power, climate state, discovery topics).

Recorder Reset

Stopped Home Assistant.

Deleted recorder DB to reclaim disk space:

home-assistant_v2.db
home-assistant_v2.db-wal
home-assistant_v2.db-shm


Restarted Home Assistant (fresh DB created).

Verification

Confirmed recorder health via states → states_meta join.

Verified LR thermostat entities recorded within minutes post-restart:

sensor.lr_energy

sensor.lr_energy_daily

sensor.lr_current_temperature

sensor.lr_current_power

sensor.lr_current_humidity

Data Accounting

2026-01-19:

data_completeness = missing

missing_reason = mysa2mqtt outage (invalid .env)

2026-01-20:

data_completeness = partial

missing_window_local = 00:00 → ~08:07

missing_reason = mysa2mqtt outage + HA recorder reset

No attempt was made to fabricate or backfill missing kWh.

Prevention & Follow-ups
Immediate (Low Effort)

Add .env linting before starting mysa2mqtt (reject non-KEY=VALUE lines).

Add a watchdog alert if no thermostat power/temperature updates are seen for N minutes.

Add rollup guardrail: auto-flag ingestion outage if events_fetched = 0 across zones.

Medium Term

Consider migrating HA recorder to MariaDB/Postgres to reduce SQLite fragility under disk pressure and long runtimes.

Lessons Learned

Container env files fail hard on malformed lines; add validation.

Recorder schema requires joining states → states_meta; avoid querying states.entity_id directly.

Treat analytics (Airtable) as the source of truth; do not backfill fabricated data.

Prepared by:
Darren Chilton
Prepared on: 2026-01-20
