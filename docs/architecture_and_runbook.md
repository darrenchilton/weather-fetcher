# WX Table Enrichment System — Technical Specification & Operations Runbook

**Project:** Albert Court Maintenance  
**Scope:** Weather ingestion, Home Assistant energy rollups, and validation monitoring  
**Audience:** Maintainers, operators, future auditors  
**Status:** Authoritative technical reference

“On 2025-12-18, the system transitioned from °F to °C at the HA/MQTT layer. A small number of thermostat events were recorded with mixed units; these were normalized post-hoc. Daily rollups were unaffected because they operate on event counts, not temperature arithmetic.”

---

## 1. System Overview

This system produces **one authoritative daily record per date** in the Airtable **WX** table and incrementally enriches it with:

- Historical and forecast weather data (GitHub Actions)
- Home Assistant–derived thermostat activity summaries
- Per-zone daily energy usage (kWh)
- Ongoing validation and confidence monitoring

The design is explicitly **append-and-enrich**, not transactional. Each producer has clearly defined responsibilities and field ownership.

---

## 2. High-Level Data Flow

```
Mysa thermostats
   ↓ (event-driven telemetry)
mysa2mqtt → MQTT
   ↓
Home Assistant state engine
   ↓
HA recorder (SQLite)
   ↓ (daily snapshot)
Thermostat rollup script
   ↓
Airtable WX table (system of record)
```

Key architectural principle:

> **During the day, data exists only as telemetry in Home Assistant.**  
> **A daily snapshot materializes that telemetry into a durable record.**

### 2.1 Deployment Topology & File Locations

**System:** Mac Mini (hostname: `Plexs-Mac-mini`)  
**User:** `plex`  
**Operating System:** macOS

**Home Assistant Deployment**

Home Assistant runs as a Docker container named `homeassistant`.

**Critical File Locations (Host Filesystem)**

| Path | Description | Typical Size |
|------|-------------|--------------|
| `/Users/plex/homeassistant/config/` | Home Assistant configuration directory (mounted into container) | - |
| `/Users/plex/homeassistant/config/configuration.yaml` | Main HA configuration file | ~10 KB |
| `/Users/plex/homeassistant/config/home-assistant_v2.db` | Recorder database (telemetry storage) | ~500 MB - 1 GB |
| `/Users/plex/homeassistant/config/scripts/` | Python rollup scripts | - |
| `/Users/plex/homeassistant/config/scripts/thermostat_rollup_m4_write_yesterday.py` | Current production rollup script | - |
| `/Users/plex/homeassistant/config/thermostat_rollup_write.log` | Rollup execution log | - |
| `/Users/plex/homeassistant/config/automations.yaml` | HA automations | - |

**Container Mount Points**

The host directory `/Users/plex/homeassistant/config/` is mounted to `/config` inside the container.

Therefore:
- Host: `/Users/plex/homeassistant/config/home-assistant_v2.db`
- Container: `/config/home-assistant_v2.db`

**Essential Terminal Commands**

**Docker Management:**
```bash
# Restart Home Assistant
docker restart homeassistant

# Check if container is running
docker ps | grep homeassistant

# View container logs (real-time)
docker logs homeassistant -f

# View last 100 log lines
docker logs homeassistant --tail 100

# Execute command inside container
docker exec homeassistant <command>

# Interactive shell inside container
docker exec -it homeassistant /bin/bash
```

**Log Monitoring:**
```bash
# Monitor recorder operations
docker logs homeassistant -f | grep -i recorder

# Monitor purge operations
docker logs homeassistant -f | grep -i purge

# Check for errors
docker logs homeassistant --tail 500 | grep -i error

# Search logs for specific zone/sensor
docker logs homeassistant | grep -i "stairs"

# View rollup script execution log
cat /Users/plex/homeassistant/config/thermostat_rollup_write.log
tail -f /Users/plex/homeassistant/config/thermostat_rollup_write.log
```

**Database Operations:**
```bash
# Check database size
ls -lh /Users/plex/homeassistant/config/home-assistant_v2.db

# Check database size in human-readable format
du -h /Users/plex/homeassistant/config/home-assistant_v2.db

# Manual database purge (7-day retention)
docker exec homeassistant python -m homeassistant.components.recorder.util purge --keep-days 7 --repack

# Manual database purge (14-day retention)
docker exec homeassistant python -m homeassistant.components.recorder.util purge --keep-days 14 --repack
```

**Configuration Management:**
```bash
# Edit configuration.yaml
docker exec -it homeassistant nano /config/configuration.yaml

# Check configuration for errors
docker exec homeassistant python -m homeassistant --script check_config

# Reload YAML configuration without restart
# (via HA UI: Developer Tools → YAML → Reload options)
```

**Disk Space Monitoring:**
```bash
# Check available disk space
df -h /Users/plex/homeassistant

# Check size of config directory and contents
du -sh /Users/plex/homeassistant/config/*

# Find large files in config directory
find /Users/plex/homeassistant/config -type f -size +100M -exec ls -lh {} \;
```

**Rollup Script Execution:**
```bash
# View available shell commands (defined in configuration.yaml)
# These are executed via HA automations or Developer Tools → Actions

# Manual rollup execution (if needed)
docker exec homeassistant bash -lc 'WRITE_WX=1 python3 /config/scripts/thermostat_rollup_m4_write_yesterday.py'

# View rollup output
tail -50 /Users/plex/homeassistant/config/thermostat_rollup_write.log
```

**Network & Connectivity:**
```bash
# Check Home Assistant is accessible
curl -I http://192.168.1.153:8123

# Check container network
docker inspect homeassistant | grep -A 10 NetworkSettings
```

**Backup Verification:**
```bash
# List recent backups (if using HA backup feature)
ls -lt /Users/plex/homeassistant/backups/ | head -10

# Check backup size
du -sh /Users/plex/homeassistant/backups/*
```

**Quick Diagnostics:**
```bash
# One-liner: Check container status, database size, recent logs
docker ps | grep homeassistant && \
ls -lh /Users/plex/homeassistant/config/home-assistant_v2.db && \
docker logs homeassistant --tail 20
```

**Important Notes**

- Always use `docker exec homeassistant` prefix when running commands that need to access container internals
- The database file should never be edited manually; use recorder purge operations
- Configuration changes require restart or YAML reload to take effect
- Log files can grow large; monitor `/config/` directory size periodically

---

## 3. Airtable WX Table Contract

### 3.1 Record Identity

- The WX table is keyed by `{datetime}` (date).
- All producers must locate records using:

```
IS_SAME({datetime}, 'YYYY-MM-DD', 'day')
```

### 3.2 Record Creation Rules

- Weather fetchers may create records.
- Home Assistant **never creates records**; it only updates existing ones.

### 3.3 Field Ownership

