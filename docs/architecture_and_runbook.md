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

### 5.4 Daily Setpoint Baseline Rollup (Therm SP)

5.4.1 Purpose

In addition to daily kWh rollups, the system materializes a per-zone thermostat setpoint baseline for each day. This enables later analysis that incorporates both energy usage and setpoint intent (e.g., “higher energy because setpoints were higher”), without treating setpoint change frequency as a correctness signal.

This process is explicitly non-alerting and does not affect DQ.

### 5.4.2 Output Model (script-owned fields in WX)

The setpoint rollup writes the following script-owned fields on the target WX record:

{Therm SP Start (Derived)} — JSON map: zone → setpoint at start of day

{Therm SP End (Derived)} — JSON map: zone → setpoint at end of day

{Therm SP Source (Derived)} — JSON map: zone → Observed | CarriedForward | Stale

{Therm SP Changes Count (Derived)} — JSON map: zone → count of setpoint-bearing events during the day

{Therm SP Stale Zones (Derived)} — comma-separated list of zones considered stale

{Therm SP Summary (Derived)} — human-readable diagnostic summary (includes counters)

{Therm SP Last Run} — timestamp of the most recent run

These fields are owned exclusively by the Therm SP script and must not be written by other producers.

### 5.4.3 Data Sources and Semantics

Source table: Thermostat Events

Canonical event time field: {Timestamp} (date/time)

Canonical setpoint field: {New Setpoint} (number)

Zone identity: {Thermostat} (preferred; typically linked record name), fallback {Name} (text)

Semantics:

“Start setpoint” is the last known setpoint before local day start; if none exists, it uses the first setpoint event on that day.

“End setpoint” is the last known setpoint on or before local day end.

If no setpoint event occurred on the day but prior history exists, the day is tagged CarriedForward.

If the last known setpoint is older than the staleness threshold, the zone is tagged Stale.

Staleness threshold:

Default: 36 hours (configurable in the automation script)

Exclusions:

EXCLUDED_ZONES can be provided to exclude zones from all Therm SP computations.

### 5.4.4 Automation Trigger and Targeting

Steady-state (production): a scheduled Airtable automation runs each morning and updates yesterday’s WX record.

Trigger: Scheduled (daily), after overnight telemetry/rollups are complete

Target day: yesterday (local timezone: America/New_York)

Record selection: find the WX row whose {datetime} matches the target day (day-level match)

Historical backfill (one-time / occasional): a separate manual workflow may be used to backfill older WX records. After backfill is complete, the scheduled automation is the authoritative mechanism.

Operational guidance:

The daily scheduled Therm SP run is safe to re-run; it is deterministic and overwrites the same derived fields for the target day.

### 5.4.5 Relationship to Energy Rollups and Validation

Therm SP provides setpoint context for later analysis of energy efficiency and behavior.

Therm SP is not used for DQ alerting and does not imply correctness or incorrectness of energy measurements.

Validation (Manual vs Auto energy comparisons) remains semantically separate from Therm SP.

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

## 6.2 Interpreting Daily Heating Numbers (Plain-English Guide)

The system produces daily summaries that may look like:
https://airtable.com/appoTbBi5JDuMvJ9D/tblhUuES8IxQyoBqe/viwNTndUN0mEuam91?blocks=hide
view: Zone Efficiency

2025-12-18 | 7 | 103 | 9


These values are descriptive, not judgments. They are intended to help a human understand what kind of day it was, not whether the system performed well or poorly.

What each number means

Heating Demand (HDD = 7)
This reflects how cold the day was.
A higher number means the house needed more heating; a lower number means it was mild.

Total Heating Energy (103 kWh)
This is how much energy the heating system actually used across the whole house that day.

Zones Active (9)
This is how many areas of the house were heated at least somewhat that day.

How to read the combination

In plain terms, this row says:

“On a moderately cold day, most of the house was heated, and the system used a moderate amount of energy to do so.”

This is not a score and not an efficiency rating. It is simply a factual snapshot of demand, response, and scale.

What a single day does not tell you

It does not indicate inefficiency

It does not indicate degradation

It does not require action

