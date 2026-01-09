# Automation — Set Point to Off

## Purpose

Emits a **Slack notification** when a thermostat setpoint is explicitly set to **0.0**, indicating the system has been turned off for a zone.

This automation provides **operator visibility** into explicit shutoff events and does not modify data.

---

## Trigger

**Type:** When a record enters a view  
**Table:** `Thermostat Events`  
**View:** `Set Point off`

### Trigger semantics
The trigger fires when:
- a thermostat event is created that matches the view, or
- an existing event is updated and newly matches the view, or
- the view’s filters change and cause a record to enter the view

---

## View Contract: `Set Point off`

This automation is entirely driven by the view definition.

### Filter logic
The view includes thermostat event records where:

- `New Setpoint = 0.0`

This represents an explicit “off” action rather than a passive or inferred state.

---

### Interpretation
When a record enters this view:
- A thermostat zone’s setpoint has been set to zero
- Heating for that zone is effectively disabled
- The event may be intentional (vacancy, shutdown) or noteworthy (unexpected off)

---

## Actions

### Step 1 — Send Slack message

- **Action type:** Send message
- **Slack channel:** `#windham-wx-report`

#### Message content (semantic)
- Clear divider
- Statement: “Set point set to off”
- Event name (`Name`)
- Link to the filtered Thermostat Events view
- Link back to the automation configuration

This message is informational and intentionally non-judgmental.

---

## Reads

| Table | Fields |
|------|--------|
| Thermostat Events | `New Setpoint` |
| Thermostat Events | `Name` |

---

## Writes

**None**

This automation does not mutate Airtable data.

---

## Idempotency Model

- **Not idempotent**
- Each entry (or re-entry) into the view emits a Slack message
- Multiple off events for the same zone are reported independently

This behavior is intentional.

---

## Failure Modes and Detection

| Failure mode | Result | Detection |
|--------------|--------|-----------|
| View misconfigured | Missed or excess notifications | Slack volume or silence |
| Slack integration failure | Lost notification | Airtable automation error log |
| Setpoint flapping | Multiple messages | Expected behavior |

---

## Classification

**Alerting / Monitoring**

- No data derivation
- No schema mutation
- Purely observational

---

## Contract Impact

**Non–contract-affecting**

- Does not influence WX rollups or thermostat derivations
- Does not gate downstream pipelines

---

## Inclusion in `PIPELINE_thermostats.md`

**No**

### Rationale
- This automation observes thermostat events
- It does not produce or transform pipeline data
- Belongs to operational awareness rather than data derivation

---

## Summary

Set Point to Off surfaces explicit thermostat shutoff events in real time via Slack, providing human visibility without altering data or enforcing policy.
