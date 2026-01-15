# Table Lineage — Thermostat Events (tblvd80WJDrMLCUfm)

Base ID: `appoTbBi5JDuMvJ9D`

**Table Name:** Thermostat Events  
**Table ID:** tblvd80WJDrMLCUfm  
**Canonical Path:** docs/lineage/TABLE_thermostat-events.md  

**Grain:** 1 record per thermostat effective setpoint change (including OFF↔ON semantics)  
**Identity:** Airtable record ID (append-only event log)  
**Role:** Authoritative near–real-time event stream for thermostat setpoint changes.
Downstream automations aggregate these events into daily artifacts (WX, Therm Zone Daily).

**Row creation policy:** Append-only (create-only). Events should be treated as immutable once written.

---

---

## Related lineage docs
- `docs/lineage/TABLE_wx.md` — daily fact table (links/events surface)
- `docs/lineage/TABLE_therm-zone-daily.md` — derived per-(Zone × Day) metrics
- `docs/lineage/TABLE_wx-changes.md` — mutation audit log

## Sources (how data enters this table)

### Home Assistant real-time event logging (authoritative row creator)
- **Mechanism:** Home Assistant `rest_command.log_thermostat_event`
- **Config location:** `/config/configuration.yaml` (lines 12–31)
- **Endpoint:** `https://api.airtable.com/v0/appoTbBi5JDuMvJ9D/tblvd80WJDrMLCUfm`
- **Write mode:** append-only (create-only via HTTP POST)
- **Payload fields (ingest-time):**
  - `Timestamp` = `{{ now().isoformat() }}`
  - `Date` = `{{ now().strftime('%Y-%m-%d') }}`
  - `Thermostat` = derived from `friendly_name` with `" Thermostat"` stripped
  - `New Setpoint`, `Previous Setpoint` = derived with OFF mapped to 0
  - `Change Type` = `"Unknown"` (default; may be refined downstream)

### Home Assistant automation that calls the rest_command (real-time trigger surface)
- **Automation item_id:** `log_thermostat_setpoint_changes`
- **Domain:** `automation`
- **Evidence source:** `/config/.storage/trace.saved_traces` (multiple runs captured)
- **Triggers (2 state triggers):**
  1) `platform: state` on these entities (attribute **temperature**):
     - `climate.stairs_thermostat`
     - `climate.lr_thermostat`
     - `climate.kitchen_thermostat`
     - `climate.up_bath_thermostat`
     - `climate.manc_thermostat`
     - `climate.master_thermostat`
     - `climate.den_thermostat`
     - `climate.guest_hall_thermostat`
     - `climate.laundry_thermostat`
     - `climate.guest_bath_thermostat`
     - `climate.entryway_thermostat`
     - `climate.guest_room_thermostat`
  2) `platform: state` on the same entities (attribute **hvac_mode**)

### Manual entry (exceptional)
- **Actor:** Human (Airtable UI)
- **Write mode:** manual create
- **Purpose:** Rare recovery or annotation scenarios only.
- **Policy:** Must be clearly annotated; downstream logic must tolerate but not depend on manual events.

---

## Writers (actors that create/update records)

| Actor | Create | Update | Delete |
|------|--------|--------|--------|
| Home Assistant (automation `log_thermostat_setpoint_changes` → `rest_command.log_thermostat_event`) | ✔ | ✖ | ✖ |
| Human (UI) | ✔ (rare) | ✖ | ✖ |

No actor is permitted to update or delete existing Thermostat Event records.

---

## Change detection semantics (how the automation decides to log)

The automation uses a **template condition** that:

1) Implements a **startup spam guard**:
   - Ignores events for **90 seconds** after `input_datetime.ha_last_start`.

2) Ignores transitions involving `unknown` / `unavailable`.

3) Computes **effective setpoints** with OFF mapped to 0:
   - If from/to state or `hvac_mode` is `off`, effective setpoint = 0
   - Else effective setpoint = climate `temperature` attribute (float)

4) Logs an event only when:
   - `to_effective_setpoint != from_effective_setpoint`

This means Thermostat Events represents **effective setpoint change**, not raw state churn.

---

## Field ownership (who owns which fields)

### HA-owned (ingest-time payload fields)
Written by Home Assistant at creation time:
- `Timestamp`
- `Date`
- `Thermostat`
- `New Setpoint`
- `Previous Setpoint`
- `Change Type` (defaulted to Unknown at ingest)

### Automation-owned (post-ingest enrichment)
Written by Airtable automations (documented under `docs/automations/`) to support linkage and analytics:
- Link to WX record (if implemented as a linking stage)
- Normalized / classified change type
- Any bucketing, grouping, or derived classification fields

### Human-owned
- Notes / commentary fields (if present)
- Explicit manual correction annotations

---

## Enrichment stages (ordered lifecycle)

1. **Real-time ingest**
   - Thermostat state/setpoint changes in HA trigger the automation.
   - Automation calls `rest_command.log_thermostat_event` with computed values.
   - Airtable Thermostat Events record is created immediately.

2. **Linkage to WX**
   - Scheduled Airtable automation links events to the appropriate WX local day.

3. **Downstream daily aggregation**
   - Events are aggregated into:
     - WX derived daily fields
     - Therm Zone Daily derived rows

4. **Validation + DQ checks**
   - Detect anomalies such as “expected activity but no events,” or unlinked events.

---

## Timing and ordering assumptions

- Thermostat Events creation is near–real-time and should precede daily aggregations.
- Event-to-WX linkage is allowed to be eventually consistent (scheduled).
- Missing events are a stronger failure signal than late linkage.

---

## Failure detection and guardrails

Primary detection points:
- **HA trace evidence:** the presence/absence of action executions for
  `rest_command.log_thermostat_event` in `/config/.storage/trace.saved_traces`.
- **Airtable-side evidence:** gaps in Thermostat Events during known interaction periods.
- **Downstream checks:** DQ/validation automations flag unlinked events and suspicious zero-event days.

Operational risks:
- Airtable credential/token expiry or invalidation → POST failures
- Automation disabled or mis-triggered
- Payload schema drift if Airtable field names change

---

## Invariants (must remain true)

1. Thermostat Events is append-only; historical events are not edited or deleted.
2. Home Assistant automation `log_thermostat_setpoint_changes` is the authoritative creator.
3. OFF is represented as an effective setpoint of **0** (as implemented).
4. Each event represents a change in **effective setpoint**.
5. Downstream daily aggregations are reproducible from event history.

---

## Security invariant (operational)

- Airtable credentials and HA tokens must be stored in secrets (not plaintext YAML) and rotated if exposed.
