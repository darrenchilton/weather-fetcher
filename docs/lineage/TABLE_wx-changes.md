# Table Lineage — WX Changes

Base ID: `appoTbBi5JDuMvJ9D`

**Table Name:** WX Changes  
**Canonical Path:** docs/lineage/TABLE_wx-changes.md  

**Grain:** 1 record per detected change event against a WX record  
**Identity:** Airtable record ID (append-only log)  
**Role:** Mutation audit and observability table. WX Changes records *meaningful mutations*
to WX rows caused by ingestion, rollups, or automations, enabling traceability,
debugging, and trust signals.

**Row creation policy:** Append-only (create-only)

---

---

## Related lineage docs
- `docs/lineage/TABLE_wx.md` — mutation target (daily fact table)
- `docs/lineage/TABLE_thermostat-events.md` — upstream event evidence
- `docs/lineage/TABLE_therm-zone-daily.md` — downstream derived table

## Sources (how data enters this table)

### Airtable Automation: WX change detection (authoritative creator)
- **Actor:** Airtable automations documented under `docs/automations/`
  (e.g., change-detection, data-validation, DQ-related pipelines)
- **Write mode:** create-only
- **Purpose:** Emit a durable log record whenever a monitored WX field
  changes in a meaningful way.

**Inputs (read-only):**
- **WX** (`tblhUuES8IxQyoBqe`) — before/after values
- Automation runtime context (trigger time, run id, actor)

### Manual entry (exceptional)
- **Actor:** Human (Airtable UI)
- **Write mode:** manual create
- **Policy:** Allowed only for investigation or annotation.
Manual rows should be clearly labeled and excluded from automated interpretation.

---

## Writers (actors that create/update records)

| Actor | Create | Update | Delete |
|------|--------|--------|--------|
| Airtable automations (WX change detection / DQ) | ✔ | ✖ | ✖ |
| Human (UI) | ✔ (rare) | ✖ | ✖ |

No actor is permitted to update or delete existing WX Changes records.

---

## Field ownership (who owns which fields)

### Automation-owned
Typical automation-owned fields include (names may vary by implementation):
- Link to WX record
- Change timestamp
- Change category / type
- Field(s) changed
- Before value(s)
- After value(s)
- Severity / classification (informational, warn, critical)
- Source automation / producer identifier

### Human-owned
- Notes / commentary fields (if present)

---

## Enrichment stages (ordered lifecycle)

1. **Trigger**
   - WX record is updated by an upstream actor (weather ingestion, HA rollup,
     Open-Meteo update, or other automation).

2. **Change detection**
   - Automation evaluates whether the mutation is meaningful
     (value delta, threshold breach, categorical change, etc.).

3. **WX Changes row creation**
   - If criteria are met, a WX Changes record is created capturing:
     - what changed
     - when it changed
     - which WX record was affected
     - how severe the change is

4. **Downstream use**
   - Used for alerting, debugging, audits, and long-term trust analysis.
   - Does **not** feed back into WX mutation decisions directly.

---

## Timing and ordering assumptions

- WX Changes creation occurs **after** the triggering WX update.
- Multiple WX Changes may be emitted for a single WX row over time.
- Ordering across different automations is eventual; timestamps, not order,
  are the authoritative sequence indicator.

---

## Failure detection and guardrails

### Expected absence vs failure
- No WX Changes rows on a day **may be normal** if nothing changed.
- Absence becomes suspicious only when paired with known upstream activity.

### Failure modes
- Automation disabled → silent loss of observability (no mutation logs)
- Overly broad change criteria → excessive noise
- Overly narrow criteria → missed anomalies

### Monitoring strategies
- Scheduled review of WX Changes volume (too many / too few)
- Severity-based alerting (critical-only vs informational)

---

## Invariants (must remain true)

1. WX Changes is append-only.
2. Each record corresponds to a single detected mutation event.
3. WX Changes never drives mutations; it only observes them.
4. Historical records are immutable and auditable.
5. Links to WX must always reference an existing WX record.

---

## Recovery and reprocessing

- WX Changes cannot be reconstructed perfectly after the fact without
  replaying historical mutations.
- If change-detection logic changes, treat historical WX Changes as
  versioned under the old logic.
- For investigation gaps, annotate manually rather than rewriting history.
