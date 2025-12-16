#!/usr/bin/env python3
import os
import re
import sys
import json
import time
import requests
import sqlite3
from datetime import datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    print("ERROR: zoneinfo not available (need Python 3.9+).")
    sys.exit(1)

BASE_ID = "appoTbBi5JDuMvJ9D"
TBL_EVENTS = "tblvd80WJDrMLCUfm"   # Thermostat Events
TBL_WX     = "tblhUuES8IxQyoBqe"   # WX

LOCAL_TZ = ZoneInfo("America/New_York")
HA_DB_PATH = "/config/home-assistant_v2.db"

ZONES_ORDER = [
    "Stairs", "LR", "Kitchen", "Up Bath", "MANC", "Master",
    "Den", "Guest Hall", "Laundry", "Guest Bath", "Entryway", "Guest Room"
]

ZONE_DAILY_ENTITY = {
    "Stairs":     "sensor.stairs_energy_daily",
    "LR":         "sensor.lr_energy_daily",
    "Kitchen":    "sensor.kitchen_energy_daily",
    "Up Bath":    "sensor.up_bath_energy_daily",
    "MANC":       "sensor.manc_energy_daily",
    "Master":     "sensor.master_energy_daily",
    "Den":        "sensor.den_energy_daily",
    "Guest Hall": "sensor.guest_hall_energy_daily",
    "Laundry":    "sensor.laundry_energy_daily",
    "Guest Bath": "sensor.guest_bath_energy_daily",
    "Entryway":   "sensor.entryway_energy_daily",
    "Guest Room": "sensor.guest_room_energy_daily",
}

ZONE_KWH_FIELD = {z: f"{z} KWH (Auto)" for z in ZONES_ORDER}
TRACE_ID_LIMIT = 25


def read_token_from_config_yaml(path="/config/configuration.yaml"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        m = re.search(r'Authorization:\s*"Bearer\s+([^\"]+)"', text)
        return m.group(1).strip() if m else None
    except Exception:
        return None


def get_airtable_token():
    token = os.getenv("AIRTABLE_TOKEN")
    if token:
        return token.strip()
    token = read_token_from_config_yaml()
    if token:
        return token
    print("ERROR: No Airtable token found in AIRTABLE_TOKEN or /config/configuration.yaml")
    sys.exit(2)


def airtable_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def airtable_request(method, url, headers, **kwargs):
    last_exc = None
    for attempt in range(5):
        try:
            r = requests.request(method, url, headers=headers, timeout=30, **kwargs)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last_exc = e
            sleep = 2 ** attempt  # 1,2,4,8,16
            print(f"WARNING: Airtable request failed (attempt {attempt+1}/5). Retrying in {sleep}s. Error: {e}")
            time.sleep(sleep)
    raise last_exc


def iso_local_midnight_range_for_yesterday():
    now_local = datetime.now(LOCAL_TZ)
    target_date = (now_local.date() - timedelta(days=1))
    start_local = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=LOCAL_TZ)
    end_local = start_local + timedelta(days=1)
    return target_date.isoformat(), start_local, end_local


def dt_iso(dt: datetime) -> str:
    return dt.isoformat()


def classify_event(new_sp, prev_sp):
    try:
        new_v = float(new_sp)
        prev_v = float(prev_sp)
    except Exception:
        return "UNKNOWN"

    if new_v == 0 and prev_v > 0:
        return "TURNED_OFF"
    if prev_v == 0 and new_v > 0:
        return "TURNED_ON_RESTORE"
    if new_v != prev_v and new_v != 0 and prev_v != 0:
        return "SETPOINT_CHANGE"
    return "UNKNOWN"


def fetch_events(token, start_local, end_local):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_EVENTS}"
    formula = (
        "AND("
        f"{{Timestamp}} >= DATETIME_PARSE('{dt_iso(start_local)}'),"
        f"{{Timestamp}} <  DATETIME_PARSE('{dt_iso(end_local)}')"
        ")"
    )

    records = []
    offset = None
    while True:
        params = {"filterByFormula": formula, "pageSize": 100}
        if offset:
            params["offset"] = offset

        r = airtable_request("GET", url, airtable_headers(token), params=params)
        data = r.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break

    return records