Single days are inherently noisy. Meaning emerges only when similar days are compared over time.

Intended use

These summaries support pattern recognition, comparison between similar weather days, and gradual trend awareness. Operational correctness is handled separately by the Data Quality (DQ) gate.

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

## 8.3 Thermostat Data Quality Gate (Active-Only)
8.3.1 Purpose

The Thermostat Data Quality (DQ) Gate provides a binary operational health signal (PASS / FAIL / WARN) answering one question only:

Given the zones that were actually active on a given day, did the automated system produce valid kWh data for those zones?

This gate is intentionally orthogonal to the comparative validation and confidence scoring framework. It does not compare against manual or modeled expectations and does not attempt to judge energy reasonableness.

It exists to:

Detect missing or corrupt automated data

Eliminate false failures caused by unused zones

Provide a clean alerting signal for automation reliability

8.3.2 Design Principles

The DQ gate follows these rules:

Active-only expectation
A zone is expected to produce kWh data only if it was active, where “active” is defined as:

At least one thermostat event recorded for that zone on the target date

Evidence-based requirement
Expectations are derived from the Thermostat Events table, not static configuration or assumptions.

Zero is valid, blank is not

0.0 kWh is a legitimate outcome

Blank/null kWh indicates a data pipeline failure for required zones

No model comparison
The DQ gate does not consider:

“Just DC” values

Manual entries

Expected vs actual differences

Kitchen-specific tolerances

Explicit guardrail for missing telemetry
If no thermostat events exist for the day, the system emits WARN, not PASS, to avoid masking upstream event-logging failures.

8.3.3 Implementation Mechanism

The DQ gate is implemented as an Airtable Automation Script, scheduled once daily (typically early morning, after all overnight rollups have completed).

Inputs

Target date (default: yesterday, local time)

WX table daily record

Thermostat Events table records for the target date

Outputs (written to WX table)

Therm DQ Status — PASS, FAIL, or WARN

Therm DQ Score — numeric (0–100), derived mechanically from findings

Therm DQ Required Zones — zones inferred as required

Therm DQ Missing Zones — required zones with missing kWh

Therm DQ Negative Zones — required zones with invalid negative kWh

Therm DQ Notes — structured diagnostic summary

These fields are script-owned and must not be written by other producers.

8.3.4 Required Zone Derivation

For a given target date:

Collect all thermostat events with Date == targetDate

Extract the unique set of zones referenced by those events

Remove zones explicitly excluded from DQ enforcement (e.g., Guest Hall)

The remaining set becomes requiredZones

There is no static “always required” list in the active-only model.

8.3.5 Validation Rules

For each zone in requiredZones:

Missing:
Auto kWh field is blank or non-numeric → FAIL

Invalid:
Auto kWh < 0 → FAIL

Zones not in requiredZones are ignored entirely for DQ purposes.

8.3.6 Status Semantics
Status	Meaning
PASS	All required zones have valid (≥0) Auto kWh
FAIL	At least one required zone has missing or negative Auto kWh
WARN	No thermostat events found; DQ expectations cannot be inferred

A WARN day indicates telemetry ambiguity, not confirmed correctness.

8.3.6.1 Interpreting WARN on Unoccupied Days

A WARN status is emitted when no thermostat events are recorded for the target date, because the system cannot infer which zones were required.

This condition has two distinct real-world causes:

Telemetry ambiguity
An upstream logging or ingestion failure may have prevented thermostat events from being recorded.

Expected inactivity (unoccupied house)
The house was unoccupied and no thermostat setpoints or states changed during the day.

In the second case, a WARN is expected and benign.

Operational guidance:

If {Usage Type} indicates an unoccupied or low-interaction day (e.g., Empty: Only Kitchen, Empty: All, No Usage),
a DQ WARN due to zero events requires no action.

If WARN occurs on days where thermostat interaction was expected, investigate event ingestion.

This guardrail exists to avoid falsely emitting PASS when event telemetry is missing, not to signal data corruption.

8.3.7 Relationship to Confidence Score

The DQ gate and the Therm Confidence Score serve different roles:

