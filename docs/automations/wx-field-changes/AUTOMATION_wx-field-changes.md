# Automation — WX Field Changes

## Purpose

Creates an **immutable audit log** of changes to selected weather fields on the `WX` table.

Each qualifying update results in a new record in `WX Changes`, preserving:
- the updated values
- the effective datetime
- a human-readable description
- a backlink to the source WX record

This enables historical inspection, debugging, and provenance tracking without mutating the source record.

---

## Trigger

**Type:** When a record is updated  
**Table:** `WX`  
**Watched fields:**
- `temp`
- `precipprob`
- `snow`
- `om_temp`
- `om_snowfall`

The trigger fires whenever **any** of these fields changes.

---

## Actions

### Step 1 — Create record (WX Changes)

**Table:** `WX Changes`

Fields written:
- `datetime` ← `WX.datetime`
- `temp` ← `WX.temp`
- `precipprob` ← `WX.precipprob`
- `snow` ← `WX.snow`
- `om_temp` ← `WX.om_temp`
- `om_snowfall` ← `WX.om_snowfall`
- `description` ← `WX.Local WX Desc`

This step captures a **point-in-time snapshot** of weather state.

---

### Step 2 — Update record (WX Changes)

**Target:** The record created in Step 1  
**Update:**
- `WX` ← `WX.datetime (formatted for link)`

This establishes a **relational backlink** to the originating WX record.

---

## Reads

| Table | Fields |
|------|--------|
| WX | `datetime` |
| WX | `temp` |
| WX | `precipprob` |
| WX | `snow` |
| WX | `om_temp` |
| WX | `om_snowfall` |
| WX | `Local WX Desc` |

---

## Writes

| Table | Fields |
|------|--------|
| WX Changes | `datetime` |
| WX Changes | `temp` |
| WX Changes | `precipprob` |
| WX Changes | `snow` |
| WX Changes | `om_temp` |
| WX Changes | `om_snowfall` |
| WX Changes | `description` |
| WX Changes | `WX` (link) |

---

## Idempotency Model

**Non-idempotent by design.**

- Every qualifying update creates a new `WX Changes` record
- Repeated updates with the same values will still produce records
- This is intentional and treated as an **append-only event log**

There is no deduplication logic in this automation.

---

## Failure Modes and Detection

| Failure mode | Effect | Detection |
|--------------|-------|-----------|
| Rapid WX updates | High record volume | `WX Changes` growth |
| Field added/renamed | Trigger stops firing | Automation error / silent gap |
| Link step fails | Orphan change record | Missing `WX` link |

---

## Classification

**Monitoring / Audit**

- No derived fields
- No upstream gating
- No downstream dependencies

---

## Contract Impact

**Non–contract-affecting**

- Does not influence daily rollups
- Does not change WX semantics
- Exists solely to observe and record change

---

## Inclusion in `PIPELINE_thermostats.md`

**No**

### Rationale
This automation observes WX mutation but does not participate in thermostat derivation, rollups, or scoring.

---

## Summary

WX Field Changes provides a durable audit trail of weather field mutations, enabling traceability and debugging while keeping the primary WX record clean and authoritative.