def find_wx_record_for_date(token, target_date_iso):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_WX}"
    formula = f"IS_SAME({{datetime}}, '{target_date_iso}', 'day')"

    r = airtable_request(
        "GET",
        url,
        airtable_headers(token),
        params={"filterByFormula": formula, "pageSize": 10},
    )
    recs = r.json().get("records", [])

    if not recs:
        raise RuntimeError(f"No WX record found for {target_date_iso} (IS_SAME on {{datetime}}).")

    if len(recs) > 1:
        ids = [rr["id"] for rr in recs]
        raise RuntimeError(f"Multiple WX records found for {target_date_iso}: {ids}")

    return recs[0]["id"]


def build_summary(target_date_iso, events):
    totals = {"SETPOINT_CHANGE": 0, "TURNED_OFF": 0, "TURNED_ON_RESTORE": 0, "UNKNOWN": 0}
    per_zone = {
        z: {"SETPOINT_CHANGE": 0, "TURNED_OFF": 0, "TURNED_ON_RESTORE": 0, "UNKNOWN": 0, "ids": []}
        for z in ZONES_ORDER
    }
    zones_active = set()

    normalized = []
    for rec in events:
        rid = rec.get("id")
        f = rec.get("fields", {})
        zone = f.get("Thermostat")
        ts = f.get("Timestamp")
        new_sp = f.get("New Setpoint")
        prev_sp = f.get("Previous Setpoint")

        etype = classify_event(new_sp, prev_sp)
        normalized.append((ts, zone, etype, rid))

        totals[etype] = totals.get(etype, 0) + 1

        if zone:
            zones_active.add(zone)
            if zone not in per_zone:
                per_zone[zone] = {"SETPOINT_CHANGE": 0, "TURNED_OFF": 0, "TURNED_ON_RESTORE": 0, "UNKNOWN": 0, "ids": []}
            per_zone[zone][etype] = per_zone[zone].get(etype, 0) + 1
            if rid:
                per_zone[zone]["ids"].append(rid)

    normalized.sort(key=lambda x: (x[0] or "", x[1] or "", x[2] or ""))

    ordered_active = [z for z in ZONES_ORDER if z in zones_active]
    for z in sorted(zones_active):
        if z not in ordered_active:
            ordered_active.append(z)

    lines = []
    lines.append(f"Thermostat activity for {target_date_iso}")
    lines.append("")
    lines.append(f"Total events: {len(events)}")
    lines.append(f"Zones active: {', '.join(ordered_active) if ordered_active else '(none)'}")
    lines.append("")
    lines.append("Event breakdown:")
    lines.append(f"- Setpoint changes: {totals.get('SETPOINT_CHANGE', 0)}")
    lines.append(f"- Turned OFF (New=0): {totals.get('TURNED_OFF', 0)}")
    lines.append(f"- Turned ON restore (Prev=0): {totals.get('TURNED_ON_RESTORE', 0)}")
    if totals.get("UNKNOWN", 0):
        lines.append(f"- Unknown: {totals.get('UNKNOWN', 0)}")

    lines.append("")
    lines.append("Per-zone rollup (counts):")
    for z in list(per_zone.keys()):
        d = per_zone[z]
        c_sum = d.get("SETPOINT_CHANGE", 0) + d.get("TURNED_OFF", 0) + d.get("TURNED_ON_RESTORE", 0) + d.get("UNKNOWN", 0)
        if c_sum == 0:
            continue

        lines.append(
            f"- {z}: setpoint={d.get('SETPOINT_CHANGE', 0)}, "
            f"off={d.get('TURNED_OFF', 0)}, "
            f"on_restore={d.get('TURNED_ON_RESTORE', 0)}"
            + (f", unknown={d.get('UNKNOWN', 0)}" if d.get("UNKNOWN", 0) else "")
        )

        ids = d.get("ids", [])
        if ids:
            show = ids[:TRACE_ID_LIMIT]
            more = len(ids) - len(show)
            suffix = f" (+{more} more)" if more > 0 else ""
            lines.append(f"  Trace IDs: {', '.join(show)}{suffix}")

    return "\n".join(lines)


def _local_to_utc_ts(dt_local: datetime) -> float:
    return dt_local.astimezone(ZoneInfo("UTC")).timestamp()


