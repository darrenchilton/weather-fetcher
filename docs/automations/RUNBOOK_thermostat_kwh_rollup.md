# Thermostat kWh rollup (mutable truth)

## Purpose
Compute per-zone daily kWh from Home Assistant recorder history and write results into Airtable `WX` (`* KWH (Auto)` fields).

Key property: **mutable truth**. Historical days may be recomputed and overwritten as HA history changes.

## Runtime script vs repo script (authoritative execution)
Home Assistant executes the script inside the container path:

- **Runtime (authoritative for HA execution):**
  - Container: `/config/scripts/thermostat_rollup_m4_write_yesterday.py`
  - Host mount: `/Users/plex/homeassistant/config/scripts/thermostat_rollup_m4_write_yesterday.py`

- **Repo copy (source for development):**
  - `homeassistant/scripts/thermostat_rollup_write_yesterday.py`

Operational note: repo changes must be deployed/copied into `/config/scripts/` to affect the nightly run.

## Safety: writes are opt-in
Default behavior is dry-run.

Writes only occur when either:
- `WRITE_WX=1` environment variable is set, or
- `--write` flag is provided

## Recompute windows
### Nightly (recommended)
Nightly HA automation recomputes the last 3 days ending yesterday (local time).

Shell command (HA):
```yaml
shell_command:
  thermostat_rollup_write_yesterday: >-
    bash -lc 'WRITE_WX=1 python3 /config/scripts/thermostat_rollup_m4_write_yesterday.py --days-back 3 >> /config/thermostat_rollup_write.log 2>&1'





### Manual backfill / reconciliation
Recompute last N days ending yesterday (local):

```bash
docker exec homeassistant bash -lc 'WRITE_WX=1 python3 /config/scripts/thermostat_rollup_m4_write_yesterday.py --days-back N >> /config/thermostat_rollup_write.log 2>&1'

