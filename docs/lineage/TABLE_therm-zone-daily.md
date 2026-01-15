# Table Lineage — Therm Zone Daily (tbld4NkVaJZMXUDcZ)

Base ID: `appoTbBi5JDuMvJ9D`

**Table Name:** Therm Zone Daily  
**Table ID:** tbld4NkVaJZMXUDcZ  
**Canonical Path:** docs/lineage/TABLE_therm-zone-daily.md  

**Grain:** 1 record per (Zone × Local Day)  
**Identity / Upsert key:** (`Date` local day, `Zone`)  
**Role:** Derived daily thermostat analytics by zone. This table is a derived-only surface:
it exists to provide a normalized per-zone daily fact table for reporting and analysis.

**Row creation policy:** Deterministic upsert (create missing; update existing)

---

---

## Related lineage docs
- `docs/lineage/TABLE_wx.md` — daily fact table (input surface)
- `docs/lineage/TABLE_thermostat-events.md` — event log (input surface)
- `docs/lineage/TABLE_wx-changes.md` — mutation audit log (observability)

## Sources (how data enters this table)

### Airtable Automation: therm-zone-daily (authoritative sole writer)
- **Actor:** Airtable Automation `therm-zone-daily`
- **Documentation:** `docs/automations/AUTOMATION_therm-zone-daily.md`
- **Script artifact:** `docs/automations/therm-zone-daily/artifacts/therm-zone-daily.script.js`
- **Write mode:** upsert (create + update) on (Zone × Local Day)
- **Purpose:** Materialize daily derived metrics per zone from upstream evidence.

**Upstream inputs (read-only):**
- **WX** (`tblhUuES8IxQyoBqe`) — daily facts and readiness/monitoring fields
- **Thermostat Events** (`tblvd80WJDrMLCUfm`) — event log (setpoint changes) linked to WX
- Potentially other derived fields produced by other automations (DQ gate outputs)

### Manual entry
- **Actor:** Human (Airtable UI)
- **Write mode:** discouraged; treat as break-glass only
- **Policy:** Manual edits to derived metrics are non-authoritative and should be avoided.
If absolutely required, annotate and expect future automation runs to overwrite.

---

## Writers (actors that create/update records)

| Actor | Create | Update | Delete |
|------|--------|--------|--------|
| Airtable Automation: therm-zone-daily | ✔ | ✔ (deterministic overwrite) | ✖ |
| Human (UI) | ✖ (discouraged) | ✖ (discouraged) | ✖ |

**Sole writer invariant:** Only the `therm-zone-daily` automation may write this table.

---

## Field ownership (who owns which fields)

### Automation-owned (therm-zone-daily)
All derived metrics and linkage fields are automation-owned, including but not limited to:
- `Date` (local day)
- `Zone`
- Link to `WX` (foreign key / linked record)
- Aggregated event metrics (counts, setpoint-hours, degree-hours, efficiency indices)
- Change counts / change classification aggregates
- Source markers (e.g., derived vs carried-forward semantics if present)
- DQ status copy-forward fields (if implemented)

### Human-owned
- Notes / commentary (if present and explicitly designated human-owned)

**Policy:** Human edits to automation-owned fields are expected to be overwritten.

---

## Enrichment stages (ordered lifecycle)

1. **Preconditions (upstream readiness)**
   - WX record exists for the target local day (WX is created by weather ingestion).
   - Thermostat Events exist and are linked/available for the day’s window.
   - Optional DQ gates have executed (if required by your pipeline).

2. **Index build (upsert map)**
   - Automation reads existing Therm Zone Daily records for the target date range
     and builds an index keyed by (`Date`, `Zone`).

3. **Metric derivation (per zone)**
   - For each zone, compute deterministic daily metrics from upstream evidence:
     - Derived from linked Thermostat Events and/or WX thermostat rollup artifacts
     - Any zone-specific aggregates computed in JS.

4. **Upsert write**
   - Create new records for missing (Zone × Day).
   - Update existing records in-place with deterministic overwrite semantics.
   - Batch size is capped (create/update in slices; see script artifact).

5. **Post-write invariants**
   - Exactly one record per (Zone × Day).
   - All records link back to the correct WX day (if linkage field exists).

---

## Timing and ordering assumptions

- `therm-zone-daily` is scheduled (daily) and assumes upstream producers have had time to run:
  - Weather ingestion (WX row exists)
  - Home Assistant rollups (WX thermostat fields updated)
  - Event linkage and change-detection stages (if used as inputs)
- The system is eventually consistent; schedule timing is not a correctness proof.
Readiness should be inferred from data evidence (e.g., WX readiness signals).

---

## Failure detection and guardrails

### Airtable-native indicators
- Automation run history: failures show runtime exceptions (getTable/getField/updateRecordAsync)
- Output validation: missing zones or duplicate (Zone × Day) rows should be detectable via views

### Data-quality / validation gates (if enabled)
- DQ status copied into Therm Zone Daily can be used as a first-class failure signal.
- “Missing Therm Zone Daily for yesterday” can be monitored by a scheduled check or view.

### Common failure modes
- Upstream WX day missing (weather ingestion failure or schema mismatch)
- Linkage missing between Thermostat Events and WX day
- Field renames in Airtable causing script getField failures
- New zone added without updating the automation’s zone list (if zones are enumerated)

---

## Invariants (must remain true)

1. **Derived-only:** No external script creates or edits Therm Zone Daily rows.
2. **Uniqueness:** At most one record exists per (`Date`, `Zone`).
3. **Determinism:** Re-running the automation for the same day produces the same outputs.
4. **Upsert safety:** Updates overwrite automation-owned fields and do not create duplicates.
5. **Referential integrity:** Each record links to the correct WX day (if linkage is present).

---

## Recovery and reprocessing

- Safe recovery action: rerun the `therm-zone-daily` automation for the affected date range.
- If upstream inputs were late/missing, rerun upstream stages first, then rerun `therm-zone-daily`.
- If schema drift occurred (field rename/type change), fix schema and rerun automation to repopulate.
