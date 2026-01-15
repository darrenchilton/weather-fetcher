# Table Lineage — WX (tblhUuES8IxQyoBqe)

Base ID: `appoTbBi5JDuMvJ9D`

**Table Name:** WX  
**Table ID:** tblhUuES8IxQyoBqe  
**Canonical Path:** docs/lineage/TABLE_wx.md  

**Grain:** 1 record per **local day** (America/New_York)  
**Identity / key:** `datetime` (date field representing the local day)  
**Role:** Daily fact table and computation surface. WX is the convergence point for:
- **Authoritative weather** (Visual Crossing; creates rows)
- **Comparative weather** (Open-Meteo; updates only)
- **Home Assistant daily rollups** (thermostat + indoor environment; updates only)
- **Airtable automation enrichments** (linkage, classification, validation, DQ, derived daily analytics)

**Row creation policy:** Only **Visual Crossing weather ingestion** is permitted to create WX rows.

---

---

## Related lineage docs
- `docs/lineage/TABLE_thermostat-events.md` — real-time event log
- `docs/lineage/TABLE_therm-zone-daily.md` — derived per-zone daily facts
- `docs/lineage/TABLE_wx-changes.md` — change log / observability

## Sources (all ways data can enter this table)

### A) Visual Crossing weather ingestion (authoritative WX row creator)
- **Actor:** `weather_fetcher.py` (repo: weather-fetcher)
- **Write mode:** upsert (create missing days + update existing days)
- **Horizon:** rolling window including historical backfill and forecast days (per README / ingestion schema)
- **Purpose:** Ensure one WX record exists per local day and populate producer-owned Visual Crossing fields.
- **Key invariant:** This is the **only** permitted creator of WX rows.

### B) Open-Meteo enrichment (update-only; comparative weather)
- **Actors:** `update_openmeteo.py` (scheduled), `openmeteo_fetcher.py` (fetch/transform), `run_openmeteo.sh` (scheduler wrapper)
- **Write mode:** update-only (patch existing WX rows by matching day)
- **Purpose:** Populate/overwrite `om_*` comparative fields (never creates WX rows).
- **Backfill tool:** `backfill_openmeteo_history.py` (one-off update-only historical backfill).

### C) Home Assistant thermostat daily rollup (update-only; daily artifacts)
- **Actor:** `homeassistant/scripts/thermostat_rollup_write_yesterday.py` (executed inside HA container via `shell_command`)
- **Write mode:** update-only (patch matched WX row for the target day)
- **Purpose:** Write daily thermostat artifacts (usage, kWh, setpoints, summaries, readiness evidence).
- **Timing:** Overnight; may retry; downstream automation must not assume completion based on clock time alone.

### D) Home Assistant indoor environment daily rollup (update-only)
- **Actor:** `homeassistant/scripts/ha_indoor_env_daily_write_yesterday.py` (executed via HA `shell_command`)
- **Write mode:** update-only (patch matched WX row for the target day)
- **Purpose:** Write per-entity humidity/temperature stats plus summary fields.

### E) Airtable automations (update-only; enrichment/validation)
Fully documented under `docs/automations/`. Representative categories:
- **Linkage:** link WX ↔ Thermostat Events
- **Derived classification:** usage type, change classification, etc.
- **Data validation / quality gates:** compute DQ status, warn/alert, copy DQ signals downstream
- **Derived rollups:** scheduled recomputations that update WX fields deterministically

### F) Manual entry (exceptional)
- **Actor:** Human (Airtable UI)
- **Write mode:** manual edits
- **Policy:** Allowed only for explicitly human-owned fields (e.g., notes, annotations).
Manual edits to producer-owned fields are expected to be overwritten by the next run.

---

## Writers (actors that update records)

| Actor | Create | Update | Delete |
|------|--------|--------|--------|
| Visual Crossing ingestion (`weather_fetcher.py`) | ✔ | ✔ | ✖ |
| Open-Meteo enrichment (`update_openmeteo.py`, backfill tool) | ✖ | ✔ | ✖ |
| HA thermostat rollup (`thermostat_rollup_write_yesterday.py`) | ✖ | ✔ | ✖ |
| HA indoor env rollup (`ha_indoor_env_daily_write_yesterday.py`) | ✖ | ✔ | ✖ |
| Airtable automations (multiple) | ✖ | ✔ | ✖ |
| Human (UI) | ✖ (discouraged) | ✔ (restricted) | ✖ |

---

## Field ownership (who owns which fields)

WX is intentionally multi-writer. Correctness depends on a clear “field ownership” contract.