def read_yesterday_daily_kwh_from_db(start_local: datetime, end_local: datetime):
    if not os.path.exists(HA_DB_PATH):
        raise FileNotFoundError(f"HA DB not found at {HA_DB_PATH}")

    start_utc_ts = _local_to_utc_ts(start_local)
    end_utc_ts = _local_to_utc_ts(end_local)

    con = sqlite3.connect(HA_DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute("SELECT metadata_id, entity_id FROM states_meta")
    meta = {row["entity_id"]: row["metadata_id"] for row in cur.fetchall()}

    out = {}
    for zone, ent in ZONE_DAILY_ENTITY.items():
        try:
            mid = meta.get(ent)
            if not mid:
                out[zone] = None
                continue

            cur.execute(
                """
                SELECT state, last_updated_ts
                FROM states
                WHERE metadata_id = ?
                  AND last_updated_ts >= ?
                  AND last_updated_ts <  ?
                  AND state NOT IN ('unknown','unavailable')
                ORDER BY last_updated_ts DESC
                LIMIT 1
                """,
                (mid, start_utc_ts, end_utc_ts),
            )
            row = cur.fetchone()
            out[zone] = round(float(row["state"]), 3) if row else None
        except Exception as e:
            print(f"ERROR: kWh read failed for {zone}: {e}")
            out[zone] = None

    con.close()
    return out


def update_wx_record(token, wx_record_id, summary_text, kwh_by_zone, write_wx: bool):
    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_WX}/{wx_record_id}"

    fields = {
        "Thermostat Settings (Auto)": summary_text,
        "Data Source": "Auto",
    }

    for zone, kwh in kwh_by_zone.items():
        if kwh is None:
            continue
        fields[ZONE_KWH_FIELD[zone]] = kwh

    payload = {"fields": fields}

    if not write_wx:
        print("DRY RUN (no WX write). Would PATCH:")
        print(json.dumps(payload, indent=2))
        return {"dry_run": True}

    r = airtable_request("PATCH", url, airtable_headers(token), data=json.dumps(payload))
    return r.json()


def main():
    write_wx = os.getenv("WRITE_WX", "0") == "1"
    token = get_airtable_token()
    target_date_iso, start_local, end_local = iso_local_midnight_range_for_yesterday()

    print(f"target_date_local: {target_date_iso}")
    print(f"mode: {'WRITE_WX=1 (will update WX)' if write_wx else 'dry-run (no WX writes)'}")

    events = fetch_events(token, start_local, end_local)
    print(f"events_fetched: {len(events)}")

    try:
        wx_record_id = find_wx_record_for_date(token, target_date_iso)
    except Exception as e:
        print(f"ERROR: WX lookup failed: {e}")
        sys.exit(3)

    print(f"wx_record_id: {wx_record_id}")

    summary_text = build_summary(target_date_iso, events)

    kwh_by_zone = read_yesterday_daily_kwh_from_db(start_local, end_local)
    missing = [z for z, v in kwh_by_zone.items() if v is None]

    print("kwh_yesterday_by_zone:")
    for z in ZONES_ORDER:
        print(f"- {z}: {kwh_by_zone.get(z)}")

    if missing:
        print(f"WARNING: missing kWh for zones: {', '.join(missing)}")
        summary_text += (
            "\n\nkWh note: One or more zones have no kWh for this date. "
            "This is expected if energy meters were added after the target date, "
            "or if recorder history is missing for the daily energy sensors."
        )

    print("summary_preview_start")
    print(summary_text)
    print("summary_preview_end")

    _ = update_wx_record(token, wx_record_id, summary_text, kwh_by_zone, write_wx)
    print("wx_update: OK" if write_wx else "wx_update: SKIPPED (dry run)")

    run_summary = {
        "rollup": "thermostat",
        "date": target_date_iso,
        "events_fetched": len(events),
        "kwh_present": sum(1 for v in kwh_by_zone.values() if v is not None),
        "kwh_missing": sum(1 for v in kwh_by_zone.values() if v is None),
        "wx_record_id": wx_record_id,
        "write_mode": bool(write_wx),
    }
    print("run_summary_json:")
    print(json.dumps(run_summary, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
