#!/usr/bin/env python3
"""
ha_indoor_env_daily_write_yesterday.py

Purpose
- Pull a target local day (default: yesterday; override via --date-local) HA history for
  indoor humidity + temperature sensors (local midnight→midnight)
- Compute samples/min/max/avg per entity
- Write JSON payloads back into the existing Airtable WX record for that date
- Also write a human-friendly summary into one Long text field

Key behavior (robust / low-maintenance)
- By default, AUTO-DISCOVERS entities via /api/states:
    *_current_humidity
    *_current_temperature
- You can override discovery by setting:
    HUM_ENTITIES="sensor.a,sensor.b"
    TEMP_ENTITIES="sensor.c,sensor.d"

Credentials / configuration (aligned to your existing system)
- HA_BASE (required)   e.g. http://127.0.0.1:8123
- HA_TOKEN (required)  HA Long-lived access token
- Airtable token:
    - Prefer AIRTABLE_TOKEN env var
    - Else parse /config/configuration.yaml for: Authorization: "Bearer <token>"
- Airtable base:
    - AIRTABLE_BASE_ID env var, else defaults to appoTbBi5JDuMvJ9D
- Airtable table/fields:
    - AIRTABLE_TABLE (default "WX")
    - WX_DATE_FIELD  (default "datetime")

Write controls
- WRITE_WX=1 (default behavior if unset: WRITE)
- DISCOVER_ENTITIES=1: prints the discovered entity lists and exits (no Airtable write)

Data quality warnings (recommended)
- MIN_SAMPLES (default 24):
    Adds warnings to the summary and log for entities with 0 samples or < MIN_SAMPLES samples.

Airtable fields written (must exist in WX)
- HA Indoor Humidity Stats (Auto)        (Long text)
- HA Indoor Temperature Stats (Auto)     (Long text)
- HA Indoor Env Summary (Auto)           (Long text)
- HA Indoor Env Human Summary (Auto)     (Long text)   <-- NEW
- HA Indoor Env Last Run (Auto)          (Date/time or text)

Notes
- Uses HA /api/history/period with minimal_response=1 and no_attributes=1
- Ignores unknown/unavailable states
"""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo


# -----------------------------
# Defaults / constants
# -----------------------------

TZ_NAME_DEFAULT = "America/New_York"

# Same Airtable Base ID as your existing rollup scripts
BASE_ID_DEFAULT = "appoTbBi5JDuMvJ9D"

AIRT_HUM_FIELD = "HA Indoor Humidity Stats (Auto)"
AIRT_TEMP_FIELD = "HA Indoor Temperature Stats (Auto)"
AIRT_SUMMARY_FIELD = "HA Indoor Env Summary (Auto)"
AIRT_HUMAN_FIELD = "HA Indoor Env Human Summary (Auto)"  # NEW
AIRT_LASTRUN_FIELD = "HA Indoor Env Last Run (Auto)"

DISCOVER_HUM_RE = r"_current_humidity$"
DISCOVER_TEMP_RE = r"_current_temperature$"


# -----------------------------
# Helpers
# -----------------------------

@dataclass
class Stats:
    samples: int = 0
    min: Optional[float] = None
    max: Optional[float] = None
    sum: float = 0.0

    def add(self, x: float) -> None:
        self.samples += 1
        self.sum += x
        self.min = x if self.min is None else min(self.min, x)
        self.max = x if self.max is None else max(self.max, x)

    def as_dict(self) -> Dict[str, Any]:
        avg = (self.sum / self.samples) if self.samples else None
        return {
            "samples": self.samples,
            "min": self.min,
            "max": self.max,
            "avg": (round(avg, 4) if avg is not None else None),
        }


