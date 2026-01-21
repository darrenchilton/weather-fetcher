# Airtable Schema Contract — WX + Related Tables

Base: `appoTbBi5JDuMvJ9D`  
Source: Airtable schema probe (authoritative)

This document pins the **contractual subset** required by automated producers. The WX table contains many additional formula/analysis fields that are out of contract unless explicitly listed here.

---

## Table: WX (`tblhUuES8IxQyoBqe`)

### Identity fields (required)
- `datetime` — **date**
  - Daily identity key used by producers (see `DAILY_DATA_CONTRACT.md`).
  Note: `datetime` is the canonical daily identity field used by all thermostat-derived automations,
even though it is stored as a date-only field.


### Producer-owned fields — Visual Crossing weather ingestion
These fields are written by weather ingestion and may be overwritten each run:
- `temp`, `tempmax`, `tempmin` — number
- `feelslike`, `feelslikemax`, `feelslikemin` — number
- `dew`, `humidity` — number
- `precip`, `precipprob`, `precipcover` — number
- `preciptype` — singleLineText
- `snow`, `snowdepth` — number
- `windgust`, `windspeed`, `winddir` — number
- `sealevelpressure` — number
- `cloudcover`, `visibility` — number
- `solarradiation`, `solarenergy`, `uvindex`, `severerisk` — number
- `sunrise`, `sunset` — singleLineText
- `moonphase` — number
- `conditions` — multilineText
- `description` — singleLineText
- `icon` — singleLineText
- `stations` — multilineText

(Additional VC-written fields may exist; add them here if relied upon.)

### Producer-owned fields — Open-Meteo enrichment (update-only)
- `om_temp`, `om_temp_f` — number
- `om_humidity` — number
- `om_pressure` — number
- `om_wind_speed`, `om_wind_speed_mph` — number
- `om_precipitation` — number
- `om_weather_code` — number
- `om_elevation` — number
- `om_data_timestamp` — dateTime
- `om_snowfall`, `om_snowfall_6h`, `om_snow_depth` — number
- `temp_difference` — number (derived compare; see `WEATHER_INGESTION_SCHEMA.md`)

### Producer-owned fields — Home Assistant thermostat rollup (update-only)
- `Thermostat Settings (Auto)` — multilineText
- `Data Source` — singleLineText (expected: `Auto`)
- Per-zone kWh (numbers):
  - `Stairs KWH (Auto)`, `LR KWH (Auto)`, `Kitchen KWH (Auto)`, `Up Bath KWH (Auto)`
  - `MANC KWH (Auto)`, `Master KWH (Auto)`, `Den KWH (Auto)`, `Guest Hall KWH (Auto)`
  - `Laundry KWH (Auto)`, `Guest Bath KWH (Auto)`, `Entryway KWH (Auto)`, `Guest Room KWH (Auto)`
 
#### Per-zone KWH reporting model (authoritative)

For each heating zone, multiple KWH fields may exist to support legacy data,
automation-derived values, and manual correction. Reporting consumers MUST use
the derived `(Reported)` fields defined below.

**Input fields (precedence order):**
1. `{Zone} KWH (Override)` — number  
   - Human-entered correction used for outages, partial data, or known errors.
   - Blank by default.
2. `{Zone} KWH (Auto)` — number  
   - Written by Home Assistant automation.
3. `{Zone} KWH` — number  
   - Legacy manual entry (historical fallback).

**Derived fields (formula):**
- `{Zone} KWH (Reported)` — number  
  - Canonical value for all reporting, charts, exports, and rollups.
  - Resolves precedence: Override → Auto → Manual.
- `{Zone} KWH (Source)` — singleLineText (formula)  
  - One of: `override`, `auto`, `manual`, `no usage`.

**Semantics:**
- `0` is a valid usage value and MUST be preserved.
- Blank indicates absence of data.
- If all three input fields are blank, `{Zone} KWH (Source)` = `no usage`.

**Automation constraints:**
- Automations MUST write only to `{Zone} KWH (Auto)`.
- Automations MUST NOT write to `(Reported)`, `(Source)`, or `(Override)`.


### Producer-owned fields — Home Assistant indoor environment rollup (update-only)
- `HA Indoor Humidity Stats (Auto)` — multilineText (JSON)
- `HA Indoor Temperature Stats (Auto)` — multilineText (JSON)
- `HA Indoor Env Summary (Auto)` — multilineText (JSON)
- `HA Indoor Env Human Summary (Auto)` — multilineText
- `HA Indoor Env Last Run (Auto)` — dateTime

### Human-owned fields (must never be written by automation)
- `Validation Notes (manual)` — multilineText
- Manual KWH fields (examples): `Stairs KWH`, `LR KWH`, `Kitchen KWH`, etc. — number
- Any other manual note fields not explicitly producer-owned.

### Deprecated / legacy fields
- `Thermostat Settings (can delete after automations)` — multilineText
  - Contract status: deprecated (do not write; delete only after confirming no Airtable automations depend on it).

---

## Table: Thermostat Events (`tblvd80WJDrMLCUfm`) — Input contract

Purpose: event log of thermostat setpoint changes.

### Required fields (read by rollups/automations)
- `Thermostat` — singleLineText
- `Timestamp` — dateTime
- `Previous Setpoint` — number
- `New Setpoint` — number
- `WX` — multipleRecordLinks (link to WX daily record)

(Other helper fields exist: `Date`, `Change Type`, `Notes`, etc.)

---

## Table: Therm Zone Daily (`tbld4NkVaJZMXUDcZ`) — Derived-only

Producer: **Airtable Automation** (derived-only; not written by repo scripts in Phase 6.5).

### Identity / linkage
- `Date` — date
- `Zone` — singleSelect
- `Key (Date|Zone)` — formula
- `WX Record` — multipleRecordLinks

### Core derived metrics
- `kWh Auto` — number
- `Degree Hours` — number
- `Setpoint Hours` — number
- `Efficiency Index` — number
- `SP Source` — singleSelect
- `SP Changes Count` — number
- `DQ Status` — singleSelect
- `Usage Type` — singleSelect
- `Rolling 7d EI` — number

---

## Change control (Airtable)
Breaking:
- rename/remove any producer-owned field listed above
- change field types of producer-owned fields
- change/remove `datetime` identity field in WX

Non-breaking:
- additive new fields
- additive formulas/derived outputs (document if relied upon)
