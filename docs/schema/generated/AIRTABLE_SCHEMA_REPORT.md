# Airtable Schema Probe Report
- Generated (UTC): `2026-01-09T00:11:02.447999+00:00`
- Base ID: `appoTbBi5JDuMvJ9D`
- Raw base schema: `docs/schema/observed/airtable_base_schema_observed.json`
- Tables list: `docs/schema/observed/airtable_tables_observed.json`
- Manifest: `docs/schema/generated/airtable_schema_manifest.json`

## Extracted tables
### WX (tblhUuES8IxQyoBqe)
- Field count: 194
- Fields (by id): `docs/schema/observed/airtable_fields_tblhUuES8IxQyoBqe.json`
- Fields (by name): `docs/schema/observed/airtable_fields_wx.json`

| Field | Type |
|---|---|
| Date | formula |
| Test Phase | singleSelect |
| Day of Week | formula |
| Usage Type | singleSelect |
| Long Note | multilineText |
| Thermostat Settings (can delete after automations) | multilineText |
| All thermostat changes | rollup |
| Heat KwH | number |
| Therm KWH (Auto Total) | formula |
| Total Heat KWH (Calc) | formula |
| Run Data Validation (post manual entry) | checkbox |
| Den KWH | number |
| Entryway KWH | number |
| Guest Bath KWH | number |
| Guest Hall KWH | number |
| Guest Room KWH | number |
| Kitchen KWH | number |
| Laundry KWH | number |
| LR KWH | number |
| MANC KWH | number |
| Master KWH | number |
| Stairs KWH | number |
| Up Bath KWH | number |
| Heat Settings/Graph | multipleAttachments |
| AI Analysis Notes for Thermostat Changes | formula |
| Created | createdTime |
| Local WX Desc | formula |
| Update Thermostats | checkbox |
| datetime | date |
| p(KwH) | formula |
| Initial p(KwH) | number |
| p(KwH) Corrected | formula |
| Heat Prediction | formula |
| Heat Prediction (by type) | formula |
| temp | number |
| tempmax | number |
| tempmin | number |
| feelslikemax | number |
| feelslike | number |
| Feels min (F) | formula |
| Cover? | formula |
| feelslikemin | number |
| dew | number |
| humidity | number |
| precip | number |
| precipprob | number |
| precipcover | number |
| preciptype | singleLineText |
| snow | number |
| snowdepth | number |
| windgust | number |
| windspeed | number |
| winddir | number |
| sealevelpressure | number |
| cloudcover | number |
| visibility | number |
| solarradiation | number |
| solarenergy | number |
| uvindex | number |
| severerisk | number |
| sunrise | singleLineText |
| sunset | singleLineText |
| moonphase | number |
| conditions | multilineText |
| description | singleLineText |
| icon | singleLineText |
| stations | multilineText |
| Usage note | singleSelect |
| Up Main | formula |
| Month | formula |
| Year | formula |
| Winter 2022 Check 1 | formula |
| Winter 2022 Check 2 | formula |
| 13C Turn | singleSelect |
| Month-Year | formula |
| Link to Pwr Roll Up | multipleRecordLinks |
| Just DC Count | formula |
| All Count | formula |
| Guest Count | formula |
| Last Update | lastModifiedTime |
| Notes to Add | multipleLookupValues |
| Update note | multipleLookupValues |
| Dew Point Readings | multipleAttachments |
| Snow (inches) | formula |
| Loc | number |
| P(kwh) for Notifications | formula |
| No Use Count | formula |
| Feels F for notifications | formula |
| Predict Difference | formula |
| Usage Type Text | formula |
| Is Fire? | formula |
| Winter | formula |
| Temp Max (F) | formula |
| Temp Min (F) | formula |
| Test Counter | formula |
| p(KwH) (new) | formula |
| New Heat Prediction | formula |
| WeatherFactor | formula |
| New Heat Predictor Accuracy Check | formula |
| New Heat Predictor Accuracy Check copy | formula |
| Snow (Round) | formula |
| Min F (round) | formula |
| 2022 2024 Jan Feb | formula |
| UVAlert | formula |
| Vegetable Garden Journal | multipleRecordLinks |
| Precip (inches) | formula |
| Days to Today | formula |
| om_temp | number |
| om_temp_f | number |
| om_humidity | number |
| om_pressure | number |
| om_wind_speed | number |
| om_wind_speed_mph | number |
| temp_difference | number |
| Number | number |
| om_elevation | number |
| om_precipitation | number |
| om_data_timestamp | dateTime |
| om_weather_code | number |
| Local v Albany Temp Diff (F) | formula |
| temp (F) | formula |
| Local Precip (IN) | formula |
| Local Temp (F) | formula |
| Moderate or Heavier Precip? | formula |
| Time Stamp (EST) | formula |
| Usage Type Empty | formula |
| Snow Present? | formula |
| WX Rollups | multipleRecordLinks |
| Winter Period? | formula |
| Power/Heat Rollup | singleLineText |
| Stairs % | formula |
| om_snowfall | number |
| om_snowfall_6h | number |
| om_snow_depth | number |
| om_snowfall (inches) | formula |
| om_snow_6h (inches) | formula |
| Stairs KWH (Auto) | number |
| LR KWH (Auto) | number |
| Kitchen KWH (Auto) | number |
| Up Bath KWH (Auto) | number |
| MANC KWH (Auto) | number |
| Master KWH (Auto) | number |
| Den KWH (Auto) | number |
| Guest Hall KWH (Auto) | number |
| Laundry KWH (Auto) | number |
| Guest Bath KWH (Auto) | number |
| Entryway KWH (Auto) | number |
| Guest Room KWH (Auto) | number |
| Thermostat Settings (Auto) | multilineText |
| Data Source | singleLineText |
| Validation Notes (manual) | multilineText |
| HDD (18C) | formula |
| HA Rollup Present? | formula |
| Therm DQ Status | singleSelect |
| Therm DQ Score | number |
| Therm DQ Missing Zones | multilineText |
| Therm DQ Negative Zones | multilineText |
| Therm DQ Required Zones | multilineText |
| Therm DQ Notes | multilineText |
| Therm Validation Status | singleSelect |
| Therm Validation Score | number |
| Therm Validation Compared Zones | multilineText |
| Therm Validation Missing Manual Zones | multilineText |
| Therm Validation Missing Auto Zones | multilineText |
| Therm Validation Max Abs Diff | number |
| Therm Validation Mean Abs Diff | number |
| Therm Validation Notes | multilineText |
| Therm Validation Needs Review | checkbox |
| Therm Validation Last Run | dateTime |
| Therm kWh per HDD (Auto Total) | formula |
| Therm KWH (Auto Total Zones Present) | formula |
| Thermostat Events | multipleRecordLinks |
| Estimated Heating Cost (auto) | formula |
| Therm SP Start (Derived) | multilineText |
| Therm SP End (Derived) | multilineText |
| Therm SP Source (Derived) | multilineText |
| Therm SP Changes Count (Derived) | multilineText |
| Therm SP Stale Zones (Derived) | multilineText |
| Therm SP Summary (Derived) | multilineText |
| Therm SP Last Run | dateTime |
| Trigger Therm Stat Changes | checkbox |
| WX Changes | multipleRecordLinks |
| Temp Therm Calc | checkbox |
| Therm SP Timeline (Derived) | multilineText |
| Therm SP Setpoint-Hours (Derived) | multilineText |
| Therm SP Degree-Hours (Derived) | multilineText |
| Therm SP Degree-Hours by Setpoint (Derived) | multilineText |
| Therm Efficiency Index (Derived) | multilineText |
| Therm Zone Daily | multipleRecordLinks |
| HA Indoor Humidity Stats (Auto) | multilineText |
| HA Indoor Temperature Stats (Auto) | multilineText |
| HA Indoor Env Summary (Auto) | multilineText |
| HA Indoor Env Last Run (Auto) | dateTime |
| HA Indoor Env Human Summary (Auto) | multilineText |

