#!/usr/bin/env python3
import os
import sys
import csv
import json
import argparse
import subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

BASE_ID = "appoTbBi5JDuMvJ9D"
TBL_WX  = "tblhUuES8IxQyoBqe"  # WX
LOCAL_TZ = ZoneInfo("America/New_York")

ZONES_ORDER = [
    "Stairs", "LR", "Kitchen", "Up Bath", "MANC", "Master",
    "Den", "Guest Hall", "Laundry", "Guest Bath", "Entryway", "Guest Room"
]
ZONE_KWH_FIELD = {z: f"{z} KWH (Auto)" for z in ZONES_ORDER}

def eprint(*a):
    print(*a, file=sys.stderr)

def parse_args():
    ap = argparse.ArgumentParser(description="Read-only drift check: Thermostat KWH (Auto) recompute vs Airtable.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--days", type=int, help="Look back N days ending yesterday (local).")
    g.add_argument("--start-local", type=str, help="Start date YYYY-MM-DD (inclusive, local).")
    ap.add_argument("--end-local", type=str, help="End date YYYY-MM-DD (inclusive, local). Required if --start-local.")
    ap.add_argument("--abs-warn", type=float, default=0.15)
    ap.add_argument("--abs-fail", type=float, default=0.50)
    ap.add_argument("--pct-warn", type=float, default=0.05)
    ap.add_argument("--pct-fail", type=float, default=0.15)
    ap.add_argument("--rollup-script", default=os.path.expanduser("~/weather-fetcher/homeassistant/scripts/thermostat_rollup_write_yesterday.py"))
    return ap.parse_args()

def daterange_days(days: int):
    now = datetime.now(LOCAL_TZ)
    end = now.date() - timedelta(days=1)
    start = end - timedelta(days=days-1)
    d = start
    while d <= end:
        yield d.isoformat()
        d += timedelta(days=1)

def daterange_explicit(start_iso: str, end_iso: str):
    s = datetime.strptime(start_iso, "%Y-%m-%d").date()
    e = datetime.strptime(end_iso, "%Y-%m-%d").date()
    if e < s:
        raise ValueError("--end-local must be >= --start-local")
    d = s
    while d <= e:
        yield d.isoformat()
        d += timedelta(days=1)

def run_rollup_dry(rollup_script: str, date_iso: str):
    """
    Executes your thermostat rollup in dry-run mode for a specific local date.
    Returns: (wx_record_id, dict zone->kwh)
    """
    env = os.environ.copy()
    # Ensure we do NOT write. Your script already has dry-run default behavior in this mode.
    # If you later add a flag, we can pass it explicitly.
    cmd = [sys.executable, rollup_script, "--date-local", date_iso]
    p = subprocess.run(cmd, capture_output=True, text=True, env=env)
    out = p.stdout
    err = p.stderr

    if p.returncode != 0:
        raise RuntimeError(f"Rollup failed for {date_iso} (exit={p.returncode}).\nSTDOUT:\n{out}\nSTDERR:\n{err}")

    wx_id = None
    kwh = {}
    in_kwh_block = False

    for line in out.splitlines():
        if line.startswith("wx_record_id:"):
            wx_id = line.split(":", 1)[1].strip()
        if line.strip() in ("kwh_yesterday_by_zone:", "kwh_by_zone:"):
            in_kwh_block = True
            continue
        if in_kwh_block:
            if not line.startswith("- "):
                # end of block
                in_kwh_block = False
                continue
            # "- Stairs: 1.868"
            try:
                body = line[2:]
                zone, val = body.split(":", 1)
                kwh[zone.strip()] = float(val.strip())
            except Exception:
                continue

    if not wx_id:
        raise RuntimeError(f"Could not parse wx_record_id from rollup output for {date_iso}.")
    # Normalize missing zones to 0.0 for consistency
    for z in ZONES_ORDER:
        kwh.setdefault(z, 0.0)

    return wx_id, kwh

def airtable_get_wx_fields(wx_record_id: str):
    import requests
    token = os.getenv("AIRTABLE_TOKEN")
    if not token:
        raise RuntimeError("AIRTABLE_TOKEN is required for drift check.")

    url = f"https://api.airtable.com/v0/{BASE_ID}/{TBL_WX}/{wx_record_id}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json().get("fields", {})

def classify(delta_abs: float, delta_pct: float, abs_warn: float, abs_fail: float, pct_warn: float, pct_fail: float):
    if delta_abs >= abs_fail or delta_pct >= pct_fail:
        return "FAIL"
    if delta_abs >= abs_warn or delta_pct >= pct_warn:
        return "WARN"
    return "OK"

