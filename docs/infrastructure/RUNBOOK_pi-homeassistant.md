# Raspberry Pi Infrastructure Runbook
# Albert Court — Home Assistant & mysa2mqtt
Last Updated: 2026-02-21


## Purpose

This document is the primary context document for debugging the Albert Court home
heating automation system. Paste this document at the start of any new debug session
to provide full system context without repeating history.


## Architecture

### Raspberry Pi 4 4GB (PRIMARY — Active)

OS: Home Assistant OS 17.1
HA Core: 2026.2.2
Role: Runs HA, MQTT broker, mysa2mqtt, rollup scripts
Access: SSH via Tailscale
SSH prompt: root@a0d7b954-ssh
HA URL: http://homeassistant.local:8123
Config path: /homeassistant/
Scripts path: /homeassistant/scripts/

### Mac Mini (STANDBY — Stopped)

Role: Emergency rollback only. Keep Docker containers intact for 30 days post-migration.
Status as of 2026-02-21: All containers stopped (homeassistant, mysa2mqtt, mosquitto)
Do not restart unless Pi completely fails.


## Services

### Mosquitto MQTT Broker
Type: HA add-on (not Docker)
Config: /homeassistant/mosquitto/mosquitto.conf
Auth: allow_anonymous true (no credentials needed)
Port: 1883

### mysa2mqtt
Type: Docker container
Image: bourquep/mysa2mqtt
Container name: mysa2mqtt
Function: Connects to Mysa cloud, publishes device state to local Mosquitto broker
Mysa account: darrenchilton@gmail.com

Start/restart:
  docker restart mysa2mqtt

Check logs:
  docker logs --tail 50 mysa2mqtt

Known warning: "High interrupt rate / clientId collision"
  Cause: Another process or stale MQTT session competing for the same clientId
  Fix: docker restart mysa2mqtt
  History: Was caused by Mac Mini Mosquitto still running post-migration (now stopped)


## Thermostat Zones

12 Mysa BB-V1-1 thermostats. All on MQTT via mysa2mqtt.

Zone         Device ID
-----------  ----------------
Stairs       a4cf1279a498
LR           a8032a16b2b0
Kitchen      a8032a16b248
Up Bath      ac67b207baac
MANC         a8032a16b2a4
Master       246f28cc1030
Den          a4cf1279a1f8
Guest Hall   ec94cb62f150
Laundry      a8032a164350
Guest Bath   246f28cc8d60
Entryway     94b97ee0478c
Guest Room   246f28ca32b8

MQTT availability topic pattern:
  mysa2mqtt/climate/{Zone}/{device_id}_climate/availability

HA entity ID pattern:
  climate.{zone}_thermostat  (e.g. climate.den_thermostat)

Check all availability topics:
  mosquitto_sub -h localhost -t 'mysa2mqtt/+/+/+/availability' -v -C 48


## Airtable Integration

Token:       REDACTED
Base ID:      appoTbBi5JDuMvJ9D
Tables:
  Setpoints (thermostat events): tblvd80WJDrMLCUfm
  Health monitoring:             tblIHXInJUxhwrzr4
  WX / daily energy rollup:     tblhUuES8IxQyoBqe

What writes to Airtable:
  1. Setpoint changes — automation airtable_log_thermostat_setpoint_changes
     fires on climate entity state change → rest_command.log_thermostat_event
  2. Daily kWh rollups — Python scripts scheduled via HA automations
  3. Health monitoring — logs broker/recorder/device availability events


## Rollup Scripts

Location: /homeassistant/scripts/
Primary script: thermostat_rollup_m4_write_yesterday.py

Schedule (defined in automations.yaml, id: thermostat_rollup_scheduled):
  00:30 EST
  02:00 EST
  04:30 EST
  Action: shell_command.thermostat_rollup_write_yesterday

Manual run (writes yesterday to Airtable):
  WRITE_WX=1 python3 /homeassistant/scripts/thermostat_rollup_m4_write_yesterday.py

Manual run with backfill (writes N days back):
  WRITE_WX=1 python3 /homeassistant/scripts/thermostat_rollup_m4_write_yesterday.py --days-back 2

Log file: /config/thermostat_rollup_write.log


## HA Long-Lived Access Token

Tokens are instance-specific. Always regenerate when migrating to a new HA instance.
Generate at: HA → Profile (bottom left) → Long-Lived Access Tokens

Current token (generated 2026-02-21 on Pi):
  eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJkNDg3MzM1MjgzNmY0NTZjYjcxMjhhMDM2MmMzYWIxOCIsImlhdCI6MTc3MTY3MDcyOSwiZXhwIjoyMDg3MDMwNzI5fQ.0AISwLikmUtHzW7VTnsOaF6ll5glCvTrfdf6aTHIWTM