| Producer | Owned Fields |
|--------|--------------|
| Weather fetchers | Core weather fields (`temp`, `tempmin`, `tempmax`, etc.) |
| Open-Meteo | `om_*` comparative fields |
| Home Assistant | `Thermostat Settings (Auto)`, `<Zone> KWH (Auto)`, monitoring fields |

Overwriting fields owned by another producer is a hard violation.

---

## 4. Home Assistant Telemetry (During the Day)

### 4.1 Update Cadence

- There is **no fixed polling interval**.
- Updates are **event-driven**:
  - Mysa publishes power changes via MQTT
  - Home Assistant updates state immediately

Measured cadence (empirical):
- Median update: ~20–30 seconds when active
- P90: ~2 minutes
- Worst observed gaps: ~4–5 minutes

This cadence is more than sufficient for accurate daily kWh integration.

### 4.2 Where Data Lives During the Day

- Raw power and energy data is stored in the **Home Assistant recorder database** (`home-assistant_v2.db`).
- This database is local to the machine/container.
- Data here is **telemetry**, not a ledger.

Until the daily rollup runs:
- No durable daily kWh exists
- Airtable fields remain blank by design

### 4.3 Recorder Database Retention Policy

**Purpose**

The Home Assistant recorder database (`home-assistant_v2.db`) stores telemetry from all sensors during the day. Without retention limits, this database can grow to multi-gigabyte sizes, consuming unnecessary disk space and slowing down Home Assistant operations.

**Configured Retention**

The system is configured with a 14-day retention policy in `configuration.yaml`:

```yaml
recorder:
  purge_keep_days: 14
  commit_interval: 60
  auto_purge: true
```

**What These Settings Mean:**

- **purge_keep_days: 14** — Retain only the last 14 days of detailed telemetry
- **commit_interval: 60** — Write to database every 60 seconds (reduces disk I/O)
- **auto_purge: true** — Automatically purge old data daily at 4:12 AM local time

**Expected Database Size**

With 12 thermostats reporting power/energy data every 20-30 seconds:
- **Without retention:** Database can grow to 9+ GB over time
- **With 14-day retention:** Steady-state size is approximately 500 MB - 1 GB
- **With 7-day retention:** Approximately 300-500 MB

**Why 14 Days Is Conservative**

Since Airtable WX table is the system of record and daily rollups run 3 times per night (00:30, 02:00, 04:30), the system only strictly needs 1-2 days of telemetry for recovery purposes. The 14-day retention provides a substantial safety margin for:
- Troubleshooting unexpected issues
- Manual backfills if rollup automation fails
- Diagnostic analysis of sensor behavior

**Operational History**

- **2025-12-29:** Database reached 9.2 GB before retention policy was enforced
- **2025-12-29:** Manual purge with 7-day retention reduced database to 367 MB
- **Ongoing:** Auto-purge runs daily at 4:12 AM, maintaining database at ~500-700 MB

**Manual Purge Procedure**

If manual cleanup is needed (e.g., after configuration changes or to reduce retention further):

Via Home Assistant UI:
1. Developer Tools → Actions
2. Service: `recorder.purge`
3. Switch to UI mode
4. Set `keep_days` and enable `repack`
5. Click "Perform action"

Via command line:
```bash
docker exec homeassistant python -m homeassistant.components.recorder.util purge --keep-days 7 --repack
```

**Note:** Purge operations take 15-45 minutes depending on database size and will cause Home Assistant to be briefly slower during execution.

**Verification**

Check current database size:
```bash
ls -lh /path/to/home-assistant_v2.db
```

Monitor auto-purge logs:
```bash
docker logs homeassistant | grep -i "purge completed"
```

Expected log output after daily auto-purge:
```
Recorder: Purge completed, removed XXXXX states and XXXXX events
```

**Safety Considerations**

This retention policy is safe because:
1. Airtable WX table is the authoritative system of record
2. Daily rollups capture all energy data before purge runs
3. Multiple overnight rollup runs provide redundancy
4. 14 days provides ample recovery margin (only 1-2 days strictly needed)

---

## 5. Daily Rollup (Materialization)

## 5.0 Rollup Execution Environment & Credential Model

All Home Assistant rollup scripts (thermostat rollups, indoor environment rollups) authenticate to Home Assistant via **runtime-injected environment variables**.

### Required Environment Variables

Each rollup script requires the following environment variables at execution time:

- `HA_BASE` — Home Assistant API base URL  
  Example: `http://127.0.0.1:8123`

- `HA_TOKEN` — Home Assistant long-lived access token  
  Used for all `/api/*` requests (history, states, etc.)

These variables are **mandatory**. Scripts do not attempt fallback discovery, config parsing, or secret loading.

If either variable is missing, the script terminates immediately.

### Why These Variables Are Not Global

The Home Assistant Docker container does **not** expose these values globally by design.

They are injected only at execution time to ensure that:
- Credentials are scoped to the specific command being run
- Tokens are not ambiently available to unrelated processes
- Manual execution paths are explicit and auditable

There is intentionally:
- No `.env` file
- No `secrets.yaml` reference
- No alternative credential loading mechanism
### Execution Modes (Production vs Manual)

### 📌 INSERT BLOCK — *Common Failure Modes & Interpretation*

```md
### Common Failure Modes & How to Interpret Them

| Symptom | Meaning | Action |
|-------|--------|--------|
| `ERROR: missing env var HA_TOKEN` | Script was executed without environment-variable injection | Re-run via `shell_command` or provide `HA_BASE` and `HA_TOKEN` inline |
| `HTTP Error 401: Unauthorized` | Token is invalid, revoked, or expired | Validate token manually (see below); generate a new long-lived token if needed |
| Script runs but writes nothing | Target WX record not found or no qualifying data | Check date targeting and recorder coverage |
| Script works via automation but fails manually | Manual execution missing env vars | This is expected; manual path must inject env vars explicitly |
| `HTTP 401` from `/api/` or `automation.reload` | Shell token is missing, truncated, or revoked | Replace HA long-lived token and re-test `/api/` until HTTP 200 |

#### Token Replacement & YAML Reload Gotcha

Home Assistant does **not** automatically reload `automations.yaml` after file edits.

After modifying any automation YAML:
- You **must** reload automations via:
  - UI: Developer Tools → YAML → Reload Automations  
  **or**
  - API: `POST /api/services/automation/reload`

Failure to reload results in:
- YAML edits appearing correct on disk
- Automations continuing to run the previous in-memory definition

This is a common source of false-negative debugging.


These errors do **not** indicate bugs in the rollup scripts.  
They indicate execution-context mismatches.

Rollup scripts may be executed in three distinct contexts. Understanding the differences is critical for correct troubleshooting.

#### 1) Shell Command Execution (Production)

This is the **canonical production path**.

- Defined in `configuration.yaml` under `shell_command`
- Environment variables (`HA_BASE`, `HA_TOKEN`) are injected inline
- Invoked by Home Assistant automations or manually via Developer Tools → Actions

Example (illustrative):

```yaml
shell_command:
  ha_rollup_yesterday: >
    HA_BASE=http://127.0.0.1:8123
    HA_TOKEN=***
    python3 /config/scripts/thermostat_rollup_write_yesterday.py
