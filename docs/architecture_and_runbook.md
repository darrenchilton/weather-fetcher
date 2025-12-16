# WX Table Enrichment System — Technical Specification & Operations Runbook

**Repository:** weather-fetcher  
**Scope:** Weather ingestion + Home Assistant enrichment of the Airtable WX table  
**Audience:** Maintainers, future operators, auditors  
**Status:** Authoritative (repo-safe, no secrets)

---

## 1. System Overview

The WX Table Enrichment System is a **multi-producer data pipeline** that maintains a single daily weather record per date in Airtable and incrementally enriches it with:

- Core weather data (Visual Crossing)
- Comparative weather data (Open-Meteo)
- Home energy and thermostat activity (Home Assistant)

All producers cooperate by respecting a shared **record identity contract** and **field ownership model**.

---

## 2. Airtable WX Table Contract (Authoritative)

### 2.1 Primary Key

- The WX table is keyed by the **`{datetime}`** field (date).
- All writers must locate records using:

```
IS_SAME({datetime}, 'YYYY-MM-DD', 'day')
```

### 2.2 Record Creation Rules

- **Weather fetchers** may create or update records.
- **Home Assistant** must **never create records**.
- Home Assistant updates only existing records.

### 2.3 Field Ownership

| Producer           | Owned Fields |
|-------------------|--------------|
| Visual Crossing    | Core weather fields (`temp`, `humidity`, etc.) |
| Open-Meteo         | `om_*` fields |
| Home Assistant     | `Thermostat Settings (Auto)`, `<Zone> KWH (Auto)`, `Data Source` |

Overwriting another producer’s fields is a hard violation.

---

## 3. Data Producers

### 3.1 Visual Crossing Weather Fetcher

- Runs via GitHub Actions every 6 hours.
- Fetches historical + forecast weather.
- Creates or updates WX records.
- Serves as the **record initializer**.

### 3.2 Open-Meteo Fetcher

- Runs via GitHub Actions 30 minutes after VC.
- Updates existing WX records only.
- Adds elevation-corrected comparative fields.

### 3.3 Home Assistant Thermostat Rollup (Phase 7)

- Runs locally inside Home Assistant.
- Enriches WX records with:
  - Thermostat event summaries
  - Per-zone daily kWh usage
- Uses HA recorder SQLite DB for energy data.

Canonical script:

```
/config/scripts/thermostat_rollup_write_yesterday.py
```

---

## 4. Home Assistant Rollup — Functional Specification

### 4.1 Target Date Semantics

- Target date is always **yesterday (local time)**.
- Local timezone: `America/New_York`.
- Processing window:

```
[00:00, 24:00) local time
```

### 4.2 Event Rollup Logic

- Reads thermostat events from Airtable Events table.
- Classifies events:
  - Setpoint change
  - OFF
  - ON restore
- Produces:
  - Total event counts
  - Per-zone counts
  - Trace IDs (Airtable record IDs)

### 4.3 kWh Rollup Logic

- Reads daily utility meters from HA recorder DB.
- Sensors: `sensor.<zone>_energy_daily`
- The **last numeric state within the window** is the day’s kWh.

#### Missing Data Handling

If a zone has no numeric kWh:

- Field is **not written**
- A clear explanatory note is appended to the summary
- No zeros are fabricated

This preserves historical accuracy.

---

## 5. Scheduling & Idempotency

### 5.1 Schedule

Home Assistant automation runs:

- **00:30 local** — primary run
- **02:00 local** — late-event catch-up

### 5.2 Idempotency Guarantees

- Rollups are rebuilt from source data every run.
- Writes overwrite the same WX record deterministically.
- Re-running produces identical output given identical inputs.

---

## 6. Deployment Model

### 6.1 Canonical Entry Point

Home Assistant uses a single canonical shell command:

```yaml
shell_command:
  thermostat_rollup_write_yesterday: >-
    python3 /config/scripts/thermostat_rollup_write_yesterday.py
```

### 6.2 Automation Wiring

```yaml
action:
  - service: shell_command.thermostat_rollup_write_yesterday
```

### 6.3 Restart Procedure

Preferred:

```bash
docker exec homeassistant ha core restart
```

Fallback:

```bash
docker restart homeassistant
```

---

## 7. Operational Runbook

### 7.1 Manual Dry Run

```bash
docker exec homeassistant bash -lc "python3 /config/scripts/thermostat_rollup_write_yesterday.py"
```

### 7.2 Manual Write Run

```bash
docker exec homeassistant bash -lc "WRITE_WX=1 python3 /config/scripts/thermostat_rollup_write_yesterday.py"
```

### 7.3 What a Healthy Run Looks Like

- Exactly one WX record resolved
- Event counts reconcile
- `kwh_present > 0` after meters exist
- `wx_update: OK` in logs

### 7.4 Common Failure Modes

| Symptom | Likely Cause |
|-------|--------------|
| Missing kWh | Meter history not present |
| Multiple WX records | Data hygiene issue |
| Zero events | Legitimate no-change day |

---

## 8. Security & Secrets

- Airtable tokens **must not** be committed.
- Secrets live in:
  - HA config or env vars
  - GitHub Actions secrets
- Repo documentation uses placeholders only.

---

## 9. GitHub as Source of Truth (Roadmap)

### Phase A — Documentation (Complete)
- Repo contains architecture + runbook
- HA implementation archived

### Phase B — GitOps-lite
- Repo becomes deployment source
- Scripts pushed into HA from repo

### Phase C — GitHub-run Execution (Future)
- Expose kWh inputs securely
- Run full rollup from GitHub Actions
- HA becomes data publisher, not executor

---

## 10. Status

- **Phase 7:** COMPLETE
- **Production:** Stable and unattended
- **Next Phase (Optional):** Monitoring, backfill tooling, cost attribution