Used in: configuration.yaml lines 51 and 57 (HA_TOKEN env var for Python scripts)

To update token after regeneration:
  sed -i 's/OLD_TOKEN/NEW_TOKEN/g' /homeassistant/configuration.yaml


## Key File Locations

File                    Path
----------------------  ----------------------------------------
Main config             /homeassistant/configuration.yaml
Automations             /homeassistant/automations.yaml
Scripts                 /homeassistant/scripts/
Rollup log              /config/thermostat_rollup_write.log
Indoor env log          /config/ha_indoor_env_write.log
Mosquitto config        /homeassistant/mosquitto/mosquitto.conf


## Quick Diagnostic Checklist

Run these in order when something seems wrong.

1. Is mysa2mqtt running?
   docker ps | grep mysa

2. Are thermostats publishing online?
   mosquitto_sub -h localhost -t 'mysa2mqtt/+/+/+/availability' -v -C 12

3. Any errors in mysa2mqtt?
   docker logs --tail 50 mysa2mqtt | grep -i "error\|warn\|offline"

4. Is rollup automation present?
   grep -c "thermostat_rollup_scheduled" /homeassistant/automations.yaml
   (should return 1)

5. Check rollup log
   tail -50 /config/thermostat_rollup_write.log

6. Is HA token valid?
   curl -s http://localhost:8123/api/ \
     -H "Authorization: Bearer TOKEN" | grep -c message
   (should return 1 if valid)


## Common Issues & Fixes

### Thermostats show "unavailable" in HA

Symptoms: All climate entities unavailable; power sensors showing 0W; kWh rollup blank

Diagnosis:
  docker logs --tail 50 mysa2mqtt | grep -i "collision\|offline"
  mosquitto_sub -h localhost -t 'mysa2mqtt/+/+/+/availability' -v -C 12

Fix:
  docker restart mysa2mqtt
  Wait 60 seconds, verify availability topics all show "online"

If collision persists, check for competing MQTT clients:
  mosquitto_sub -h localhost -t '$SYS/broker/clients/connected' -C 1
  (normal count is <10; >20 indicates collision or reconnect storm)

Check Mac Mini is fully stopped:
  SSH to Mac → docker ps (should show nothing mysa or homeassistant related)


### Rollup writes zeros or blanks to Airtable

Check 1 — Automation present:
  grep -c "thermostat_rollup_scheduled" /homeassistant/automations.yaml
  If 0, automation is missing. Add it to automations.yaml (see automation template below).

Check 2 — Token valid:
  grep -n "HA_TOKEN" /homeassistant/configuration.yaml
  Verify token matches current token in this document.

Check 3 — Thermostats were online:
  If thermostats were unavailable during the day, power sensors recorded nothing.
  Check HA device history for unavailability events.

Check 4 — Run manually and inspect output:
  WRITE_WX=1 python3 /homeassistant/scripts/thermostat_rollup_m4_write_yesterday.py


### curl commands fail with 401 Unauthorized

Token is wrong or expired. Regenerate in HA and update configuration.yaml.
See "HA Long-Lived Access Token" section above.


### curl paste corruption in terminal

Write to a script file instead of pasting long commands directly:
  cat > /tmp/cmd.sh << 'EOF'
  curl -s -X POST http://localhost:8123/api/services/automation/reload \
    -H "Authorization: Bearer TOKEN" \
    -H "Content-Type: application/json"
  EOF
  bash /tmp/cmd.sh


## Rollup Automation Template

If the rollup automation is missing from automations.yaml, append this block:

- id: thermostat_rollup_scheduled
  alias: "Thermostat Rollup: Scheduled Daily"
  mode: single
  trigger:
    - platform: time
      at: "00:30:00"
    - platform: time
      at: "02:00:00"
    - platform: time
      at: "04:30:00"
  action:
    - service: shell_command.thermostat_rollup_write_yesterday

Then reload:
  curl -s -X POST http://localhost:8123/api/services/automation/reload \
    -H "Authorization: Bearer TOKEN" \
    -H "Content-Type: application/json"


## Data Gap History

Date        Status    Notes
----------  --------  -------------------------------------------------------
2026-02-19  Missing   Mac HA stopped before rollup window; unrecoverable
2026-02-20  Partial   ~27 kWh written; MQTT unavailable most of day post-cutover
2026-02-21  Clean     First full day on Pi; MQTT issues resolved ~22:00 Feb 20


## Migration History

2026-02-20: Hard cutover from Mac Mini to Raspberry Pi 4
  - Fresh HA OS install on Pi
  - mysa2mqtt running as Docker container
  - Mosquitto running as HA add-on
  - Mac Mini Mosquitto stopped 2026-02-21 (should have been part of cutover)

Related incident: docs/incidents/2026-02-20-pi-migration-mqtt-outage.md
