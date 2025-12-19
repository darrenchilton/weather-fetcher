# WX Table Enrichment System — Technical Specification & Operations Runbook

**Project:** Albert Court Maintenance  
**Scope:** Weather ingestion, Home Assistant energy rollups, and validation monitoring  
**Audience:** Maintainers, operators, future auditors  
**Status:** Authoritative technical reference

“On 2025-12-18, the system transitioned from °F to °C at the HA/MQTT layer. A small number of thermostat events were recorded with mixed units; these were normalized post-hoc. Daily rollups were unaffected because they operate on event counts, not temperature arithmetic.”

---

## 1. System Overview

This system produces **one authoritative daily record per date** in the Airtable **WX** table and incrementally enriches it with:

- Historical and forecast weather data (GitHub Actions)
- Home Assistant–derived thermostat activity summaries
- Per-zone daily energy usage (kWh)
- Ongoing validation and confidence monitoring

The design is explicitly **append-and-enrich**, not transactional. Each producer has clearly defined responsibilities and field ownership.

---

## 2. High-Level Data Flow

```
Mysa thermostats
   ↓ (event-driven telemetry)
mysa2mqtt → MQTT
   ↓
Home Assistant state engine
   ↓
HA recorder (SQLite)
   ↓ (daily snapshot)
Thermostat rollup script
   ↓
Airtable WX table (system of record)
```

Key architectural principle:

> **During the day, data exists only as telemetry in Home Assistant.**  
> **A daily snapshot materializes that telemetry into a durable record.**

---

## 3. Airtable WX Table Contract

### 3.1 Record Identity

- The WX table is keyed by `{datetime}` (date).
- All producers must locate records using:

```
IS_SAME({datetime}, 'YYYY-MM-DD', 'day')
```

### 3.2 Record Creation Rules

- Weather fetchers may create records.
- Home Assistant **never creates records**; it only updates existing ones.

### 3.3 Field Ownership

| Producer | Owned Fields |
|--------|--------------|
| Weather fetchers | Core weather fields (`temp`, `tempmin`, `tempmax`, etc.) |
| Open-Meteo | `om_*` comparative fields |
| Home Assistant | `Thermostat Settings (Auto)`, `<Zone> KWH (Auto)`, monitoring fields |

Overwriting fields owned by another producer is a hard violation.

---

## 4. Home Assistant Telemetry (During the Day)

### 4.1 Update Cadence

- There is **no fixed polling interval**.
- Updates are **event-driven**:
  - Mysa publishes power changes via MQTT
  - Home Assistant updates state immediately

Measured cadence (empirical):
- Median update: ~20–30 seconds when active
- P90: ~2 minutes
- Worst observed gaps: ~4–5 minutes

This cadence is more than sufficient for accurate daily kWh integration.

### 4.2 Where Data Lives During the Day

- Raw power and energy data is stored in the **Home Assistant recorder database** (`home-assistant_v2.db`).
- This database is local to the machine/container.
- Data here is **telemetry**, not a ledger.

Until the daily rollup runs:
- No durable daily kWh exists
- Airtable fields remain blank by design

---

## 5. Daily Rollup (Materialization)

### 5.1 Timing

- Target date: **yesterday (local time)**
- Local timezone: `America/New_York`

Scheduled runs:
- 00:30 local — primary
- 02:00 local — late-event catch-up
- 04:30 local — safety net

### 5.2 kWh Rollup Logic

- Source sensors: `sensor.<zone>_energy_daily`
- For each zone:
  - Query recorder history for the target date
  - Take the **last numeric value** in the window

Missing data handling:
- If no numeric value exists, the field is **not written**
- Zeros are never fabricated

### 5.3 Idempotency

- Each run rebuilds output from source data
- Re-running produces identical results
- Writes overwrite the same WX record deterministically

---

## 6. Weather Normalization (HDD)

### 6.1 Heating Degree Days

The system derives **Heating Degree Days (HDD)** for analysis:

```
HDD (18C) = MAX(0, 18 − {om_temp})
```

- `{om_temp}` = local-area daily average temperature (°C)
- HDD is **derived**, not fetched

HDD is used for **analysis and validation only**, not control logic.

---

## 7. Usage Modes & Intent

The `{Usage Type}` field encodes human intent and drives validation semantics.

