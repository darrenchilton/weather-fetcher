# Weather Ingestion Schema — Visual Crossing + Open-Meteo (WX)

## Purpose
Define how WX rows are created/updated from weather providers, including forecast days.

---

## Visual Crossing ingestion (authoritative WX row creator)

### Script
- `weather_fetcher.py`

### API
- Base URL: `https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline`
- Params include (contractual):
  - `unitGroup = metric`
  - `include = days`

### Window semantics (normal run)
- start_date = today − 30 days
- end_date = today + 15 days

Result: WX rows are created for historical and future forecast days.

### Record identity
- Writes/uses `datetime` in WX with canonical `YYYY-MM-DD`.

### Update behavior
- Creates a record if the date is missing.
- Updates an existing record only when fields differ (field-level drift detection).

### Field contract
Visual Crossing writes the producer-owned weather fields listed in `AIRTABLE_WX_SCHEMA.md`.

Units: because `unitGroup=metric`, treat:
- temperatures: °C
- wind speed: km/h
- precip/snow: mm (provider semantics; document any conversion if later introduced)

---

## Open-Meteo enrichment (update-only)

### Scripts
- `openmeteo_fetcher.py` (fetch + normalize to `om_*`)
- updater (writes to Airtable)

### Forecast semantics
- `timezone = America/New_York`
- `forecast_days = 16`

### Match key
- Update-only: matches existing WX rows by `datetime` (`YYYY-MM-DD`).

### Field contract
Writes `om_*` fields listed in `AIRTABLE_WX_SCHEMA.md`.

### Temperature difference (VC - OM)
When both are present:
- `vc_temp` = WX `temp` (Visual Crossing; °C)
- `om_temp_f` = Open-Meteo Fahrenheit field

The system writes:
- `temp_difference = round(vc_temp - om_temp_f, 1)`

Note: this mixes units (°C minus °F). This is contractually “as implemented” today; if you want a unit-correct diff later, that would be a breaking semantic change requiring a version bump/backfill decision.

---

## Change control
Breaking:
- changing Visual Crossing `unitGroup` or key parameters
- changing the ingestion window semantics (30d/15d)
- changing the match key away from `datetime`
- changing units or meaning of existing fields without versioning