### Thermostat Events (tblvd80WJDrMLCUfm)
- Field count: 17
- Fields (by id): `docs/schema/observed/airtable_fields_tblvd80WJDrMLCUfm.json`
- Fields (by name): `docs/schema/observed/airtable_fields_thermostat_events.json`

| Field | Type |
|---|---|
| Name | formula |
| WX | multipleRecordLinks |
| Previous Setpoint | number |
| New Setpoint | number |
| Thermostat | singleLineText |
| Timestamp | dateTime |
| Date | date |
| Change Type | singleLineText |
| Daily Summary | singleLineText |
| Created | createdTime |
| Notes | multilineText |
| Event ID | autoNumber |
| Date (YYYY-DD-MM) | formula |
| For WX Rolup | formula |
| Created time | createdTime |
| MM-YYYY | formula |
| Usage Type | multipleLookupValues |

### Therm Zone Daily (tbld4NkVaJZMXUDcZ)
- Field count: 15
- Fields (by id): `docs/schema/observed/airtable_fields_tbld4NkVaJZMXUDcZ.json`
- Fields (by name): `docs/schema/observed/airtable_fields_therm_zone_daily.json`

| Field | Type |
|---|---|
| Name | formula |
| Date | date |
| Zone | singleSelect |
| Key (Date|Zone) | formula |
| WX Record | multipleRecordLinks |
| kWh Auto | number |
| Degree Hours | number |
| Setpoint Hours | number |
| Efficiency Index | number |
| SP Source | singleSelect |
| SP Changes Count | number |
| DQ Status | singleSelect |
| Usage Type | singleSelect |
| Include in Trend? | formula |
| Rolling 7d EI | number |

