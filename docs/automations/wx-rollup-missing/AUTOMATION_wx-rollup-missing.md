# Automation — WX rollup missing

## Purpose

Detects missing **Home Assistant thermostat rollups** for the most recent completed day and emits a **human-actionable Slack alert** when required WX-derived fields have not been populated by the defined SLA.

This automation acts as an **early-warning sentinel** for upstream Home Assistant execution failures and protects downstream trust in WX data.

---

## Trigger

**Type:** Scheduled  
**Schedule:** Every day at **06:30 AM ET**

### Rationale
- All HA “morning rollups” are expected to have completed by this time.
- Establishes a hard SLA boundary for completeness of *yesterday’s* WX record.
- Biases toward early detection rather than silent failure.

---

## Actions

### Step 1 — Find records

- **Action type:** Find records
- **Table:** `WX`
- **Selection mode:** From view
- **View:** `ALERT — HA Rollup Missing`
- **Maximum records:** 1000

This step delegates all detection logic to a single, auditable view.

---

### Step 2 — Conditional Slack alert

- **Condition:** Run only if `Records length > 0`
- **Action:** Send Slack message
- **Recipient:** `@darrenchilton` (direct message)

#### Message intent
- Identify affected WX dates
- Declare the SLA violation
- Provide a **procedural runbook** for immediate investigation

#### Message semantics
- Indicates HA did not populate thermostat / kWh fields by **06:30 ET**
- Includes concrete diagnostic commands:
  - Docker container status
  - HA automation presence
  - `shell_command` mapping validation
  - HA container log inspection (last 12 hours)

This message is intentionally **operational**, not descriptive.

---

## View Contract: `ALERT — HA Rollup Missing`

This automation is **tightly coupled** to the logic of the view below.  
The view represents the executable contract for detection.

---

### Time scope

The view filters WX records where:

- `datetime` **is yesterday (EST)**

This ensures only the most recent expected HA rollup window is evaluated.

---

### Rollup presence signal

The view further filters for records where:

- `HA Rollup Present? = 0`

This field is the **authoritative readiness signal** for HA-derived data.

---

### Field: `HA Rollup Present?`

**Type:** Formula (numeric)

```airtable
IF(
  OR(
    COUNTA({Thermostat Settings (Auto)}) > 0,
    COUNTA({Data Source}) > 0
  ),
  1,
  0
)

Semantic meaning

HA Rollup Present? = 1

At least one authoritative HA-derived signal exists:

Thermostat rollup populated Thermostat Settings (Auto), or

A producer explicitly populated Data Source

HA Rollup Present? = 0

No HA rollup output exists

No producer fallback occurred

The WX record is unsafe to trust

This formula intentionally collapses multiple producer paths into a single binary invariant.

Interpretation

If a WX record appears in ALERT — HA Rollup Missing at 06:30 ET, it means:

Home Assistant likely:

did not execute the rollup automation, or

executed it but failed before writing to Airtable, or

wrote partial/incomplete results

Manual investigation is required before trusting downstream analytics.

Coupling and drift warning

This automation’s behavior is entirely determined by this view.

Any change to the following must be treated as a behavioral change and requires revisiting this document:

Definition of “rollup presence”

Which fields count as authoritative HA output

Timezone or day-boundary logic

SLA timing of the scheduled trigger

Reads
Table	Fields / Constructs
WX	datetime
WX	Thermostat Settings (Auto)
WX	Data Source
WX	HA Rollup Present?
WX	All fields referenced by ALERT — HA Rollup Missing
Writes

None

This automation is read-only with respect to Airtable data.

Idempotency Model

Fully idempotent

Re-running produces the same alert as long as the view continues to return records

No state mutation

No deduplication logic required

Failure Modes and Detection
Failure mode	Result	Detection
View misconfigured	False negatives	Silent
Slack integration failure	Missed alert	Airtable automation error log
Automation disabled	No alert	Manual inspection
HA rollup completes late	False positive	Acceptable by design

This automation intentionally favors false positives over false negatives.

Classification

Alerting / Monitoring

Does not derive data

Does not mutate schema

Does not affect downstream tables

Exists solely to surface upstream pipeline failures

Contract Impact

Non–contract-affecting

No schema writes

No semantic derivations

No downstream data dependency

Inclusion in PIPELINE_thermostats.md

No

Rationale

This automation does not participate in thermostat data derivation.

It monitors external pipeline health (Home Assistant execution), not Airtable transformations.

Conceptually belongs to operational observability, not the data pipeline itself.

Summary

This automation enforces a single operational invariant:

“By 06:30 ET, every WX record for yesterday must have at least one authoritative HA-derived signal.”

Violation of this invariant triggers immediate human intervention.