Manual energy validation is **not expected** when `{Usage Type}` is one of:
- `Empty: All 13`
- `Empty: Only Kitchen`
- `No Usage`
- `Testing`

A derived formula field expresses this:

```
Manual Expected?
```

This prevents empty-house or testing days from generating false failures.

---

## 8. Monitoring & Validation Framework

The monitoring system is designed to answer one question:

> *Is the automated system behaving consistently enough that manual entry can be retired?*

It explicitly distinguishes:
- Missing data
- Legitimate zero usage
- Structural zone differences (e.g., Kitchen)

### 8.1 Core Monitoring Fields

- `Manual Expected?` — derived from `{Usage Type}`
- `Manual kWh Missing Count` — gated by `Manual Expected?`
- `kWh Comparison Count` — number of zones with both manual + auto data
- `kWh Diff Max Abs` — worst absolute delta
- `kWh Diff Max Abs (No Kitchen)` — same, excluding Kitchen
- `Kitchen kWh Abs Diff`

### 8.2 Kitchen-Specific Tolerance

Kitchen is treated separately due to:
- Open plan
- Adjacent cold zones
- Structural heat loss

Kitchen deviations are penalized only when extreme, using a separate severity band.

---

## 9. Composite Confidence Score

A single numeric score summarizes system health:

```
Therm Confidence Score (0–100)
```

Properties:
- Empty / no-usage days → score = 100
- Requires minimum comparison coverage (≥5 zones)
- Penalizes:
  - Missing expected manual data
  - Low comparison coverage
  - Large non-Kitchen deltas
  - Extreme Kitchen-only deltas

This score is used for **trend analysis**, not alerts.

---

## 9.1 How to Interpret the Confidence Score Over Time

### 9.1.1 What the score means

- The score is a **row-level health summary**. It is most meaningful on days where `{Manual Expected?}=1` and `{kWh Comparison Count}≥5`.
- A score of **100** on empty/no-usage/testing days does **not** mean “perfect measurement”; it means “validation intentionally skipped.”

### 9.1.2 Recommended operational bands

Use these bands for interpretation (not strict pass/fail):

- **90–100 (Green):** System behaving consistently. Differences are within expected tolerance. 
- **75–89 (Yellow):** Acceptable but worth a glance. Often indicates either reduced comparison coverage or one moderate deviation.
- **50–74 (Orange):** Investigate. Typically driven by low coverage, missing expected manual data, or a non-Kitchen deviation.
- **0–49 (Red):** Not a usable validation day (missing manual data when expected) or a major divergence.

### 9.1.3 Trend-based interpretation (the actual goal)

The score is designed to be interpreted over **weeks**, not single days:

- **Stability test:** Scores should cluster within a narrow band on comparable usage types.
- **Drift test:** Watch for gradual degradation (e.g., a rolling average trending down over 2–3 weeks).
- **Repeat offender test:** If low scores correlate to the **same zone(s)** repeatedly (excluding Kitchen), treat that as actionable.

### 9.1.4 Suggested “ready to retire manual entry” criteria

A pragmatic criterion set (tune as desired):

- Consider only days where `{Manual Expected?}=1` and `{kWh Comparison Count}≥5`.
- Over any **rolling 14-day window**:
  - ≥80% of days score **≥85**, and
  - no more than 1 day scores **<75**, and
  - no repeated non-Kitchen FAIL pattern.

When the above holds for **2 consecutive windows**, manual entry is no longer providing new information.

---

## 10. Operational Risk Model

### 10.1 Data Loss Window

The only meaningful risk window is:

> **Recorder DB lost before daily rollup runs**

Mitigations:
- Multiple overnight runs
- Ability to backfill if recorder intact

Once written to Airtable, data is durable and independent of Home Assistant.

### 10.2 Internet vs Power Outage

- Internet outage: no data loss
- Short power outage: no data loss
- Machine failure + recorder loss: potential loss of un-materialized days only

---

## 11. GitHub Roadmap (Planned)

Future evolution (non-urgent):

- HA publishes daily snapshot externally
- GitHub Actions materialize WX records
- HA becomes telemetry producer only

This further reduces local state risk.

---

## 12. System Status

- Daily rollup: stable
- Monitoring: operational
- Validation: in progress
- Manual entry retirement: pending confidence trends

---

**End of document**


