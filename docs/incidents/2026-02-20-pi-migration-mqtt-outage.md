Incident Report — Pi Migration: MQTT Unavailability & Missing Rollups

Incident ID: 2026-02-20-pi-migration-mqtt
Date (Local): 2026-02-20 → 2026-02-21
Timezone: America/New_York
Severity: Data loss (thermostat telemetry + energy rollups)
Status: Resolved


Summary

Migration of Home Assistant from Mac Mini to Raspberry Pi 4 completed Feb 20, 2026.
Following cutover, all 12 thermostat climate entities showed "unavailable" in HA for most
of Feb 20. mysa2mqtt logs showed repeated "High interrupt rate / clientId collision"
warnings, causing the container to publish availability = offline for all devices.
Energy rollups for Feb 20 were written with severely incomplete data (~27 kWh vs expected
~50+ kWh). Feb 19 rollup was never written (Mac HA stopped before rollup window).

Additionally, the rollup scheduling automations were not present in automations.yaml
post-migration, so no scheduled rollups would have run regardless of MQTT status.
The HA long-lived access tokens in configuration.yaml were also stale (generated on Mac,
invalid on Pi).


Impact

Feb 19: fully missing rollup (Mac HA stopped before 00:30 rollup window)

Feb 20: partial rollup (~27 kWh written; thermostats unavailable most of day)

Feb 21 onward: first clean full day of recording

Setpoint change logging to Airtable: unaffected (automation was present and working)

No impact to weather fetcher or Airtable historical data


Root Cause

Primary: clientId collision on MQTT broker

The Mac Mini's Mosquitto broker (eclipse-mosquitto Docker container) was left running
after the Pi cutover. Although mysa2mqtt was stopped on the Mac, Mosquitto continued
listening on port 1883. mysa2mqtt on the Pi was generating MQTT clientIds that collided
with persistent sessions registered on the Mac broker (or the Mac broker itself was still
reachable and interfering). This caused mysa2mqtt to repeatedly interrupt its connection
and publish availability = offline for all devices.

Evidence:
  docker logs mysa2mqtt showed: "High interrupt rate (6/60s). Possible clientId collision.
  Regenerating clientId and resetting connection..."
  $SYS/broker/clients/connected showed 49 connected clients (abnormally high)
  After docker restart mysa2mqtt, devices came back online cleanly

Secondary: Missing rollup automations

The automations.yaml restored from Mac backup did not include the rollup scheduling
automation (thermostat_rollup_scheduled). Shell commands were defined in
configuration.yaml but nothing triggered them.

Tertiary: Stale HA access tokens

Long-lived tokens in configuration.yaml (lines 51 and 57) were generated on the Mac HA
instance and were rejected by the Pi HA instance with 401 Unauthorized. This would have
caused the ha_indoor_env_daily_write_yesterday.py script to fail even if triggered.


Detection

Manual inspection of Airtable WX table showed blank kWh fields for Feb 20.
HA device page for Den showed "became unavailable" event at 6:29 AM Feb 20.
mosquitto_sub on availability topics confirmed all devices were publishing "online" after
docker restart, ruling out mysa cloud connectivity as the cause.


Timeline (Local)

2026-02-19 → 2026-02-20: Mac HA stopped before rollup window (00:30 EST)
  → Feb 19 rollup never executed. Data unrecoverable.

2026-02-20 ~05:00: Pi cutover begins

2026-02-20 ~06:29: Den Thermostat (and all others) become unavailable in HA
  → mysa2mqtt experiencing clientId collisions with Mac Mosquitto still running

2026-02-20 (most of day): All climate entities unavailable; power sensors recording 0W

2026-02-21 ~22:00 (previous session): docker restart mysa2mqtt resolves clientId collision
  → All 12 devices publish availability = online
  → Live power readings confirmed (Master 667W, Guest Bath 382W, etc.)

2026-02-21 ~05:00: Remaining issues identified and fixed:
  → Mac Mosquitto stopped (docker stop mosquitto on Mac Mini)
  → Rollup automation added to automations.yaml
  → New HA access token generated; configuration.yaml updated on lines 51 and 57
  → Manual rollup run confirmed Airtable write working


Recovery Actions

MQTT Fix
  Stopped Mac Mini Mosquitto: docker stop mosquitto
  Restarted mysa2mqtt on Pi: docker restart mysa2mqtt
  Verified all 12 availability topics publishing "online" via mosquitto_sub

Rollup Automation Fix
  Added automation id: thermostat_rollup_scheduled to automations.yaml
  Triggers: 00:30, 02:00, 04:30 EST
  Calls: shell_command.thermostat_rollup_write_yesterday
  Reloaded automations via HA API

Token Fix
  Generated new long-lived token on Pi HA instance
  Replaced both stale tokens in configuration.yaml (lines 51 and 57) via sed

Verification
  Manual rollup run wrote Feb 20 partial data to Airtable (~27 kWh)
  Live dashboard confirmed all zones showing current power readings
  Automation count confirmed at 4 (grep -c "alias" automations.yaml)


Data Accounting

2026-02-19:
  data_completeness = missing
  missing_reason = Mac HA stopped before rollup window; Pi DB had no Feb 19 data

2026-02-20:
  data_completeness = partial
  kWh_written = ~27 (vs expected ~50+)
  missing_reason = MQTT unavailability from ~06:29; thermostats not recording power
  note = Migration day; one incomplete day is acceptable per migration plan

2026-02-21:
  data_completeness = full (first clean day)

No attempt was made to fabricate or backfill missing kWh.


Prevention & Follow-ups

Immediate

Ensure Mac Mosquitto is stopped as part of cutover checklist (add to migration runbook).
Verify rollup automations are present in automations.yaml post-migration before declaring
cutover complete.
Validate HA tokens in configuration.yaml immediately post-migration.

Medium Term

Add health check: alert if mysa2mqtt logs clientId collision warning more than once per hour.
Add rollup guardrail: flag if total kWh written is less than 10% of prior 7-day average.
Add automation count check to post-migration verification checklist.


Lessons Learned

Mac services must be fully stopped (not just HA and mysa2mqtt — also Mosquitto) before
Pi cutover is considered complete.

automations.yaml must be verified for rollup scheduling triggers, not just setpoint logging.

HA long-lived access tokens are instance-specific. Always regenerate on new instance.

Treat Airtable as the analytics system of record. Do not backfill fabricated data.
Migration day incomplete data is acceptable and expected.


Prepared by: Darren Chilton
Prepared on: 2026-02-21
