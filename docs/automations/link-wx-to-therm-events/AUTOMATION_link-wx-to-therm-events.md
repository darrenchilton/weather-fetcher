# Airtable Automation — Link WX to Therm Events

## 1. Identity
- Base: appoTbBi5JDuMvJ9D
- Automation name (UI): Link WX to Therm Events
- Automation type: Record-created trigger → Update record
- Status: ON
- Trigger table: Thermostat Events
- Runs per month (observed): high (event-driven)
- Last verified: 2026-01-08 (local)

## 2. Purpose and scope
### Purpose
Immediately link each newly created **Thermostat Events** record to its corresponding **WX** daily record.

This establishes the **event → day** relationship early, so that:
- downstream scripts can rely on event-to-day linkage,
- manual inspection of Thermostat Events is intelligible,
- late-arriving events are still associated with the correct WX day.

### Scope
- Single-record, synchronous enrichment at event creation time.
- No aggregation, no backfill, no multi-record logic.

## 3. Trigger
- Trigger type: When a record is created
- Trigger table: Thermostat Events
- Trigger condition: Always
- Trigger payload:
  - Airtable record ID of the newly created Thermostat Events row.

## 4. Action
### Action type
- Update record

### Target
- Table: Thermostat Events
- Record ID: Airtable record ID from trigger step

### Fields written
- `WX` (link field)
  - Value source: formula / lookup labeled **Date (YYYY-DD-MM)** in the automation UI
  - Purpose: resolve and link the Thermostat Event to the correct WX daily record

> Note: The automation UI shows the WX field being populated via a derived “Date (YYYY-DD-MM)” selector, which implies Airtable is performing a lookup or formula-based resolution to choose the correct WX record.

## 5. Date and identity semantics
### Intended behavior
- Each Thermostat Event is linked to **exactly one WX record**, representing the local day the event belongs to.

### Observed assumptions
- The automation assumes:
  - Thermostat Events contain a date or timestamp field usable to derive the local day.
  - WX contains exactly one record per local day.
  - The derived “Date (YYYY-DD-MM)” selector correctly resolves to the intended WX record.

### Timezone handling
- Timezone logic is implicit and handled by Airtable field configuration (not by script).
- This differs from the explicit timezone handling used in scripted automations.

## 6. Idempotency model
- Intended model: **single-write on creation**
- The automation only fires on record creation.
- Re-running does not occur automatically.
- If the WX link is later cleared or incorrect:
  - Manual correction or a separate repair automation would be required.

## 7. Failure modes and observability
### Failure modes
- WX record not found for derived date:
  - Result: WX link remains empty.
  - No retry occurs automatically.
- Ambiguous WX resolution (multiple records for same date):
  - Airtable may link arbitrarily or fail validation (depends on field config).
- Date mismatch due to timezone interpretation:
  - Event may be linked to the wrong WX day near midnight boundaries.

### Observability
- Visual inspection of Thermostat Events table:
  - WX link field populated (or not).
- No logging, no status fields, no error capture.

## 8. Contract classification
- Contract-affecting: **YES**
  - This automation establishes the foundational linkage between raw events and daily facts.
  - Downstream scripts *implicitly* rely on correct event/day alignment even if they re-derive dates independently.

## 9. Downstream dependencies
- Therm State Changes (3:15am):
  - Re-derives day membership by timestamp, but linked WX improves debuggability.
- Data Quality (3:45am):
  - Uses Thermostat Events by Date; correct linkage ensures conceptual consistency.
- Manual analysis and audits:
  - WX linkage is the only persistent, human-readable join between events and days.

## 10. Known limitations (documented, not changed)
1) No backfill:
   - Events created before this automation existed are not auto-linked.
2) No repair logic:
   - Incorrect or missing links are not automatically corrected.
3) Implicit timezone semantics:
   - Unlike scripted automations, timezone rules are not explicit or version-controlled.

## 11. Evidence
- UI:
  - Trigger: When a record is created (Thermostat Events)
  - Action: Update record → Thermostat Events → Field: WX
- No script (pure Airtable native automation)

## 12. Change log
- 2026-01-08: Initial documentation snapshot (from production automation UI)
