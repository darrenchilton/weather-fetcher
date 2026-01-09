# Automation — Data Validation

## Purpose

Runs a **thermostat validation** script on a single WX record after a user performs a manual entry workflow.

This is **validation only** (Manual vs Auto comparison). It does **not** assess data integrity and does **not** emit alerts. It writes structured validation outputs back onto the same WX record for review, reporting, and/or downstream presentation.

---

## Artifacts

- `artifacts/data-validation.trigger.json`
- `artifacts/data-validation.steps.json`
- `artifacts/data-validation.script.js`



## Trigger

**Type:** When a record is updated  
**Table:** `WX`  
**Watched field(s):** `Run Data Validation (post manual entry)`  
**View restriction:** None (watches the table, filtered by field)

### Operator model (how it is intended to be used)
- A user toggles/updates `Run Data Validation (post manual entry)` on a WX record.
- That update triggers this automation and runs the validation script for that specific record.

---

## Actions

### Step 1 — Run script

**Action type:** Run script (custom script from code editor)

#### Inputs
- `wxRecordId` = Airtable record ID (from the triggering record)

> Note: The script supports optional input overrides (thresholds, excluded zones, etc.), but the automation as configured appears to provide only `wxRecordId`. Default thresholds and policies apply unless the automation is later extended.

---

## What the Script Does (Functional Summary)

### Scope
- Loads the single WX record referenced by `wxRecordId`.
- Compares **per-zone kWh** values:
  - Auto: `* KWH (Auto)` fields
  - Manual: `* KWH` fields
- Produces a per-zone diff summary plus rollup stats.
- Writes results back to the same WX record into “Therm Validation *” fields.

### Explicit non-goals (as stated in script header)
- Does NOT perform “data integrity / DQ” (handled elsewhere)
- Does NOT drive alerts (no Slack, no warnings outside Airtable)

---

## Reads

### Tables
- `WX`

### Fields read (primary)
- `Usage Type` (single select / text)
- Per-zone kWh fields, for the configured zone list:
  - `{LR KWH (Auto)}`, `{LR KWH}`, …
  - `{Kitchen KWH (Auto)}`, `{Kitchen KWH}`, …
  - `{Up Bath KWH (Auto)}`, `{Up Bath KWH}`, …
  - `{MANC KWH (Auto)}`, `{MANC KWH}`, …
  - `{Master KWH (Auto)}`, `{Master KWH}`, …
  - `{Stairs KWH (Auto)}`, `{Stairs KWH}`, …
  - `{Den KWH (Auto)}`, `{Den KWH}`, …
  - `{Guest Hall KWH (Auto)}`, `{Guest Hall KWH}`, …
  - `{Laundry KWH (Auto)}`, `{Laundry KWH}`, …
  - `{Guest Bath KWH (Auto)}`, `{Guest Bath KWH}`, …
  - `{Guest Room KWH (Auto)}`, `{Guest Room KWH}`, …
  - `{Entryway KWH (Auto)}`, `{Entryway KWH}`, …

### Script-config/policy signals (via constants)
- Certain usage types skip validation entirely:
  - `System Off`
  - `Enabled, No Heat Needed`
- `Empty House` changes expectations to Kitchen-only by default
- Always excluded zones (default): `Guest Hall`
- Optional zones opt-in (default): `Laundry`, `Guest Room`

---

## Writes

### Table
- `WX` (updates the triggering record only)

### Fields written (always or conditionally)
On normal run (non-skipped), the script writes:

- `Therm Validation Status` (single select): `PASS` / `WARN` / `FAIL`
- `Therm Validation Score` (number, 0–100)
- `Therm Validation Compared Zones` (text)
- `Therm Validation Missing Manual Zones` (text)
- `Therm Validation Missing Auto Zones` (text)
- `Therm Validation Max Abs Diff` (number)
- `Therm Validation Mean Abs Diff` (number; may be null)
- `Therm Validation Notes` (long text, includes thresholds + per-zone detail)
- `Therm Validation Needs Review` (checkbox/boolean)
- `Therm Validation Last Run` (date/time)

On “skipped” usage types, it still writes a full set of outputs with:
- `Therm Validation Status = PASS`
- `Therm Validation Score = 100`
- Notes indicating SKIPPED + rationale
- Compared/missing fields set to “(skipped)”

---

## Validation Logic (as implemented)

### Hybrid threshold model (per zone)
The script uses a **hybrid tolerance** system:

- A zone is “OK” if it passes **either**:
  - absolute kWh tolerance, OR
  - percentage tolerance
- A zone is “SEVERE” only if it fails **both**:
  - absolute fail threshold AND
  - percentage fail threshold

Default thresholds (unless overridden via automation inputs):
- PASS absolute tolerance: `0.50 kWh`
- FAIL absolute tolerance: `2.00 kWh`
- PASS percent tolerance: `5%`
- FAIL percent tolerance: `15%`

### Status assignment (record-level)
- `WARN` if compared zone count < minimum (default: 1)
- `FAIL` if any severe zones exist
  - Exception: if only Kitchen is compared, severe results are downgraded to `WARN`
- `WARN` if:
  - any warn zones exist, OR
  - any missing manual zones exist, OR
  - any missing auto zones exist
- Otherwise `PASS`

### Score model (record-level)
Starts at 100, subtracts:
- `10` per severe zone
- `5` per warn zone
- `5` per missing auto zone
- `2` per missing manual zone
Clamped to `[0, 100]`.

---

## Idempotency Model

**Idempotent for a fixed record state.**

- Re-running the script on the same WX record with unchanged inputs yields equivalent outputs.
- The script overwrites the “Therm Validation *” output fields deterministically from current record values.

There is no multi-record mutation and no incremental state.

---

## Failure Modes and Detection

| Failure mode | Expected behavior | Detection |
|---|---|---|
| `wxRecordId` missing | Script throws error (“Missing required input”) | Automation run shows failure |
| Record not found | Script throws error | Automation run shows failure |
| Field name drift (renamed fields) | Script may throw or produce missing/null comparisons | Automation failure or WARN-heavy output |
| Non-numeric field content | Coerced where possible; otherwise treated as null | Missing manual/auto zones in output |
| Usage Type triggers skip policy | Script writes “SKIPPED” outputs | Visible in `Therm Validation Notes` |

---

## Classification

**Contract-affecting (derived validation outputs) — but not pipeline-critical.**

This automation writes a set of derived validation fields that may be used by:
- review workflows
- dashboards/views
- operational interpretation

However, it does **not**:
- produce the thermostat rollup data
- affect Thermostat Events or Therm Zone Daily
- gate the scheduled pipeline

It is best understood as a **post-entry validation layer**.

---

## Inclusion in `PIPELINE_thermostats.md`

**No (recommended).**

### Rationale
- Triggered by manual workflow field updates, not scheduled pipeline stages.
- Produces “validation overlay” fields, not canonical rollups.
- Better placed in an “Operator Workflows / Validation” section (or a separate QA/validation doc).

If you want a single place to reference it from the pipeline doc, add a short link/mention under “Manual interventions” rather than treating it as a pipeline step.

---

## Summary

Data Validation is a user-invoked automation that compares manual kWh entries against auto-derived kWh values per zone on a single WX record, producing standardized validation status, score, and notes on that record. It is deterministic, record-scoped, and intended for review—not alerting or pipeline derivation.
