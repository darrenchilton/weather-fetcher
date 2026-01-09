# Automation — DQ Warn

## Purpose

Emits a **Slack warning notification** when a WX record enters a data-quality warning or failure state, as determined by the **Thermostat Data Quality** automation.

This automation provides **human visibility** into DQ issues but does not modify data or escalate automatically.

---

## Trigger

**Type:** When a record enters a view  
**Table:** `WX`  
**View:** `DQ Score (WARN)`

### Trigger semantics
The trigger fires when:
- a WX record is created and matches the view, or
- an existing WX record is updated and newly matches the view, or
- the view’s filters change and cause a record to enter the view

---

## View Contract: `DQ Score (WARN)`

This automation is **entirely driven** by the view logic below.

### Time scope
The view filters WX records where:
- `datetime` is **after 2025-12-15 (GMT)**  
- `datetime` is **before today (EST)**

This bounds alerts to recent operational data.

---

### DQ condition
The view further filters for:
- `Therm DQ Status` **is any of**:
  - `WARN`
  - `FAIL`

The view therefore represents **non-PASS thermostat data quality outcomes**.

---

### Interpretation
If a WX record enters this view:
- Thermostat DQ checks have completed
- At least one rule has produced a WARN or FAIL
- The record may still be usable, but requires attention or review

---

## Actions

### Step 1 — Send Slack message

- **Action type:** Send message
- **Slack channel:** `#thermostat-warning`

#### Message content (semantic)
- Header: `DQ Warning:`
- Body: Contents of `Therm DQ Notes`
- Footer: Deep link back to the Airtable base / automation context

The message is intentionally concise and defers detailed interpretation to Airtable.

---

## Reads

| Table | Fields |
|------|--------|
| WX | `Therm DQ Status` |
| WX | `Therm DQ Notes` |
| WX | `datetime` |

---

## Writes

**None**

This automation is read-only with respect to Airtable data.

---

## Idempotency Model

- **Not idempotent by design**
- Each transition of a record into the view produces a Slack message
- Re-entering the view (after leaving) will emit again

This is acceptable for warning-level visibility.

---

## Failure Modes and Detection

| Failure mode | Result | Detection |
|--------------|--------|-----------|
| View misconfigured | Missing or excessive alerts | Slack volume / silence |
| Slack integration failure | Lost notification | Airtable automation error log |
| Record flaps between states | Multiple warnings | Expected behavior |

---

## Classification

**Alerting / Monitoring**

- Does not derive data
- Does not mutate records
- Sole purpose is human notification

---

## Contract Impact

**Non–contract-affecting**

- No schema changes
- No downstream pipeline dependency

---

## Inclusion in `PIPELINE_thermostats.md`

**No**

### Rationale
- This automation does not participate in data derivation
- It reacts to outcomes of the data-quality pipeline
- Belongs to operational observability and alerting

---

## Summary

DQ Warn is a lightweight Slack notification automation that surfaces thermostat data quality WARN/FAIL outcomes to humans without modifying data or driving escalation logic.
