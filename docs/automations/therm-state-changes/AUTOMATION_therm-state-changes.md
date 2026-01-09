# Airtable Automation — Therm State Changes (3:15am)

## 1. Identity
- Base: appoTbBi5JDuMvJ9D
- Automation name (UI): Therm State Changes (3:15am)
- Automation type: Scheduled trigger → Run script (code editor)
- Status: ON
- Schedule: Every 1 day at 3:15am (EST)
- Starting (UI): 2026-01-02
- Last verified: 2026-01-08 (local)

## 2. Purpose and scope
### Purpose
Compute daily, timezone-aligned thermostat setpoint state artifacts for a target WX day, based on the Thermostat Events log and WX daily outdoor temperature.

This automation writes the derived thermostat “truth set” into **WX** fields used downstream by:
- Derive Usage Type (3:30am) — reads Therm SP Timeline (Derived)
- Daily explode script (4:15am) — reads Degree-Hours / Setpoint-Hours / Efficiency Index / Source / Changes Count

### Upstream inputs (reads)
- Table: WX
  - Identity field: `datetime` (matched by YYYY-MM-DD in TIME_ZONE)
  - Reads:
    - `datetime`
    - `om_temp` (daily average outdoor temp in °C)

- Table: Thermostat Events
  - Reads:
    - `Timestamp`
    - `New Setpoint`
    - `Thermostat` (preferred zone source)
    - `Name` (fallback zone source)

### Outputs (writes) — WX fields
Writes JSON strings (per-zone maps), plus summary + last run timestamp:

- Therm SP Start (Derived)
- Therm SP End (Derived)
- Therm SP Timeline (Derived)
- Therm SP Setpoint-Hours (Derived)
- Therm SP Degree-Hours (Derived)
- Therm SP Degree-Hours by Setpoint (Derived)
- Therm Efficiency Index (Derived)
- Therm SP Source (Derived)
- Therm SP Changes Count (Derived)
- Therm SP Stale Zones (Derived)
- Therm SP Summary (Derived)
- Therm SP Last Run

### Contract classification
- Contract-affecting: YES
  - Produces the authoritative thermostat state timeline and the derived metrics that other automations/scripts consume.
  - A failure or semantic change here cascades into usage classification and Therm Zone Daily.

## 3. Trigger
- Trigger type: At a scheduled time
- Schedule: Every day at 3:15am (EST)
- Automation starting date (UI): 2026-01-02
- Condition: Always
- Inputs (optional):
  - targetDate (YYYY-MM-DD) — backfill/testing
  - TIME_ZONE (IANA tz; default America/New_York)
  - STALE_HOURS (default 36)
  - MIDNIGHT_GRACE_MINUTES (default 10)
  - EXCLUDED_ZONES (array; default [])

### Important semantic distinction (start date vs data date)
The automation UI “Starting” date only gates when the automation begins to run.
The script’s data date rule is:

- `targetDate = cfg.targetDate || yesterday(TIME_ZONE)`

## 4. Time and identity semantics
- TIME_ZONE default: America/New_York
- Target day boundaries:
  - startOfDayTZ(targetDate) and endOfDayTZ(targetDate) computed as UTC instants corresponding to local midnight…23:59:59.999 in TIME_ZONE.
- WX daily record selection:
  - Iterate WX records; interpret `datetime` as Date or YYYY-MM-DD string; compare YYYY-MM-DD in TIME_ZONE to targetDate.

## 5. Thermostat event normalization
### Zone identity
- Primary: Thermostat Events.{Thermostat} (name)
- Fallback: Thermostat Events.{Name}
- Exclusions:
  - EXCLUDED_ZONES input variable filters out matching zone names.

### Temporal filtering
- Parse Timestamp (Date or ISO string).
- Only include events whose local day (ymdInTZ) is <= targetDate.
- Day-of interest events are those within [dayStart, dayEnd].

### Setpoint parsing
- New Setpoint must be numeric (number or coercible string); non-numeric is dropped.

## 6. Derived outputs (per zone)
For each inferred zone `z`:

### Snapshots
- Start SP:
  - lastBeforeStart.sp if available
  - else first day event’s sp if any
  - else null
- End SP:
  - last event up to dayEnd if available
  - else null

### Timeline (Therm SP Timeline (Derived))
- Construct intervals covering the day where setpoint is known (non-null):
  - “Midnight grace”:
    - If the first event occurs within MIDNIGHT_GRACE_MINUTES after dayStart, treat it as effective at midnight.
  - Otherwise carry forward lastBeforeStart as the starting setpoint when available.
- Interval output objects:
  - `{ from: ISO, to: ISO, sp: number }`

### Setpoint-hours (Therm SP Setpoint-Hours (Derived))
- For each interval:
  - totalHours += duration
  - setpointHours += durationHours * sp
  - hoursBySetpoint[sp] += durationHours
- Stored as:
  - `{ totalHours, setpointHours, hoursBySetpoint }` (rounded to 3 decimals)

### Degree-hours (Therm SP Degree-Hours (Derived))
- Requires WX.om_temp numeric.
- For each interval:
  - delta = max(0, sp - omTempC)
  - degreeHours += delta * durationHours
- Also writes by-setpoint variant:
  - Therm SP Degree-Hours by Setpoint (Derived)

### Efficiency index (Therm Efficiency Index (Derived))
- For each zone:
  - kWh from WX field `{zone} KWH (Auto)` (if exists)
  - efficiencyIndex = kWh / degreeHours when:
    - source != "Stale"
    - kWh != null
    - degreeHours != null and > 0
- Else null.

### Source classification (Therm SP Source (Derived))
- "Observed": at least one event on the target day
- "CarriedForward": no event on day, but prior context exists
- "Stale": no usable recent context OR last event age vs dayEnd exceeds STALE_HOURS
- Stale zones are collected into Therm SP Stale Zones (Derived) (comma-separated)

### Changes count (Therm SP Changes Count (Derived))
- dayZoneEvents.length

## 7. Idempotency model
- Intended model: deterministic overwrite
  - For a given targetDate, recomputes all derived thermostat fields on the WX record and overwrites them.
- Safe to re-run:
  - Yes (no record creation; update-only on one WX record).

## 8. Failure modes and observability
### Hard failures
- No WX record found matching targetDate by `datetime`:
  - script throws Error; automation run fails.
- API/schema mismatch: missing required tables/fields:
  - runtime exception during getTable/getField/updateRecordAsync.

### Soft failures / degraded outputs
- No zones inferred from Thermostat Events:
  - script writes empty JSON objects for all output fields + diagnostic summary; does not throw.
- Missing WX.om_temp:
  - degree-hours become null; efficiency index becomes null; timeline and setpoint-hours still computed.

### Observability
- Airtable automation run history
- Script console logs:
  - “Daily recompute for …”
  - “✓ Updated … record successfully”
- WX summary field:
  - Therm SP Summary (Derived) includes per-zone computed values and diagnostics.

## 9. Contract touchpoints
- Writes derived fields on WX that are prerequisites for:
  - Derive Usage Type (reads Therm SP Timeline (Derived))
  - Therm Zone Daily upsert (reads degree-hours, setpoint-hours, efficiency index, source, changes count)
- Reads Thermostat Events as the raw event log input.

## 10. Evidence
- UI: Scheduled daily 03:15am EST; Starting 2026-01-02; Run script action (code editor)
- Script: stored in `artifacts/therm-state-changes.script.js`
- Trigger/step snapshots: stored as normalized JSON artifacts

## 11. Change log
- 2026-01-08: Initial documentation snapshot (from production automation + script)
