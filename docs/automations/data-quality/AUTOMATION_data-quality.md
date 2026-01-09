# Airtable Automation — Data Quality (3:45am)

## 1. Identity
- Base: appoTbBi5JDuMvJ9D
- Automation name (UI): Data Quality (3:45am)
- Automation type: Scheduled trigger → Run script (code editor)
- Status: ON
- Schedule: Every 1 day at 3:45am (EST)
- Starting (UI): 2025-12-19
- Last verified: 2026-01-08 (local)

## 2. Purpose and scope
### Purpose
Compute a daily thermostat data-quality status for a target day and write it into **WX**.

This is an **ACTIVE-ONLY** DQ policy:
- Only zones that were *active* (had Thermostat Events on the target date) are required to have valid kWh Auto values.
- No “expected zones” logic and no expected-vs-auto comparisons.
- If there are zero thermostat events, the script emits WARN (guardrail) and does not assert kWh completeness.

### Upstream inputs (reads)
- Table: WX
  - Identity field (script-configured): `Date` (YYYY-MM-DD after normalization)
  - Reads:
    - Date
    - Per-zone `{Zone} KWH (Auto)` fields (mapping table in script)

- Table: Thermostat Events
  - Reads:
    - Date
    - Thermostat (zone name)

### Outputs (writes) — WX fields
- Therm DQ Status (single select: PASS/WARN/FAIL)
- Therm DQ Score (number 0–100)
- Therm DQ Required Zones (long text)
- Therm DQ Missing Zones (long text)
- Therm DQ Negative Zones (long text)
- Therm DQ Notes (long text)

### Contract classification
- Contract-affecting: YES
  - Therm DQ Status is copied into Therm Zone Daily (Daily explode script) and is a trust signal for downstream interpretation.

## 3. Trigger
- Trigger type: At a scheduled time
- Schedule: Every day at 3:45am (EST)
- Automation starting date (UI): 2025-12-19
- Condition: Always
- Inputs (optional):
  - targetDate (YYYY-MM-DD)

### Important semantic distinction (start date vs data date)
UI “Starting” date gates when the automation begins running.
The data date rule is:
- `targetDate = cfg.targetDate || (yesterday by local system date)`.

Note: this script computes yesterday using `Date.getDate()-1` and local runtime timezone, not explicit IANA TIME_ZONE.

## 4. Zone model and “active-only” semantics
### Zone universe
- ALL_ZONES (enumerated in script):
  - Stairs, LR, Kitchen, Up Bath, MANC, Master, Den,
    Guest Hall, Laundry, Guest Bath, Entryway, Guest Room

### Exclusions
- EXCLUDED_ZONES: Guest Hall
- Excluded zones are never required for DQ even if active.

### Active zones (derived from events)
- A zone is “active” if Thermostat Events has at least one record for targetDate where:
  - Events.Date == targetDate
  - Thermostat (zone) is present and matches ALL_ZONES

### Required zones
- requiredZones = activeZones - EXCLUDED_ZONES

## 5. kWh validation logic
For each zone in requiredZones:
- Map zone → WX field name via ZONE_TO_AUTO_FIELD (must match exactly)
- Read WX kWh value:
  - Missing (null / blank / non-numeric) → missingZones
  - Numeric < 0 → negativeZones
  - Numeric >= 0 → presentZones

If no mapping exists for a required zone:
- COUNT_MISSING_MAPPING_AS_MISSING = true ⇒ count as missing.

## 6. Scoring and status logic
### Score
- Start at 100.
- Subtract:
  - 25 points per missing zone
  - 60 points per negative zone
- Clamp to [0, 100].

### Status
- Default PASS.
- If WARN_IF_NO_EVENTS and eventsCount == 0:
  - status = WARN
  - Notes explain that requiredZones is empty and completeness is not asserted.
- Else if any missingZones or negativeZones:
  - status = FAIL
- Else:
  - status = PASS

## 7. Idempotency model
- Deterministic overwrite of the DQ fields on the WX record for targetDate.
- Safe to re-run for the same day.

## 8. Failure modes and observability
### Hard failures
- WX record not found for targetDate using WX.Date:
  - throws Error and fails the automation run.
- Missing output fields (Therm DQ Status/Score/etc.) in WX schema:
  - runtime exception during update.

### Soft failures / degraded outputs
- If Thermostat Events “Date” field differs in format or timezone, activeZones may be empty and status may become WARN (if eventsCount == 0).

### Observability
- Airtable automation run history
- WX.Therm DQ Notes contains a full structured run report:
  - targetDate, eventsCount, activeZones, requiredZones, present/missing/negative, score, status
- Automation outputs set:
  - targetDate, eventsCount, activeZones, requiredZones, status, score

  - If `WX.datetime` does not exist or is not populated for the target day, the automation fails with “WX record not found for targetDate=...”.


## 9. Contract touchpoints and downstream dependencies
- Writes:
  - WX.Therm DQ Status (used downstream)
- Downstream consumption:
  - Therm Zone Daily upsert copies DQ Status into Therm Zone Daily
  - Any alerting automation based on DQ (e.g., DQ Warn view) may depend on these fields

## 10. Known alignment risks (documented; no changes here)
1) WX identity field mismatch across automations:
   - This script uses WX_DATE_FIELD = "Date"
   - Therm State Changes and Therm Zone Daily use WX_DATE_FIELD = "datetime"
   - If WX does not maintain both fields correctly, DQ may silently operate on a different date identity than other scripts.

2) Timezone mismatch risk:
   - Script computes yesterday using local runtime date arithmetic (no TIME_ZONE / DST-safe anchor).
   - This differs from the UTC-noon anchor used in Therm State Changes / Therm Zone Daily.

## 11. Evidence
- UI: Scheduled daily 03:45am EST; Starting 2025-12-19; Run script action (code editor)
- Script: stored in `artifacts/data-quality.script.js`
- Trigger/step snapshots: stored as normalized JSON artifacts

## 12.  WX record identity

This automation identifies the target WX record using:

- Field: `WX.datetime` (date-only field; no time component)
- Matching method: normalize `WX.datetime` to `YYYY-MM-DD` in `TIME_ZONE` and compare to `targetDate`
- Rationale: `WX.datetime` is the canonical daily identity field for WX and is used by other thermostat-derived automations.

## 13. Target date selection and timezone policy

- Default behavior: if no `targetDate` input variable is provided, the script computes `targetDate = yesterday` in `TIME_ZONE`.
- DST-safe method: “yesterday” is computed using an IANA timezone conversion plus a UTC-noon anchor (avoids DST boundary ambiguity).
- Input overrides:
  - `targetDate` (optional): `YYYY-MM-DD`
  - `TIME_ZONE` (optional): IANA timezone string; defaults to `America/New_York`

## 14. Thermostat Events day matching

- Events are filtered using `Thermostat Events.Date` (`EV_DATE_FIELD = "Date"`).
- Assumption: `Thermostat Events.Date` represents the intended local day aligned to `TIME_ZONE`.
- Note: If event-day mismatches are ever observed around midnight/DST, a more robust approach is to filter by an event timestamp and derive day via `ymdInTZ(timestamp, TIME_ZONE)`.



## 15. Change log
- 2026-01-08: Initial documentation snapshot (from production automation + script)
