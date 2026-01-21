# Airtable Automation — Derive Usage Type (3:30am)

## 1. Identity
- Base: appoTbBi5JDuMvJ9D
- Automation name (UI): Derive Usage Type (3:30am)
- Automation type: Scheduled trigger → Run script (code editor)
- Status: ON
- Schedule: Every 1 day at 3:30am (EST)
- Starting (UI): 2026-01-04
- Last verified: 2026-01-08 (local)

## 2. Purpose and scope
### Purpose
Set single-select **{Usage Type}** on the daily **WX** record for a target local day, derived from the thermostat setpoint timeline JSON (authoritative “ON/OFF” semantics), with an additional warm-day bucket based on summed kWh.

### Upstream inputs (reads)
- Table: WX
  - Date identity field (script-configured): `Date`  (see risks below)
  - Reads:
-     `Therm SP Timeline (Derived)` (authoritative for zone ON/OFF)
-     All fields matching `* KWH (Auto)` (summed only for “Enabled, No Heat Needed”)
-     `datetime` (identity match)
    - Usage Type (implicitly, to overwrite)
- `datetime` (identity match)





### Outputs (writes)
- Table: WX
  - Writes:
    - Usage Type (single select: `{ name: <value> }`)

### Contract classification
- Contract-affecting: YES
  - Usage Type is a first-class derived classification used downstream (reporting, derived tables, alerting).

## 3. Trigger
- Trigger type: At a scheduled time
- Schedule: Every day at 3:30am (EST)
- Automation starting date (UI): 2026-01-04
- Condition: Always
- Inputs:
  - Optional `targetDate` (YYYY-MM-DD override)

### Important semantic distinction (start date vs data date)
The automation UI “Starting” date only gates when the automation begins to run.
It does not define which day’s WX record is processed.

The script’s data date rule is:
- `targetDate = cfg.targetDate || yesterday_in_America/New_York`

So, for example:
- Run at 2026-01-05 03:30 EST → targets 2026-01-04 (unless overridden).

## 4. Derivation rules (as implemented)
### Usage types (expected single select options)
- Guests
- Just DC
- All
- Empty House
- Enabled, No Heat Needed
- System Off

### Authoritative ON/OFF source
- `{Therm SP Timeline (Derived)}` JSON:
  ON if any segment sp > 7
  OFF-all-day if all segments sp <= 7 (or no segments)
  - Zones missing entirely from JSON are treated as OFF-all-day (conservative).
  - “System Off” means all zones sp <= 7 all day
  - 
### Rule precedence (in code order)
1) **System Off**
   - All zones OFF-all-day
2) **Enabled, No Heat Needed**
   - Some zone ON (anyZoneOn == true) AND totalKwh <= KWH_EPS (default 0.001)
3) **Guests**
   - Guest Room zone is ON
4) **All**
   - Master ON AND MANC ON
5) **Just DC**
   - Master ON AND MANC OFF
6) **Empty House**
   - Master OFF-all-day AND MANC OFF-all-day
7) Fallback
   - No write; leave Usage Type unchanged

## 5. Steps (action-by-action)
### Step 1 — Run a script (code editor)
- Action type: Run script
- Reads:
  - WX table:
    - Date identity field (configured as `Date`)
    - Therm SP Timeline (Derived)
    - All fields ending ` KWH (Auto)`
    - Usage Type (target field)
- Writes:
  - WX: updateRecordAsync on the matched daily record, setting {Usage Type} to a single-select value.

## 6. Idempotency model
- Intended model: Idempotent overwrite
  - For the selected WX record (targetDate), script deterministically computes Usage Type and overwrites the field.
- Safe to re-run for same targetDate:
  - Yes, outcome is deterministic given the same Therm SP Timeline (Derived) and kWh values.

## 7. Failure modes and observability
### Failure modes (explicit in script)
- No WX record matches targetDate:
  - Logs message and returns without writing.
- Missing Therm SP Timeline (Derived):
  - Logs message and returns without writing.
- Timeline JSON parse failure:
  - Logs message and returns without writing.
- No rule matched:
  - Logs and returns without writing.

### Silent-but-important failure modes (implicit)
- Single select option mismatch:
  - If {Usage Type} select options do not include the computed string, the update may fail at runtime.
- Date field mismatch:
  - If WX’s identity field is not actually named `Date` (e.g., if it is `datetime`), the script will fail to find the daily record and will perform no write.

### Observability
- Airtable automation run history
- Script console logs (via automation run detail)

## 8. Contract touchpoints
- Writes contractual/derived field:
  - WX.{Usage Type}
- Depends on upstream derived field:
  - WX.{Therm SP Timeline (Derived)}
- Depends on upstream energy fields:
  - WX.{* KWH (Auto)} for kWh sum / warm-day classification.

## 9. Risks / required alignment checks
1) **WX date identity field name**
   - This script uses `WX_DATE_FIELD = "Date"`.
   - Your Therm Zone Daily script uses `WX_DATE_FIELD = "datetime"`.
   - If WX does not have both fields consistently populated, this is a high-risk “no-op” failure mode.
   - Resolution is documentation + standardization (no automation changes yet per constraints).

2) **Timezone correctness**
   - Script uses `yyyymmddYesterdayNY()` with Intl for date parts, but then constructs a `-05:00` timestamp for “today midnight”.
   - This can be DST-sensitive. Operationally it is likely acceptable because:
     - The script runs daily at 03:30 local
     - TargetDate can be overridden
   - If DST-perfect behavior becomes required, reuse the UTC-noon anchor pattern used in Therm Zone Daily.

## 10. Evidence
- UI: Scheduled daily 03:30am EST; Starting 2026-01-04; Run script action (code editor)
- Script: stored in `artifacts/derive-usage-type.script.js`
- Trigger/step snapshots: stored as normalized JSON artifacts

## 11. WX record identity

This automation identifies the target WX record using:

- Field: `WX.datetime` (date-only field; no time component)
- Matching method: normalize `WX.datetime` to `YYYY-MM-DD` in `TIME_ZONE` and compare to `targetDate`

This aligns Usage Type derivation with the thermostat pipeline’s canonical daily identity field.

## 12. Target date selection and timezone policy

- Default behavior: if no `targetDate` input variable is provided, the script computes `targetDate = yesterday` in `TIME_ZONE`.
- DST-safe method: “yesterday” is computed using an IANA timezone conversion plus a UTC-noon anchor (avoids DST boundary ambiguity).
- Input overrides:
  - `targetDate` (optional): `YYYY-MM-DD`
  - `TIME_ZONE` (optional): IANA timezone string; defaults to `America/New_York`

## 13. Change log
- 2026-01-08: Initial documentation snapshot (from production automation + script)
- 2026-01-21: Changed ON/OFF semantics from >0/==0 to >7/<=7; script now uses field-id update to avoid field name parse issues.