def require_env(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise SystemExit(f"ERROR: missing env var {name}")
    return v


def split_entities(env_name: str) -> List[str]:
    v = os.environ.get(env_name, "").strip()
    if not v:
        return []
    return [x.strip() for x in v.split(",") if x.strip()]


def read_token_from_config_yaml(path: str = "/config/configuration.yaml") -> Optional[str]:
    """
    Searches for: Authorization: "Bearer <token>"
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        m = re.search(r'Authorization:\s*"Bearer\s+([^\"]+)"', text)
        return m.group(1).strip() if m else None
    except Exception:
        return None


def local_midnight_window(target_local_date: date, tz: ZoneInfo) -> Tuple[datetime, datetime]:
    start = datetime.combine(target_local_date, time(0, 0, 0), tzinfo=tz)
    end = start + timedelta(days=1)
    return start, end


def to_utc_iso(dt: datetime) -> str:
    utc = dt.astimezone(ZoneInfo("UTC"))
    return utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def http_json(method: str, url: str, headers: Dict[str, str], body: Optional[Dict[str, Any]] = None) -> Any:
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, method=method, data=data)
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=90) as resp:
        raw = resp.read()
    return json.loads(raw)


def ha_history_url(base: str, start_utc_iso: str, end_utc_iso: str, entities: List[str]) -> str:
    base = base.rstrip("/")
    path = f"/api/history/period/{urllib.parse.quote(start_utc_iso)}"
    params = {
        "end_time": end_utc_iso,
        "filter_entity_id": ",".join(entities),
        "minimal_response": "1",
        "no_attributes": "1",
    }
    return f"{base}{path}?{urllib.parse.urlencode(params)}"


def extract_numeric_state(item: Any) -> Optional[float]:
    """
    HA history points (minimal_response) are dicts like:
      {"s": "34.2", "lu": "...", ...}
    Also handles {"state": "..."}.
    Ignores unknown/unavailable.
    """
    if item is None:
        return None

    s: Optional[str] = None
    if isinstance(item, dict):
        if "s" in item:
            s = item.get("s")
        elif "state" in item:
            s = item.get("state")
    elif isinstance(item, (int, float, str)):
        s = str(item)

    if s is None:
        return None

    s2 = str(s).strip().lower()
    if s2 in ("unknown", "unavailable", ""):
        return None

    try:
        return float(s2)
    except ValueError:
        return None


def compute_stats(history_payload: Any, entities: List[str]) -> Dict[str, Dict[str, Any]]:
    stats: Dict[str, Stats] = {e: Stats() for e in entities}

    if not isinstance(history_payload, list):
        raise SystemExit("ERROR: HA history response not a list")

    for timeline in history_payload:
        if not isinstance(timeline, list) or not timeline:
            continue

        first = timeline[0]
        entity_id = first.get("entity_id") if isinstance(first, dict) else None
        if not entity_id or entity_id not in stats:
            continue

        for point in timeline:
            val = extract_numeric_state(point)
            if val is None:
                continue
            stats[entity_id].add(val)

    return {eid: st.as_dict() for eid, st in stats.items()}


def discover_entities(ha_base: str, ha_token: str) -> Tuple[List[str], List[str]]:
    """
    Discover all entities matching the suffix patterns.
    """
    url = ha_base.rstrip("/") + "/api/states"
    states = http_json("GET", url, headers={"Authorization": f"Bearer {ha_token}"})

    temps = sorted(
        s.get("entity_id") for s in states
        if isinstance(s, dict) and re.search(DISCOVER_TEMP_RE, s.get("entity_id", ""))
    )
    hums = sorted(
        s.get("entity_id") for s in states
        if isinstance(s, dict) and re.search(DISCOVER_HUM_RE, s.get("entity_id", ""))
    )
    return [x for x in hums if x], [x for x in temps if x]


def build_warnings(stats: Dict[str, Dict[str, Any]], kind: str, min_samples: int) -> List[str]:
    warnings: List[str] = []
    for eid, st in stats.items():
        n = int(st.get("samples") or 0)
        if n == 0:
            warnings.append(f"{kind}:{eid}:NO_SAMPLES")
        elif n < min_samples:
            warnings.append(f"{kind}:{eid}:LOW_SAMPLES:{n}<{min_samples}")
    return warnings


def _friendly_entity_name(eid: str) -> str:
    s = eid
    if s.startswith("sensor."):
        s = s[len("sensor."):]
    s = s.replace("_", " ").strip()
    return s.title()


def _fmt_num(x: Any, decimals: int = 2) -> str:
    if x is None:
        return "—"
    try:
        return f"{float(x):.{decimals}f}"
    except Exception:
        return "—"


def build_human_summary(
    target_ymd: str,
    tz_name: str,
    start_utc: str,
    end_utc: str,
    hum_stats: Dict[str, Dict[str, Any]],
    temp_stats: Dict[str, Dict[str, Any]],
    warnings: List[str],
) -> str:
    lines: List[str] = []
    lines.append(f"Indoor Environment — {target_ymd} ({tz_name})")
    lines.append(f"Window (UTC): {start_utc} → {end_utc}")
    lines.append("")

    lines.append("Humidity (%)")
    for eid in sorted(hum_stats.keys()):
        st = hum_stats.get(eid, {}) or {}
        lines.append(
            f"- {_friendly_entity_name(eid)}: "
            f"min {_fmt_num(st.get('min'))}, avg {_fmt_num(st.get('avg'))}, max {_fmt_num(st.get('max'))} "
            f"(n={int(st.get('samples') or 0)})"
        )

    lines.append("")
    lines.append("Temperature (native units)")
    for eid in sorted(temp_stats.keys()):
        st = temp_stats.get(eid, {}) or {}
        lines.append(
            f"- {_friendly_entity_name(eid)}: "
            f"min {_fmt_num(st.get('min'))}, avg {_fmt_num(st.get('avg'))}, max {_fmt_num(st.get('max'))} "
            f"(n={int(st.get('samples') or 0)})"
        )

    if warnings:
        lines.append("")
        lines.append("Warnings")
        for w in warnings:
            lines.append(f"- {w}")

    return "\n".join(lines).strip() + "\n"


# -----------------------------
# Airtable
# -----------------------------

def airtable_find_wx_record(
    base_id: str,
    table: str,
    airtable_token: str,
    wx_date_field: str,
    target_ymd: str,
) -> str:
    """
    Find exactly one WX record for the target date (day-level match).
    """
    url = f"https://api.airtable.com/v0/{base_id}/{urllib.parse.quote(table)}"
    headers = {"Authorization": f"Bearer {airtable_token}"}

    formula = f"IS_SAME({{{wx_date_field}}}, '{target_ymd}', 'day')"
    params = {"filterByFormula": formula, "maxRecords": "2"}
    url = f"{url}?{urllib.parse.urlencode(params)}"

    resp = http_json("GET", url, headers)
    records = resp.get("records", [])
    if not records:
        raise SystemExit(f"ERROR: No WX record found for {target_ymd} (table={table}, field={wx_date_field})")
    if len(records) > 1:
        raise SystemExit(f"ERROR: Multiple WX records matched {target_ymd}; expected 1")
    return records[0]["id"]


def airtable_patch_record(
    base_id: str,
    table: str,
    airtable_token: str,
    record_id: str,
    fields: Dict[str, Any],
) -> None:
    url = f"https://api.airtable.com/v0/{base_id}/{urllib.parse.quote(table)}/{record_id}"
    headers = {
        "Authorization": f"Bearer {airtable_token}",
        "Content-Type": "application/json",
    }
    http_json("PATCH", url, headers, body={"fields": fields})


# -----------------------------
# Main
# -----------------------------

def main() -> None:
    print(
        "=== RUN START (UTC) ===",
        datetime.now(ZoneInfo("UTC")).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )
    print("=== SCRIPT IDENTITY ===")
    print({"file": __file__, "mtime": os.path.getmtime(__file__)})

    parser = argparse.ArgumentParser(description="HA Indoor Environment Daily Rollup")
    parser.add_argument(
        "--date-local",
        help="Target local date (YYYY-MM-DD). Defaults to yesterday in local timezone.",
    )
    args = parser.parse_args()

    tz = ZoneInfo(os.environ.get("TZ_NAME", TZ_NAME_DEFAULT))

    # HA (required env)
    ha_base = require_env("HA_BASE").rstrip("/")
    ha_token = require_env("HA_TOKEN")

    # Entity selection:
    hum_entities = split_entities("HUM_ENTITIES")
    temp_entities = split_entities("TEMP_ENTITIES")

    if not hum_entities or not temp_entities:
        auto_hums, auto_temps = discover_entities(ha_base, ha_token)
        if not hum_entities:
            hum_entities = auto_hums
        if not temp_entities:
            temp_entities = auto_temps

    if os.environ.get("DISCOVER_ENTITIES") == "1":
        print("=== DISCOVERED TEMPERATURE ENTITIES ===")
        print("\n".join(temp_entities) if temp_entities else "(none)")
        print("=== DISCOVERED HUMIDITY ENTITIES ===")
        print("\n".join(hum_entities) if hum_entities else "(none)")
        return

    if not hum_entities:
        raise SystemExit("ERROR: no humidity entities found (set HUM_ENTITIES or fix discovery pattern)")
    if not temp_entities:
        raise SystemExit("ERROR: no temperature entities found (set TEMP_ENTITIES or fix discovery pattern)")

    all_entities = hum_entities + temp_entities

    # Airtable token
    airtable_token = os.getenv("AIRTABLE_TOKEN") or read_token_from_config_yaml()
    if not airtable_token:
        raise SystemExit("ERROR: No Airtable token found in AIRTABLE_TOKEN or /config/configuration.yaml")

    airtable_base = os.getenv("AIRTABLE_BASE_ID", BASE_ID_DEFAULT)
    airtable_table = os.environ.get("AIRTABLE_TABLE", "WX")
    wx_date_field = os.environ.get("WX_DATE_FIELD", "datetime")

    # Target date (local)
    if args.date_local:
        try:
            target = date.fromisoformat(args.date_local)
        except ValueError:
            raise SystemExit("ERROR: --date-local must be YYYY-MM-DD")
    else:
        today_local = datetime.now(tz).date()
        target = today_local - timedelta(days=1)

    target_ymd = target.isoformat()

    start_local, end_local = local_midnight_window(target, tz)
    start_utc = to_utc_iso(start_local)
    end_utc = to_utc_iso(end_local)

    # Query HA history
    ha_url = ha_history_url(ha_base, start_utc, end_utc, all_entities)
    ha_headers = {
        "Authorization": f"Bearer {ha_token}",
        "Content-Type": "application/json",
    }
    payload = http_json("GET", ha_url, ha_headers)

    hum_stats = compute_stats(payload, hum_entities)
    temp_stats = compute_stats(payload, temp_entities)

    min_samples = int(os.getenv("MIN_SAMPLES", "24"))
    warnings: List[str] = []
    warnings += build_warnings(hum_stats, "humidity", min_samples)
    warnings += build_warnings(temp_stats, "temperature", min_samples)

    if warnings:
        print("=== WARNINGS ===")
        for w in warnings:
            print(w)

    # Find matching WX record and patch fields
    wx_id = airtable_find_wx_record(airtable_base, airtable_table, airtable_token, wx_date_field, target_ymd)

    now_utc = datetime.now(ZoneInfo("UTC")).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    fields: Dict[str, Any] = {
        AIRT_HUM_FIELD: json.dumps(
            {"date_local": target_ymd, "generated_utc": now_utc, "entities": hum_stats},
            separators=(",", ":"),
        ),
        AIRT_TEMP_FIELD: json.dumps(
            {"date_local": target_ymd, "generated_utc": now_utc, "entities": temp_stats},
            separators=(",", ":"),
        ),
        AIRT_HUMAN_FIELD: build_human_summary(
            target_ymd=target_ymd,
            tz_name=str(tz),
            start_utc=start_utc,
            end_utc=end_utc,
            hum_stats=hum_stats,
            temp_stats=temp_stats,
            warnings=warnings,
        ),
        AIRT_SUMMARY_FIELD: json.dumps(
            {
                "date_local": target_ymd,
                "generated_utc": now_utc,
                "humidity_avg": {eid: hum_stats.get(eid, {}).get("avg") for eid in hum_entities},
                "temperature_avg": {eid: temp_stats.get(eid, {}).get("avg") for eid in temp_entities},
                "counts": {"humidity_entities": len(hum_entities), "temperature_entities": len(temp_entities)},
                "min_samples": min_samples,
                "warnings": warnings,
            },
            separators=(",", ":"),
        ),
        AIRT_LASTRUN_FIELD: now_utc,
    }

    write_wx = os.getenv("WRITE_WX", "1") == "1"
    if write_wx:
        airtable_patch_record(airtable_base, airtable_table, airtable_token, wx_id, fields)

    print(
        json.dumps(
            {
                "ok": True,
                "write_wx": write_wx,
                "date_local": target_ymd,
                "wx_record_id": wx_id,
                "ha_url": ha_url,
                "humidity_entities_count": len(hum_entities),
                "temperature_entities_count": len(temp_entities),
                "min_samples": min_samples,
                "warnings_count": len(warnings),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
