# Daily Data Contract — Airtable WX

## Purpose
Define the daily WX record as the atomic unit of storage and enrichment across producers.

## Identity (contractual)
- Airtable table: `WX` (`tblhUuES8IxQyoBqe`)
- Identity field: `datetime` (type: `date`)
- Canonical format: `YYYY-MM-DD` (local day in `America/New_York`)

## Uniqueness requirement
For each local day, there MUST be exactly one WX record such that:
- `IS_SAME({datetime}, '<date_local>', 'day')` is true.

If duplicates exist for the same day, the contract is violated.

## Create vs update authority (critical)
### Create authority
Only **Visual Crossing ingestion** (`weather_fetcher.py`) is permitted to create WX rows.

### Update-only producers
The following producers must never create WX records:
- Open-Meteo enrichment
- Home Assistant thermostat rollup
- Home Assistant indoor environment rollup
- Airtable automations (may create derived-table rows, not WX)

## Ingestion horizons
### Visual Crossing (WX creator)
Normal run covers a 45-day window:
- Historical: now − 30 days
- Forecast: now + 15 days
Result: WX rows exist for future forecast days.

### Open-Meteo (enrichment)
- Forecast horizon: 16 days
- Update-only: only updates days that already exist in WX.

## Idempotency
- Producers overwrite only the fields they own.
- Re-running the same producer for the same day is safe:
  - Weather ingestion updates only changed values.
  - HA rollups overwrite producer-owned fields for that date.
  - Open-Meteo overwrites its `om_*` fields for matching dates.

## Missing-row behavior
- If a WX row is missing for a date that an update-only producer tries to update:
  - The producer should log/alert and skip.
  - It must not create a row.

## Backfill semantics
- Weather ingestion inherently backfills the last 30 days on every run.
- Open-Meteo has optional history backfill tooling (update-only).
- HA rollups support `--date-local` backfill (update-only).

## Time window semantics (daily)
Daily window is local midnight → next local midnight in `America/New_York`.
- HA history reads convert the local window to UTC.
- Airtable queries match the day via the `datetime` date field.