def main():
    a = parse_args()

    if a.start_local:
        if not a.end_local:
            raise SystemExit("ERROR: --end-local is required when using --start-local")
        dates = list(daterange_explicit(a.start_local, a.end_local))
        start_iso, end_iso = a.start_local, a.end_local
    else:
        dates = list(daterange_days(a.days))
        start_iso, end_iso = dates[0], dates[-1]

    out_dir = os.path.expanduser("~/weather-fetcher/reports/drift")
    os.makedirs(out_dir, exist_ok=True)

    csv_path = os.path.join(out_dir, f"thermostat_kwh_drift_{start_iso}_{end_iso}.csv")
    md_path  = os.path.join(out_dir, f"thermostat_kwh_drift_{start_iso}_{end_iso}.md")

    rows = []
    day_summaries = []

    for d in dates:
        wx_id, recomputed = run_rollup_dry(a.rollup_script, d)
        fields = airtable_get_wx_fields(wx_id)

        max_abs = 0.0
        max_pct = 0.0
        worst = None
        statuses = {"OK": 0, "WARN": 0, "FAIL": 0}

        for z in ZONES_ORDER:
            f = ZONE_KWH_FIELD[z]
            airtable_val = fields.get(f, None)
            # Airtable may store as int/float or be missing
            airtable_kwh = float(airtable_val) if airtable_val is not None else 0.0
            rec_kwh = float(recomputed.get(z, 0.0))
            delta = rec_kwh - airtable_kwh
            delta_abs = abs(delta)
            denom = airtable_kwh if airtable_kwh != 0 else (rec_kwh if rec_kwh != 0 else 1.0)
            delta_pct = (delta_abs / denom) if denom else 0.0

            st = classify(delta_abs, delta_pct, a.abs_warn, a.abs_fail, a.pct_warn, a.pct_fail)
            statuses[st] += 1

            if delta_abs > max_abs or (delta_abs == max_abs and delta_pct > max_pct):
                max_abs = delta_abs
                max_pct = delta_pct
                worst = z

            rows.append({
                "date_local": d,
                "wx_record_id": wx_id,
                "zone": z,
                "recomputed_kwh": f"{rec_kwh:.3f}",
                "airtable_kwh_auto": f"{airtable_kwh:.3f}",
                "delta_kwh": f"{delta:.3f}",
                "delta_pct": f"{(delta_pct*100):.2f}",
                "status": st,
            })

        day_status = "FAIL" if statuses["FAIL"] else ("WARN" if statuses["WARN"] else "OK")
        day_summaries.append((d, wx_id, day_status, worst, max_abs, max_pct))

        print(f"{d} wx={wx_id} status={day_status} worst={worst} max_abs={max_abs:.3f} max_pct={(max_pct*100):.2f}%")

    # Write CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # Write MD summary
    fail_days = [x for x in day_summaries if x[2] == "FAIL"]
    warn_days = [x for x in day_summaries if x[2] == "WARN"]

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Thermostat KWH Drift Report\n\n")
        f.write(f"Window: **{start_iso} → {end_iso}** (local)\n\n")
        f.write(f"Thresholds:\n")
        f.write(f"- WARN: abs≥{a.abs_warn} kWh OR pct≥{a.pct_warn*100:.1f}%\n")
        f.write(f"- FAIL: abs≥{a.abs_fail} kWh OR pct≥{a.pct_fail*100:.1f}%\n\n")
        f.write(f"Days checked: **{len(day_summaries)}**\n\n")
        f.write(f"- FAIL days: **{len(fail_days)}**\n")
        f.write(f"- WARN days: **{len(warn_days)}**\n\n")

        def write_list(title, items):
            f.write(f"## {title}\n\n")
            if not items:
                f.write("_None_\n\n")
                return
            for d, wx, st, worst, max_abs, max_pct in items:
                f.write(f"- {d} (wx={wx}) worst={worst} max_abs={max_abs:.3f} max_pct={(max_pct*100):.2f}%\n")
            f.write("\n")

        write_list("FAIL days", fail_days)
        write_list("WARN days", warn_days)

        f.write("## Files\n\n")
        f.write(f"- CSV: `{csv_path}`\n")
        f.write(f"- MD: `{md_path}`\n")

    print(f"\nWrote:\n- {csv_path}\n- {md_path}")

if __name__ == "__main__":
    main()