This is the only path where environment injection is automatic.

2) docker exec (Manual / Troubleshooting)

When running a script manually inside the container, no environment variables are present by default.

They must be supplied explicitly:

docker exec homeassistant bash -lc '
  HA_BASE=http://127.0.0.1:8123
  HA_TOKEN=***
  python3 /config/scripts/thermostat_rollup_write_yesterday.py

Failure to do so will result in immediate startup errors.

3) Host Shell Execution (Incorrect / Unsupported)

Running a rollup script directly from the macOS host shell (outside Docker) is not supported.

Reasons:

/config paths do not exist on the host

Home Assistant recorder database is not accessible

Environment variables are not injected

Network assumptions differ

Any failures observed in this mode are non-actionable.
### 5.1 Timing

- Target date: **yesterday (local time)**
- Local timezone: `America/New_York`

Scheduled runs:
- 00:30 local — primary
- 02:00 local — late-event catch-up
- 04:30 local — safety net
### Canonical Token Validation

Before troubleshooting rollup logic, always validate the Home Assistant token directly.

From the host or container:

```bash
curl -H "Authorization: Bearer <HA_TOKEN>" \
  http://127.0.0.1:8123/api/
Expected result:

HTTP 200 → token is valid

HTTP 401 → token is invalid or revoked

Do not proceed with rollup debugging until this check passes.

Canonical Manual Rollup Pattern
For manual testing or backfill validation, use this pattern:

bash
Copy code
docker exec homeassistant bash -lc '
  HA_BASE=http://127.0.0.1:8123
  HA_TOKEN=***
  python3 /config/scripts/<rollup_script>.py
'
This exactly mirrors the production execution environment.

yaml
Copy code

### Automation Wiring (Home Assistant)

The Indoor Environment rollup is invoked by the same Home Assistant automation
that performs the Thermostat Rollup WRITE step.

Automation ID:
- `phase7_m3_thermostat_rollup_write_yesterday`

Action sequence (order matters only for log readability):

1. `shell_command.thermostat_rollup_write_yesterday`
2. `shell_command.ha_indoor_env_write_yesterday`

This ensures that indoor temperature and humidity statistics are materialized
whenever Home Assistant energy data is successfully written.


---
### 5.2 kWh Rollup Logic

- Source sensors: `sensor.<zone>_energy_daily`
- For each zone:
  - Query recorder history for the target date
  - Take the **last numeric value** in the window

Missing data handling:
- If no numeric value exists, the field is **not written**
- Zeros are never fabricated

### 5.3 Idempotency

- Each run rebuilds output from source data
- Re-running produces identical results
- Writes overwrite the same WX record deterministically

### 5.4 Daily Setpoint Baseline Rollup (Therm SP)

5.4.1 Purpose

In addition to daily kWh rollups, the system materializes a per-zone thermostat setpoint baseline for each day. This enables later analysis that incorporates both energy usage and setpoint intent (e.g., “higher energy because setpoints were higher”), without treating setpoint change frequency as a correctness signal.

This process is explicitly non-alerting and does not affect DQ.

### 5.4.2 Output Model (script-owned fields in WX)

The Therm SP rollup writes the following script-owned fields on the target WX record (all JSON serialized to text unless noted):

{Therm SP Start (Derived)} — JSON map: zone → setpoint at start of day (snapshot)

{Therm SP End (Derived)} — JSON map: zone → setpoint at end of day (snapshot)

{Therm SP Timeline (Derived)} — JSON map: zone → list of intervals, each {from,to,sp} in ISO-8601 UTC timestamps; this is the authoritative “setpoint at any time” representation

{Therm SP Setpoint-Hours (Derived)} — JSON map: zone → {totalHours,setpointHours,hoursBySetpoint}

{Therm SP Degree-Hours (Derived)} — JSON map: zone → degree-hours, where each interval contributes MAX(0, sp − {om_temp}) × hours

{Therm SP Degree-Hours by Setpoint (Derived)} — JSON map: zone → map(setpoint → degree-hours)

{Therm Efficiency Index (Derived)} — JSON map: zone → (kWh / degree-hours) or null when unavailable (stale, missing kWh, or degree-hours ≤ 0)

{Therm SP Source (Derived)} — JSON map: zone → Observed | CarriedForward | Stale

{Therm SP Changes Count (Derived)} — JSON map: zone → count of setpoint-bearing events during the day

{Therm SP Stale Zones (Derived)} — comma-separated list of zones considered stale

{Therm SP Summary (Derived)} — human-readable diagnostic summary (includes counters and per-zone rollup highlights)

{Therm SP Last Run} — timestamp of the most recent run

Ownership rule:
These fields are owned exclusively by the Therm SP script and must not be written by other producers.


### 5.4.3 Data Sources and Semantics

Source table: Thermostat Events

Canonical event time field: {Timestamp} (date/time)

Canonical setpoint field: {New Setpoint} (number)

Zone identity: {Thermostat} (preferred; typically linked record name), fallback {Name} (text)

Semantics:

“Start setpoint” is the last known setpoint before local day start; if none exists, it uses the first setpoint event on that day.

“End setpoint” is the last known setpoint on or before local day end.

If no setpoint event occurred on the day but prior history exists, the day is tagged CarriedForward.

If the last known setpoint is older than the staleness threshold, the zone is tagged Stale.

Staleness threshold:

Default: 36 hours (configurable in the automation script)

Exclusions:

EXCLUDED_ZONES can be provided to exclude zones from all Therm SP computations.

## 5.4.3.5 Indoor Environment Rollup (Temperature & Humidity)

### Purpose

The Indoor Environment Rollup materializes **indoor temperature and humidity telemetry**
from Home Assistant into the daily Airtable WX record.

This rollup is informational and descriptive:
- It does **not** affect energy calculations
- It does **not** participate in DQ or validation
- It exists to provide historical indoor context alongside weather and energy data

### Script

- Path (container):  
  `/config/scripts/ha_indoor_env_daily_write_yesterday.py`

### Data Sources

- Home Assistant recorder history (`/api/history/period`)
- Auto-discovered entities:
  - `*_current_temperature`
  - `*_current_humidity`

### Computation

For each discovered entity, the script computes:
- sample count
- minimum
- maximum
- average

### Airtable Outputs (WX table)

The script writes only to these existing fields:

- `{HA Indoor Temperature Stats (Auto)}`
- `{HA Indoor Humidity Stats (Auto)}`
- `{HA Indoor Env Summary (Auto)}`
- `{HA Indoor Env Last Run (Auto)}`

Ownership rule:
These fields are owned exclusively by the Indoor Environment rollup and must not be written by other producers.

### Target Day

- Always writes **yesterday** (local time)
- Local timezone: `America/New_York`

### Idempotency

- Deterministic and idempotent
- Safe to re-run multiple times for the same target day
- Re-running overwrites the same WX fields



### 5.4.4 Automation Trigger and Targeting

Steady-state (production): a scheduled Airtable automation runs each morning and updates yesterday’s WX record.

Trigger: Scheduled (daily), after overnight telemetry/rollups are complete

Target day: yesterday (local timezone: America/New_York)

Record selection: find the WX row whose {datetime} matches the target day (day-level match)

Historical backfill (one-time / occasional): a separate manual workflow may be used to backfill older WX records. After backfill is complete, the scheduled automation is the authoritative mechanism.

Operational guidance:

The daily scheduled Therm SP run is safe to re-run; it is deterministic and overwrites the same derived fields for the target day.

Current Production Automation Schedule (EST)

As of 2026-01-04, automations are intentionally staggered to accommodate HA ingestion retries:

Time (EST)	Automation	Purpose
03:15	Therm State Changes	Materialize Therm SP derived fields
03:30	Derive Usage Type	Classify occupancy from SP timeline
03:45	Data Quality	Validate HA kWh completeness
04:15	Therm Zone Daily	Explode per-zone analytics rows
~06:30	HA Rollup Missing Alert	Detect ingestion failures
Rationale

Home Assistant begins ingestion around ~02:30am and may retry

Airtable automations must not race HA

Usage Type, DQ, and projections all depend on HA-derived fields

The system favors correctness over immediacy.

### 5.4.5 Relationship to Energy Rollups and Validation

Therm SP provides setpoint context for later analysis of energy efficiency and behavior.

Therm SP is not used for DQ alerting and does not imply correctness or incorrectness of energy measurements.

Validation (Manual vs Auto energy comparisons) remains semantically separate from Therm SP.

---

### 5.4.6 Airtable Automations (Manual vs Daily Scheduled)

Two Airtable automations exist for Therm SP enrichment:

### 5.4.7 Interpretation of “No Thermostat Changes”

If no thermostat change events occur on a given day, this does not indicate missing data.

The WX record for that day already contains the authoritative thermostat state via the Therm SP derived fields, in particular {Therm SP Timeline (Derived)}, which defines the effective setpoint for all zones over the full day.

In this case, “no changes” simply means that setpoints were carried forward unchanged for the duration of the day.



#### A) Manual recompute (checkbox-triggered)

Purpose:
- Recompute Therm SP fields for a specific WX record (typically during development or one-off backfills).

Mechanism:
- Trigger: WX checkbox field {Temp Therm Calc} set to true
- Input: wxRecordId (record ID of the triggering WX record)
- Behavior: recomputes the target record’s date and writes all derived Therm SP outputs
- Post-condition: clears {Temp Therm Calc} back to false (success path)

#### B) Daily scheduled recompute (production)

Purpose:
- Recompute Therm SP fields for the prior day automatically (steady-state production path).

Mechanism:
- Trigger: Scheduled automation (daily, morning, after overnight HA rollups are complete)
- Target day: yesterday in local time zone (America/New_York)
- Record selection: locate the WX record whose {datetime} matches the target day (day-level match; supports both date-type and YYYY-MM-DD strings)
- Behavior: recomputes and overwrites the same derived Therm SP outputs for that WX record
- Post-condition: does not depend on, and should not modify, {Temp Therm Calc}

Operational properties:
- Deterministic and idempotent: safe to re-run and safe to run multiple times per day for the same target date.
- Supports optional backfill override (recommended): accept an input variable targetDate="YYYY-MM-DD" to force recompute of a specific day.

#### Field type note: {Therm Efficiency Index (Derived)}

The Therm SP scripts write {Therm Efficiency Index (Derived)} as a JSON map (zone → number|null). This field should therefore be a text-bearing field (single-line text or long text).

If Airtable tooling or logs indicate {Therm Efficiency Index (Derived)} is a Number field, treat this as a schema inconsistency and resolve via one of these approaches:

- Preferred: ensure {Therm Efficiency Index (Derived)} is a long text field and store the per-zone JSON map there.
- Optional: add a separate numeric KPI field (e.g., {Therm Efficiency KPI (Derived)}) for a single daily scalar, leaving the per-zone map in the text field.
- If a Number field with the same name exists, rename one of the duplicates to remove ambiguity and update scripts to reference the intended field.

## 5.5 Therm Zone Daily Projection (Efficiency Monitoring Layer)

### 5.5.1 Purpose

The WX table is the authoritative daily ledger. For monitoring and visualization, we maintain a **derived projection table** named **Therm Zone Daily** that materializes **one record per (Date, Zone)**.

This table exists to support:

- Time-series dashboards and Interfaces
- Zone-to-zone efficiency comparison
- Clean chart semantics (no JSON parsing in Interfaces)
- Separation between computation (WX enrichment) and consumption (analytics)

Therm Zone Daily is a *projection*, not a source of truth. It should be treated as **read-only** outside its population automation.

### 5.5.2 Data Model

Each Therm Zone Daily record corresponds to one local calendar day and one thermostat zone.

Key fields:

- **Date** (local day)
- **Zone**
- **WX Record** (link to the authoritative WX row)
- **kWh Auto**
- **Degree Hours**
- **Setpoint Hours**
- **Efficiency Index** (kWh per degree-hour)
- **SP Source** (Observed / CarriedForward / Stale)
- **SP Changes Count**
- **DQ Status**
- **Usage Type**
- **Include in Trend?** (optional gating field used by dashboards)

### 5.5.3 Population Mechanism (Daily Projection Automation)

A dedicated Airtable Automation script runs after Therm SP enrichment and:

1. Locates the WX record for the target day (yesterday, local time zone)
2. Reads per-zone derived JSON fields written by Therm SP (degree-hours, setpoint-hours, efficiency index, source, changes)
3. Explodes those per-zone maps into one row per zone
4. **Upserts** by natural key: **(Date, Zone)** (idempotent; safe to re-run)

A one-time range backfill can be executed using the same upsert approach to populate historical Therm Zone Daily rows (historical availability currently back to **2025-12-16**).

### 5.5.4 Scheduling and Ordering

Current production schedule (local time):

- **06:00 AM** — Therm SP daily recompute (writes derived JSON fields into WX)
- **08:00 AM** — Therm Zone Daily projection (explodes into per-zone analytics rows)

This ordering ensures all Therm SP derived fields are populated before projection.

Planned enhancement (guardrails):
- The projection script may assert required Therm SP fields are present and fail loudly if upstream enrichment did not complete.

### 5.5.5 Dashboards and Interfaces

All thermostat efficiency dashboards read **only** from **Therm Zone Daily**.

Primary Interface: **Thermostat Efficiency → Zone Efficiency Trends**

Core views:
- House-average Efficiency Index (daily)
- Per-zone Efficiency Index (daily)
- Total kWh Auto (daily)
- DQ coverage KPIs (PASS vs Not PASS)
- Drill-down table of zone-day records

Page-level filters:
- Date range (default: last 30 days)
- Usage Type
- Include in Trend?

### 5.6 Usage Type Derivation (Automated Occupancy Classification)

### 5.6.1 Purpose

The {Usage Type} field encodes high-level household occupancy and heating intent for a given day. It is used to:
Provide context for reporting and dashboards
Gate validation expectations (manual vs auto)
Enable human-readable summaries of system behavior
Usage Type is descriptive, not analytical:
It does not affect energy efficiency calculations
It does not participate in DQ logic
It exists to help humans interpret daily records

### 5.6.2 Source of Truth

As of January 2026, {Usage Type} is fully automated and derived exclusively from:

{Therm SP Timeline (Derived)}


This timeline is the authoritative per-zone representation of:

When a thermostat was ON (setpoint > 0)

When it was OFF (setpoint = 0)

No additional derived fields (e.g., boolean “zone on/off” helpers) are required.

### 5.6.3 Classification Rules

Usage Type is assigned once per WX record using the following deterministic rules:

Usage Type	Definition
No Usage	All zones have setpoint = 0 for the entire day (system fully off)
System Off	Alias of No Usage; typically used for summer / heating-disabled periods
Enabled, No Heat Needed	At least one zone enabled (non-zero setpoint), but total kWh = 0 (warm day)
Empty House	Master and MANC both OFF all day; at least one other zone may be enabled at setback
Guests	Guest Room has setpoint > 0 at any point during the day
Just DC	Master ON at any point; MANC OFF all day
All	Master ON at any point AND MANC ON at any point

Edge cases (e.g., spouse visiting without child) are intentionally ignored.
Classification is based strictly on thermostat behavior, not inferred human presence.

### 5.6.4 Temporal Semantics

A “day” is defined as midnight to midnight in America/New_York

Internally, this corresponds to 05:00Z → 05:00Z during winter

Timeline intervals use UTC timestamps but are interpreted in local-day context

### 5.6.5 Automation Ordering

Correct sequencing is required for accuracy:

Therm SP Daily Recompute
Writes {Therm SP Timeline (Derived)}

Usage Type Derivation Automation
Reads timeline and writes {Usage Type}

Therm Zone Daily Projection
Copies {Usage Type} into per-zone rows

The Usage Type automation is safe to re-run and overwrites the same field deterministically.

### 5.7 HA Rollup Completion Guard (Readiness Signal)
Purpose

Because Home Assistant ingestion and rollup are eventually consistent and may complete after multiple internal passes, the system uses an explicit readiness signal to indicate that Home Assistant–derived data has arrived in Airtable for a given day.

This avoids false downstream failures caused by automations running before HA ingestion has completed.

Mechanism: {HA Rollup Present?}

The WX table includes a formula field:

Field: {HA Rollup Present?}
Type: Formula (numeric: 1 or 0)

Formula:

IF(
  OR(
    COUNTA({Thermostat Settings (Auto)}) > 0,
    COUNTA({Data Source}) > 0
  ),
  1,
  0
)

Semantics

Returns 1 if any Home Assistant rollup evidence is present

Returns 0 if HA ingestion has not occurred or failed

This is a readiness signal only, not a correctness assertion

Design Rationale

HA rollups may complete after multiple internal retries

Some HA automations run at ~02:30am and again later

Downstream Airtable automations must not assume HA is complete based solely on time

This guard allows the system to explicitly distinguish:

Condition	Meaning
HA Rollup Present? = 1	HA ingestion completed at least once
HA Rollup Present? = 0	HA ingestion missing or failed

## 6. Weather Normalization (HDD)

### 6.1 Heating Degree Days

The system derives **Heating Degree Days (HDD)** for analysis:

```
HDD (18C) = MAX(0, 18 − {om_temp})
```

- `{om_temp}` = local-area daily average temperature (°C)
- HDD is **derived**, not fetched

HDD is used for **analysis and validation only**, not control logic.

## 6.2 Interpreting Daily Heating Numbers (Plain-English Guide)

The system produces daily summaries that may look like:
https://airtable.com/appoTbBi5JDuMvJ9D/tblhUuES8IxQyoBqe/viwNTndUN0mEuam91?blocks=hide
view: Zone Efficiency

2025-12-18 | 7 | 103 | 9


These values are descriptive, not judgments. They are intended to help a human understand what kind of day it was, not whether the system performed well or poorly.

What each number means

Heating Demand (HDD = 7)
This reflects how cold the day was.
A higher number means the house needed more heating; a lower number means it was mild.

Total Heating Energy (103 kWh)
This is how much energy the heating system actually used across the whole house that day.

Zones Active (9)
This is how many areas of the house were heated at least somewhat that day.

How to read the combination

In plain terms, this row says:

“On a moderately cold day, most of the house was heated, and the system used a moderate amount of energy to do so.”

This is not a score and not an efficiency rating. It is simply a factual snapshot of demand, response, and scale.

What a single day does not tell you

It does not indicate inefficiency

It does not indicate degradation

It does not require action

Single days are inherently noisy. Meaning emerges only when similar days are compared over time.

Intended use

These summaries support pattern recognition, comparison between similar weather days, and gradual trend awareness. Operational correctness is handled separately by the Data Quality (DQ) gate.

---

## 7. Usage Modes & Intent

The `{Usage Type}` field encodes human intent and drives validation semantics.

Manual energy validation is **not expected** when `{Usage Type}` is one of:
- `Empty: All 13`
- `Empty: Only Kitchen`
- `No Usage`
- `Testing`

A derived formula field expresses this:

```
Manual Expected?
```

This prevents empty-house or testing days from generating false failures.

---

## 8.3 Thermostat Data Quality Gate (Active-Only)
8.3.1 Purpose

The Thermostat Data Quality (DQ) Gate provides a binary operational health signal (PASS / FAIL / WARN) answering one question only:

Given the zones that were actually active on a given day, did the automated system produce valid kWh data for those zones?

This gate is intentionally orthogonal to the comparative validation and confidence scoring framework. It does not compare against manual or modeled expectations and does not attempt to judge energy reasonableness.

It exists to:

Detect missing or corrupt automated data

Eliminate false failures caused by unused zones

Provide a clean alerting signal for automation reliability

8.3.2 Design Principles

The DQ gate follows these rules:

Active-only expectation
A zone is expected to produce kWh data only if it was active, where “active” is defined as:

At least one thermostat event recorded for that zone on the target date

Evidence-based requirement
Expectations are derived from the Thermostat Events table, not static configuration or assumptions.

Zero is valid, blank is not

0.0 kWh is a legitimate outcome

Blank/null kWh indicates a data pipeline failure for required zones

No model comparison
The DQ gate does not consider:

“Just DC” values

Manual entries

Expected vs actual differences

Kitchen-specific tolerances

Explicit guardrail for missing telemetry
If no thermostat events exist for the day, the system emits WARN, not PASS, to avoid masking upstream event-logging failures.

8.3.3 Implementation Mechanism

The DQ gate is implemented as an Airtable Automation Script, scheduled once daily (typically early morning, after all overnight rollups have completed).

Inputs

Target date (default: yesterday, local time)

WX table daily record

Thermostat Events table records for the target date

Outputs (written to WX table)

Therm DQ Status — PASS, FAIL, or WARN

Therm DQ Score — numeric (0–100), derived mechanically from findings

Therm DQ Required Zones — zones inferred as required

Therm DQ Missing Zones — required zones with missing kWh

Therm DQ Negative Zones — required zones with invalid negative kWh

Therm DQ Notes — structured diagnostic summary

These fields are script-owned and must not be written by other producers.

8.3.4 Required Zone Derivation

For a given target date:

Collect all thermostat events with Date == targetDate

Extract the unique set of zones referenced by those events

Remove zones explicitly excluded from DQ enforcement (e.g., Guest Hall)

The remaining set becomes requiredZones

There is no static “always required” list in the active-only model.

8.3.5 Validation Rules

For each zone in requiredZones:

Missing:
Auto kWh field is blank or non-numeric → FAIL

Invalid:
Auto kWh < 0 → FAIL

Zones not in requiredZones are ignored entirely for DQ purposes.

8.3.6 Status Semantics
Status	Meaning
PASS	All required zones have valid (≥0) Auto kWh
FAIL	At least one required zone has missing or negative Auto kWh
WARN	No thermostat events found; DQ expectations cannot be inferred

A WARN day indicates telemetry ambiguity, not confirmed correctness.

8.3.6.1 Interpreting WARN on Unoccupied Days

A WARN status is emitted when no thermostat events are recorded for the target date, because the system cannot infer which zones were required.

This condition has two distinct real-world causes:

Telemetry ambiguity
An upstream logging or ingestion failure may have prevented thermostat events from being recorded.

Expected inactivity (unoccupied house)
The house was unoccupied and no thermostat setpoints or states changed during the day.

In the second case, a WARN is expected and benign.

Operational guidance:

If {Usage Type} indicates an unoccupied or low-interaction day (e.g., Empty: Only Kitchen, Empty: All, No Usage),
a DQ WARN due to zero events requires no action.

If WARN occurs on days where thermostat interaction was expected, investigate event ingestion.

This guardrail exists to avoid falsely emitting PASS when event telemetry is missing, not to signal data corruption.

8.3.7 Relationship to Confidence Score

The DQ gate and the Therm Confidence Score serve different roles:

Aspect	DQ Gate	Confidence Score
Purpose	Operational health	Analytical validation
Scope	Auto data only	Auto vs manual/model
Output	PASS / FAIL / WARN	0–100 score
Driver	Evidence (events)	Coverage + deviation
Alerting	Yes	No

A day may:

PASS DQ but have a low Confidence Score (model mismatch)

FAIL DQ even when confidence scoring is skipped

This separation is intentional and required.

8.3.8 Operational Use

Alerts should be driven exclusively by Therm DQ Status

Investigations start with Therm DQ Notes

Trend analysis continues to use the Confidence Score framework

Manual energy entry retirement decisions must rely on confidence trends, not DQ status.

8.3.9 Rationale for Active-Only Design

The active-only approach was selected because:

Not all zones are occupied daily

Off days legitimately produce zero or no activity

Static “expected zones” caused repeated false failures

Thermostat events provide objective evidence of intent to heat

This design ensures the DQ signal reflects system correctness, not household behavior.

## 8.4 Manual vs Auto Energy Semantics (Validation Context)
8.4.1 Purpose

This section documents a confirmed semantic distinction between manual energy values sourced from the Mysa app and automated energy values sourced from Home Assistant (HA). It exists to prevent misinterpretation of Validation outcomes and to clarify why numerical mismatches do not undermine system correctness or long-term efficiency monitoring.

8.4.2 Dual reporting in the Mysa app

For the same zone and day, the Mysa app reports two different kWh values, depending on UI context:

Zone Detail view (device-level)

Energy measured directly by the thermostat device.

Example: Entryway → Energy Total = 11.59 kWh (Dec 18, 2025)

Home → Breakdown view (allocation-level)

Mysa’s internally allocated per-zone energy.

Designed to sum cleanly to the home total.

Example: Albert CT → Entryway = 10.33 kWh (Dec 18, 2025)

These values are both valid within Mysa but represent different semantic quantities.

8.4.3 Definition of “Manual” in this system

Historically and by design, this system defines:

Manual kWh = Mysa Home → Breakdown view value

This choice reflects historical practice and ensures consistency across zones for a given day. Device-level Mysa values are not used as the manual baseline.

8.4.4 Implications for Validation results

Validation compares:

HA Auto (device-grounded energy measurement)

Manual (Mysa Home-level allocation)

Disagreements between these values indicate semantic differences between measurement models, not pipeline failures or data quality issues.

Accordingly:

Validation WARN/FAIL does not imply incorrect Auto data.

Data Quality (DQ) remains the sole indicator of pipeline health.

8.4.5 Relevance to system goals

The system’s primary objective is trend-based detection of efficiency degradation, not financial reconciliation.

For this objective:

Absolute daily agreement is unnecessary.

Stability and internal consistency of Auto measurements are paramount.

HA Auto values are therefore treated as authoritative for longitudinal analysis, even when they diverge from Mysa’s allocation-layer reporting.

8.4.6 Operational guidance

Do not tune Auto values to match Mysa Breakdown allocations.

Interpret Validation outcomes as context about manual-reference reliability.

Base operational decisions on trends over time, not single-day Validation results.

8.4.7 Interpreting Validation WARN and FAIL Statuses

The Thermostat Validation process compares Auto kWh (device-grounded measurement) against Manual kWh (Mysa Home-level allocation) for zones that are expected on a given day.

As a result:

A Validation WARN or FAIL does not indicate a data pipeline failure.

It does not imply incorrect automated measurements.

It reflects a semantic mismatch between two independently derived representations of energy usage.

Common, expected causes include:

Allocation differences on unoccupied or partially occupied days (e.g., Kitchen absorbing shared load)

Optional or infrequently used zones (e.g., Laundry, Guest Room)

Manual approximation or rounding

Legitimate physical behavior differences between zones

Operational guidance:

Validation results are informational and non-alerting by design.

Single-day WARN/FAIL outcomes should not prompt corrective action.

Validation is intended to be interpreted over time, looking for repeated zone-specific bias or drift.

Data Quality (DQ) remains the sole authority for determining whether automated data is trustworthy.

This separation ensures that validation highlights semantic disagreement without conflating it with system health.

8.4.8 Hybrid Validation Thresholds (Updated 2025-12-29)

**Context**

Initial validation used fixed absolute thresholds (PASS ≤0.20 kWh, FAIL >0.75 kWh) which proved too strict for high-consumption zones. A 2-3 kWh difference in a 30-40 kWh zone represents only 5-10% error—actually quite good accuracy—but was flagged as FAIL.

Analysis of validation data (December 2025) revealed:
- 82% FAIL rate on non-suspect days using old thresholds
- Average validation score: 62.7/100
- Multiple zones with legitimate 1-2 kWh differences marked as severe failures

**Updated Approach: Hybrid Thresholds**

Effective 2025-12-29, validation uses hybrid logic combining absolute (kWh) and percentage thresholds:

```
PASS:  ≤0.50 kWh  OR  ≤5%
FAIL:  >2.00 kWh  AND >15%
```

Key change: A zone must exceed **BOTH** thresholds to be marked SEVERE.

**Rationale**

The hybrid approach provides context-appropriate tolerance:
- Low-usage zones (0-5 kWh): protected by absolute threshold (0.50 kWh is significant)
- High-usage zones (20-40 kWh): protected by percentage threshold (2-3 kWh is only 5-10%)
- Genuinely problematic differences (>2 kWh AND >15%) still trigger FAIL

**Logic Flow**

For each zone comparison:
1. Calculate absolute difference (kWh)
2. Calculate percentage difference (%)
3. Classify:
   - **OK**: Passes absolute threshold OR percentage threshold
   - **WARN**: Exceeds one threshold but not both
   - **SEVERE**: Exceeds both thresholds

Record-level status:
- **PASS**: No SEVERE zones, no WARN zones
- **WARN**: One or more WARN zones, no SEVERE zones
- **FAIL**: One or more SEVERE zones

**Expected Impact**

Based on historical data (11 non-suspect days in December 2025):

| Metric | Old Thresholds | New Thresholds | Change |
|--------|---------------|----------------|--------|
| FAIL rate | 82% | 55% | -27% |
| WARN rate | 9% | 36% | +27% |
| PASS rate | 9% | 9% | No change |
| Avg score | 62.7 | 81.8 | +19.1 |

**Configurable Parameters**

The script accepts these input variables for threshold tuning:

```javascript
PASS_TOL_KWH: 0.50       // Absolute PASS threshold (kWh)
FAIL_TOL_KWH: 2.00       // Absolute FAIL threshold (kWh)
PASS_TOL_PERCENT: 5      // Percentage PASS threshold (%)
FAIL_TOL_PERCENT: 15     // Percentage FAIL threshold (%)
```

**Output Changes**

Validation notes now include percentage error for each zone:
```
- Stairs: manual=43.14 kWh, auto=45.79 kWh, diff=2.65 (abs 2.65, 5.8%)
```

This provides immediate context: Stairs shows 2.65 kWh difference but only 5.8% error—now correctly classified as OK rather than FAIL.

**Operational Guidance**

Days that FAIL under new thresholds have genuine data quality concerns:
- Multiple zones with 15%+ errors
- High absolute differences (>2 kWh) combined with high percentage errors (>15%)
- Indicates either measurement issues or Mysa app reporting failures

Days that receive WARN status:
- Have acceptable overall accuracy
- May show isolated zones with moderate differences
- Do not require immediate investigation

**Known Problem Patterns**

Analysis identified these persistent issues warranting investigation:
1. **Stairs zone**: Shows 10-40% variability across multiple days
2. **MANC zone**: Shows 20%+ errors on several days (Dec 20, 21, 27)
3. **Mysa app failures**: Dec 25 & 28 showed systematic 50-90% underreporting across all zones when app stopped mid-day reporting

**Relationship to Confidence Score**

The Thermostat Confidence Score (Section 9) remains unchanged and continues to use its own penalty logic. The confidence score and validation thresholds serve complementary purposes:
- **Validation thresholds**: Zone-level accuracy classification
- **Confidence score**: Aggregate health metric for trend analysis

Both remain informational and non-alerting.


## 9. Composite Confidence Score

A single numeric score summarizes system health:

```
Therm Confidence Score (0–100)
```

Properties:
- Empty / no-usage days → score = 100
- Requires minimum comparison coverage (≥5 zones)
- Penalizes:
  - Missing expected manual data
  - Low comparison coverage
  - Large non-Kitchen deltas
  - Extreme Kitchen-only deltas

This score is used for **trend analysis**, not alerts.

---

## 9.1 How to Interpret the Confidence Score Over Time

### 9.1.1 What the score means

- The score is a **row-level health summary**. It is most meaningful on days where `{Manual Expected?}=1` and `{kWh Comparison Count}≥5`.
- A score of **100** on empty/no-usage/testing days does **not** mean “perfect measurement”; it means “validation intentionally skipped.”

### 9.1.2 Recommended operational bands

Use these bands for interpretation (not strict pass/fail):

- **90–100 (Green):** System behaving consistently. Differences are within expected tolerance. 
- **75–89 (Yellow):** Acceptable but worth a glance. Often indicates either reduced comparison coverage or one moderate deviation.
- **50–74 (Orange):** Investigate. Typically driven by low coverage, missing expected manual data, or a non-Kitchen deviation.
- **0–49 (Red):** Not a usable validation day (missing manual data when expected) or a major divergence.

### 9.1.3 Trend-based interpretation (the actual goal)

The score is designed to be interpreted over **weeks**, not single days:

- **Stability test:** Scores should cluster within a narrow band on comparable usage types.
- **Drift test:** Watch for gradual degradation (e.g., a rolling average trending down over 2–3 weeks).
- **Repeat offender test:** If low scores correlate to the **same zone(s)** repeatedly (excluding Kitchen), treat that as actionable.

### 9.1.4 Suggested “ready to retire manual entry” criteria

A pragmatic criterion set (tune as desired):

- Consider only days where `{Manual Expected?}=1` and `{kWh Comparison Count}≥5`.
- Over any **rolling 14-day window**:
  - ≥80% of days score **≥85**, and
  - no more than 1 day scores **<75**, and
  - no repeated non-Kitchen FAIL pattern.

When the above holds for **2 consecutive windows**, manual entry is no longer providing new information.

---

## 10. Operational Risk Model

### 10.1 Data Loss Window

The only meaningful risk window is:

> **Recorder DB lost before daily rollup runs**

Mitigations:
- Multiple overnight runs
- Ability to backfill if recorder intact

Once written to Airtable, data is durable and independent of Home Assistant.

### 10.2 Internet vs Power Outage

- Internet outage: no data loss
- Short power outage: no data loss
- Machine failure + recorder loss: potential loss of un-materialized days only

### 10.3 HA Rollup Missing — Recovery Procedure

If the HA Rollup Missing alert fires:

Step 1 — Verify HA ingestion
Check Home Assistant logs
Confirm recorder database is present and recent
Confirm rollup scripts executed

Step 2 — Re-run HA rollup (if needed)
Trigger HA rollup manually or allow next retry window
Confirm {HA Rollup Present?} flips to 1

Step 3 — Re-run dependent automations (in order)
Therm State Changes
Derive Usage Type
Data Quality
Therm Zone Daily

All scripts are idempotent and safe to re-run.

Step 4 — Confirm clearance
ALERT view empty
No Slack alert next cycle
WX record fully populated

### 10.4 Auto kWh Backfill Policy (Mysa-Based Recovery)
as of 15/2025 this plan has not been operationalized. The plan is to do this some time in the future.

### 10.4.1 Purpose

This section defines the authoritative recovery procedure when Home Assistant (HA) telemetry is unavailable for one or more days due to host outage (e.g., Plex Mac mini down) and the HA recorder database cannot be used to reconstruct the missing day(s).

The objective is to restore continuity of the Auto kWh ledger so that downstream analytics, projections, and dashboards remain complete and operational.

This policy is explicitly operational, not semantic: it prioritizes continuity and recoverability over strict measurement-model purity.

### 10.4.2 Canonical Rule

Auto kWh fields represent the best available authoritative daily energy values.

Source precedence:

Primary source (normal operation):
Home Assistant daily rollup (device-grounded measurement)

Fallback source (outage recovery):
Mysa app → Home → Breakdown daily kWh values

When fallback is used, Auto fields are overwritten with Mysa values and the provenance must be explicitly recorded.

### 10.4.3 Preconditions for Using Mysa Backfill

Mysa backfill into Auto fields is permitted only if all of the following are true:

{HA Rollup Present?} = 0 for the target day

HA recorder database does not contain sufficient telemetry to re-run the daily rollup

The outage window is confirmed (e.g., host down, container stopped, disk failure)

If HA telemetry is still available, HA rollup must be re-run and Mysa backfill must not be used.

### 10.4.4 Required Fields (WX Table)

The following fields are required to support auditable backfill:

{Auto Source} (Single Select — Required)

Allowed values:

HA — Written by Home Assistant rollup

Mysa Backfill — Manually entered from Mysa Home → Breakdown

Mixed / Partial — Some zones HA, some zones Mysa

Unknown — Legacy or ambiguous provenance

{Auto Backfill Notes} (Long Text — Required when backfilled)

Freeform but concise justification, including:

Reason HA data is unavailable

Confirmation that Mysa Home → Breakdown was used

Any known caveats (partial day, app outage, etc.)

Example:

“HA down due to Plex outage; recorder unavailable. Auto kWh backfilled from Mysa Home → Breakdown.”

### 10.4.5 Backfill Procedure (Step-by-Step)

For each affected WX date:

Step 1 — Verify HA recovery is not possible

Confirm {HA Rollup Present?} = 0

Confirm recorder DB cannot reconstruct the day

Step 2 — Extract Mysa daily values

Open Mysa app

Navigate to Home → Breakdown

Select the target date

Record per-zone daily kWh values

Note: Device-level values (zone detail view) must not be used.
The Home → Breakdown view is the canonical fallback baseline.

Step 3 — Write Auto fields

Enter values directly into <Zone> KWH (Auto) fields

Do not populate manual-only fields

Leave HA-owned non-kWh artifacts (e.g., Thermostat Settings) unchanged unless explicitly required

Step 4 — Record provenance

Set {Auto Source} = Mysa Backfill

Populate {Auto Backfill Notes}

Step 5 — Close operational alerts

The HA Rollup Missing alert represents ingestion failure, not ledger completeness

Either:

acknowledge the alert operationally, or

filter alert views to exclude {Auto Source} = Mysa Backfill

The alert must not be treated as unresolved once backfill is complete.

### 10.4.6 Downstream Semantics
Data Quality (DQ) Gate

On backfilled days:

DQ PASS indicates Auto ledger completeness, not HA pipeline health

HA ingestion health is assessed separately via {HA Rollup Present?}

This distinction is intentional.

Analytics & Projections

Therm Zone Daily, efficiency metrics, and dashboards may include backfilled days

Dashboards should allow filtering or annotation by {Auto Source} where interpretation matters

Backfilled days are expected to be rare and operationally justified.

### 10.4.7 Prohibited Actions

Do not overwrite HA-written Auto values with Mysa values

Do not backfill if HA telemetry can be recovered

Do not leave provenance fields blank

Do not copy Mysa values into Manual-only fields when Auto fields are missing

### 10.4.8 Rationale

This policy accepts that:

HA Auto values and Mysa Breakdown values have different measurement semantics

During outages, continuity is more valuable than purity

Explicit provenance preserves analytical honesty

This approach allows the system to recover cleanly from host outages without architectural redesign, while keeping the system auditable and interpretable over time.

---

## 11. GitHub Roadmap (Planned)

Future evolution (non-urgent):

- HA publishes daily snapshot externally
- GitHub Actions materialize WX records
- HA becomes telemetry producer only

This further reduces local state risk.

---

## 12. System Status

- Daily rollup: stable
- Monitoring: operational
- Validation: in progress
- Manual entry retirement: pending confidence trends

- HA Rollup Missing Alert (Daily Watchdog)
Purpose

A daily watchdog automation verifies that HA ingestion completed for the prior day.
If not, it alerts the operator so corrective action can be taken before downstream analytics are trusted.

Airtable View (Alert Source)
View name: ALERT — HA Rollup Missing

Filter logic:
{datetime} is yesterday (America/New_York)
{HA Rollup Present?} = 0
This view represents:
“Yesterday’s WX record exists, but HA rollup never materialized.”

Automation Behavior
Trigger: Scheduled (daily)
Typical time: After all HA rollup retries should have completed (e.g., ~06:30am EST)

Action:
If record count > 0 → send Slack alert
Else → no action
Alert Semantics

This alert means one of the following:
HA ingestion did not run
HA ingestion ran but failed before writing to Airtable
Recorder data unavailable for the target window

It does not imply:
Bad energy data
Therm SP failure
Validation failure

It is strictly an ingestion-completeness guard.

2026-01-07 — Transient DNS / outbound connectivity interruption. Home Assistant logged repeated ClientConnectorDNSError (Met.no) and Network unreachable (HACS / HA alerts) errors following a container restart. Host networking and DNS remained functional; subsequent in-container testing confirmed outbound routing, DNS resolution, and HTTPS connectivity were healthy. Recorder database recovered cleanly (Ended unfinished session), no rollup failures were observed, and no Airtable ingestion gaps occurred. Errors ceased without configuration changes and did not recur after network stabilization. Treated as a transient DNS/upstream connectivity event during restart; no data loss.

---

**End of document**