### 1) Visual Crossing–owned fields (weather core; overwrite each run)
- Authoritative daily weather fields (the `vc_*` / core weather surface as defined in:
  - `docs/schema/AIRTABLE_WX_SCHEMA.md`
  - `docs/schema/WEATHER_INGESTION_SCHEMA.md`)

**Rule:** May be overwritten on every ingestion run for the same day.

### 2) Open-Meteo–owned fields (`om_*`; overwrite each run)
- Comparative fields sourced from Open-Meteo (forecast + derived daily aggregates)

**Rule:** Open-Meteo overwrites only its `om_*` fields; must not edit Visual Crossing fields.

### 3) Home Assistant–owned fields (thermostat + indoor env; overwrite each run for target day)
- Thermostat daily artifacts (kWh, setpoints, usage, summaries, last-run timestamps)
- Indoor environment daily stats (humidity/temperature stats + summary fields)

**Rule:** HA rollups overwrite HA-owned fields for the targeted day. HA never creates WX rows.

### 4) Airtable automation–owned fields (derived enrichment surface)
- Usage-type derivations (e.g., `derive-usage-type`)
- Data validation outputs
- Data quality outputs and warning flags
- Event linkage fields (links to Thermostat Events)
- “Change” rollups and other derived daily classification fields

**Rule:** Automation-owned fields should be treated as deterministic outputs and may be overwritten by scheduled recompute.

### 5) Human-owned fields (explicitly manual)
- Notes, annotations, “Long Note”, and other explicitly manual interpretation fields (if present)

**Rule:** Human-owned fields must not be overwritten by producers/automations.

---

## Enrichment stages (ordered lifecycle)

1. **WX row materialization (Visual Crossing)**
   - Creates missing records for the rolling window (including forecast days).
   - Updates authoritative weather fields.

2. **Open-Meteo comparative overlay**
   - Updates `om_*` fields for overlapping days.
   - Optional historical backfill updates older days without creating rows.

3. **Home Assistant overnight rollups (eventually consistent)**
   - Thermostat rollup updates yesterday’s WX row (and possibly retries).
   - Indoor environment rollup updates the same WX row.
   - Writes “last run”/evidence fields used as readiness signals.

4. **Airtable linkage + derived analytics**
   - Link Thermostat Events to the correct WX day.
   - Compute change summaries / derived classifications.
   - Upsert Therm Zone Daily downstream derived table.
   - Run validation + DQ gates and emit alerts if required.

5. **Monitoring and alerts**
   - Scheduled “missing rollup” detection checks readiness signals and alerts if HA did not materialize into Airtable by SLA.

---

## Timing and ordering assumptions

- **Clock time is not a proof of completion.** HA rollups may retry; ingestion is eventually consistent.
- Downstream automations should gate on **data evidence** (readiness fields), not time.
- WX contains both **past days and future forecast days**; downstream thermostat analytics should generally target completed days only.

---

## Failure detection and guardrails

### Row-level existence
- Missing WX row for a day implies weather ingestion failure (or schema/key mismatch).
- Weather ingestion is expected to backfill a recent historical window each run, reducing long-lived gaps.

### HA ingestion readiness
- Use the canonical HA readiness signal field(s) (documented in README/runbook) to detect missing HA rollup.
- A scheduled “WX rollup missing” automation alerts when HA evidence is absent by SLA.

### Schema drift
- Airtable field renames/types can break producers and automations.
- Guard by keeping observed schema snapshots and validating key fields (contracts in `docs/schema/`).

### Multi-writer collisions (by design)
- Collisions are avoided by strict field ownership. The primary risk is a producer overwriting another producer’s fields due to naming drift or refactor.

---

## Invariants (must remain true)

1. **One record per local day** (America/New_York), keyed by `datetime`.
2. **Only Visual Crossing ingestion creates WX rows.**
3. Open-Meteo is update-only and writes only `om_*` fields.
4. Home Assistant is update-only and writes only HA-owned rollup fields.
5. Automation-owned fields are deterministic and safe to recompute.
6. Human-owned fields are not overwritten by automated producers.

---

## Recovery and reprocessing

- **Weather gaps:** rerun Visual Crossing ingestion; it should recreate recent window deterministically.
- **Open-Meteo issues:** rerun update; backfill tool can repair historical comparative fields.
- **HA issues:** rerun HA rollup scripts for the affected day(s) (if recorder data is intact).
- **Derived analytics issues:** rerun Airtable automations (safe deterministic recompute) after upstream is repaired.
