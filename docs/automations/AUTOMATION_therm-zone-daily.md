# Airtable Automation — Therm Zone Daily (Daily explode script 4:15am)

## 1. Identity
- Base: appoTbBi5JDuMvJ9D
- Automation name (UI): Daily explode script (4:15 am)
- Canonical doc name: Therm Zone Daily — Daily Upsert
- Automation type: Scheduled trigger → Run script (code editor)
- Status: ON
- Schedule: Every 1 day at 4:15am EST
- Start date: 2025-12-16
- Last verified: 2026-01-08 (local)

## 2. Purpose and scope
### Purpose
Daily, timezone-aligned **upsert** into **Therm Zone Daily**: create/update one record per (Zone × Local Day),
sourced from the **WX** daily fact record and its derived thermostat rollup JSON blobs.

### Upstream inputs (reads)
- Table: WX
  - Identity field: `datetime` (interpreted in TIME_ZONE; matched by YYYY-MM-DD)
  - Reads:
    - Therm DQ Status
    - Usage Type
    - Therm SP Degree-Hours (Derived)  (JSON map keyed by zone)
    - Therm SP Setpoint-Hours (Derived) (JSON map keyed by zone)
    - Therm Efficiency Index (Derived)  (JSON map keyed by zone)
    - Therm SP Source (Derived)         (JSON map keyed by zone)
    - Therm SP Changes Count (Derived)  (JSON map keyed by zone)
    - Per-zone energy: `{zone} KWH (Auto)` for each zone in ZONES

### Outputs (writes)
- Table: Therm Zone Daily
  - Writes/upserts per zone:
    - Date
    - Zone (single select)
    - WX Record (link to WX)
    - kWh Auto
    - Degree Hours
    - Setpoint Hours
    - Efficiency Index
    - SP Source (single select)
    - SP Changes Count
    - DQ Status (single select)
    - Usage Type (single select)

### Contract classification
- Contract-affecting: YES
  - This automation is the sole writer of the derived table `Therm Zone Daily` (tbld4NkVaJZMXUDcZ).

## 3. Trigger

- Trigger type: At a scheduled time
- Schedule: Every day at 4:15am (EST)
- Automation start date (UI): 2025-12-16
- Condition: Always

### Important semantic distinction

The automation UI `startDate` **does not define the data date** processed.

Data date selection is entirely controlled by the script:

- Default behavior:
  - Process **yesterday**, computed in `TIME_ZONE`
- Script logic:
  ```js
  const targetYmd = override || yesterdayYMD(TIME_ZONE);


## 4. Time and identity semantics
- TIME_ZONE default: America/New_York
- Target date default: “yesterday” computed in TIME_ZONE using a UTC-noon anchor to avoid DST edge cases.
- WX record match:
  - Iterate WX records; interpret `datetime` as Date or string
  - Compare `YYYY-MM-DD` in TIME_ZONE to target date
- Therm Zone Daily identity key:
  - `(YYYY-MM-DD in TIME_ZONE) + Zone`
  - Implemented by scanning existing Therm Zone Daily rows and building a map of `YYYY-MM-DD|Zone → recordId`.

## 5. Steps (action-by-action)
### Step 1 — Run a script (code editor)
- Action type: Run script
- Reads:
  - WX table fields listed above
  - Therm Zone Daily fields (Date, Zone) to build the upsert index
- Writes:
  - Therm Zone Daily: batch create/update (50 per chunk)
- Deterministic behavior:
  - For each of 12 zones, exactly one create or one update is attempted.

## 6. Writes and data mapping
### Target: Therm Zone Daily (tbld4NkVaJZMXUDcZ)
Record identity concept: `(Zone, Local Day)`

Mapping (per zone):
- Date:
  - Written as UTC noon of targetYmd (Date.UTC(y,m,d,12,0,0)) to avoid timezone shifting.
- Zone:
  - Single select `{ name: zone }`
- WX Record:
  - Link field `[{ id: wxRecord.id }]`
- kWh Auto:
  - Source: WX field `{zone} KWH (Auto)` (number)
- Degree Hours / Setpoint Hours / Efficiency Index / SP Source / SP Changes Count:
  - Source: JSON maps stored in WX derived fields, keyed by zone name.
- DQ Status:
  - Source: WX “Therm DQ Status” (as string → single select name)
- Usage Type:
  - Source: WX “Usage Type” (as string → single select name)

## 7. Idempotency model
- Intended model: Upsert
  - If Therm Zone Daily record exists for key `YYYY-MM-DD|Zone`, update it.
  - Else create it.
- Re-running for the same day is safe:
  - Updates overwrite the same field set deterministically.
- Notes:
  - The script does not delete records (safe).
  - The script assumes Zone values are stable and match the ZONES constant exactly.

## 8. Failure modes and observability
### Failure modes
- No WX record found for target date:
  - Script throws hard error: `No WX record found where "datetime" matches YYYY-MM-DD`.
  - Impact: Therm Zone Daily for that day not updated.
- Zone mismatch:
  - If Therm Zone Daily Zone select names differ from ZONES strings, creates/updates may fail.
- Missing derived JSON blobs:
  - safeParseJsonCell returns `{}`; outputs become nulls rather than crashing.
- Missing per-zone KWH fields:
  - `getCellValue` returns null; written as null.
- Select option mismatch:
  - If select options for Zone / SP Source / DQ Status / Usage Type don’t include the value, Airtable may reject that write.

### Observability
- Automation run history in Airtable (native)
- Script outputs:
  - TIME_ZONE
  - targetDate
  - created count
  - updated count

## 9. Contract touchpoints
- Writes to derived table:
  - Therm Zone Daily (tbld4NkVaJZMXUDcZ)
- Reads contractual fields from WX:
  - datetime, Usage Type, Therm DQ Status, and specific derived thermostat JSON fields.

## 10. Evidence
- Script: stored in this document and mirrored to artifacts (below)
- UI details captured via screenshots (schedule + run script + startDate)

## 11. Change log
- 2026-01-08: Initial documentation snapshot (from production automation + script)