Aspect	DQ Gate	Confidence Score
Purpose	Operational health	Analytical validation
Scope	Auto data only	Auto vs manual/model
Output	PASS / FAIL / WARN	0–100 score
Driver	Evidence (events)	Coverage + deviation
Alerting	Yes	No

A day may:

PASS DQ but have a low Confidence Score (model mismatch)

FAIL DQ even when confidence scoring is skipped

This separation is intentional and required.

8.3.8 Operational Use

Alerts should be driven exclusively by Therm DQ Status

Investigations start with Therm DQ Notes

Trend analysis continues to use the Confidence Score framework

Manual energy entry retirement decisions must rely on confidence trends, not DQ status.

8.3.9 Rationale for Active-Only Design

The active-only approach was selected because:

Not all zones are occupied daily

Off days legitimately produce zero or no activity

Static “expected zones” caused repeated false failures

Thermostat events provide objective evidence of intent to heat

This design ensures the DQ signal reflects system correctness, not household behavior.

## 8.4 Manual vs Auto Energy Semantics (Validation Context)
8.4.1 Purpose

This section documents a confirmed semantic distinction between manual energy values sourced from the Mysa app and automated energy values sourced from Home Assistant (HA). It exists to prevent misinterpretation of Validation outcomes and to clarify why numerical mismatches do not undermine system correctness or long-term efficiency monitoring.

8.4.2 Dual reporting in the Mysa app

For the same zone and day, the Mysa app reports two different kWh values, depending on UI context:

Zone Detail view (device-level)

Energy measured directly by the thermostat device.

Example: Entryway → Energy Total = 11.59 kWh (Dec 18, 2025)

Home → Breakdown view (allocation-level)

Mysa’s internally allocated per-zone energy.

Designed to sum cleanly to the home total.

Example: Albert CT → Entryway = 10.33 kWh (Dec 18, 2025)

These values are both valid within Mysa but represent different semantic quantities.

8.4.3 Definition of “Manual” in this system

Historically and by design, this system defines:

Manual kWh = Mysa Home → Breakdown view value

This choice reflects historical practice and ensures consistency across zones for a given day. Device-level Mysa values are not used as the manual baseline.

8.4.4 Implications for Validation results

Validation compares:

HA Auto (device-grounded energy measurement)

Manual (Mysa Home-level allocation)

Disagreements between these values indicate semantic differences between measurement models, not pipeline failures or data quality issues.

Accordingly:

Validation WARN/FAIL does not imply incorrect Auto data.

Data Quality (DQ) remains the sole indicator of pipeline health.

8.4.5 Relevance to system goals

The system’s primary objective is trend-based detection of efficiency degradation, not financial reconciliation.

For this objective:

Absolute daily agreement is unnecessary.

Stability and internal consistency of Auto measurements are paramount.

HA Auto values are therefore treated as authoritative for longitudinal analysis, even when they diverge from Mysa’s allocation-layer reporting.

8.4.6 Operational guidance

Do not tune Auto values to match Mysa Breakdown allocations.

Interpret Validation outcomes as context about manual-reference reliability.

Base operational decisions on trends over time, not single-day Validation results.

8.4.7 Interpreting Validation WARN and FAIL Statuses

The Thermostat Validation process compares Auto kWh (device-grounded measurement) against Manual kWh (Mysa Home-level allocation) for zones that are expected on a given day.

As a result:

A Validation WARN or FAIL does not indicate a data pipeline failure.

It does not imply incorrect automated measurements.

It reflects a semantic mismatch between two independently derived representations of energy usage.

Common, expected causes include:

Allocation differences on unoccupied or partially occupied days (e.g., Kitchen absorbing shared load)

Optional or infrequently used zones (e.g., Laundry, Guest Room)

Manual approximation or rounding

Legitimate physical behavior differences between zones

Operational guidance:

Validation results are informational and non-alerting by design.

Single-day WARN/FAIL outcomes should not prompt corrective action.

Validation is intended to be interpreted over time, looking for repeated zone-specific bias or drift.

Data Quality (DQ) remains the sole authority for determining whether automated data is trustworthy.

This separation ensures that validation highlights semantic disagreement without conflating it with system health.

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


