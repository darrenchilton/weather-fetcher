#!/usr/bin/env python3
"""
All-up Airtable schema probe (READ-ONLY).

Writes:
- docs/schema/observed/airtable_base_schema_observed.json
- docs/schema/observed/airtable_tables_observed.json
- docs/schema/observed/airtable_fields_<table_id>.json
- docs/schema/observed/airtable_fields_<sanitized_table_name>.json
- docs/schema/generated/AIRTABLE_SCHEMA_REPORT.md
- docs/schema/generated/airtable_schema_manifest.json

Requires:
- AIRTABLE_TOKEN (PAT with schema.bases:read)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


DEFAULT_BASE_ID = "appoTbBi5JDuMvJ9D"
DEFAULT_TABLE_IDS = [
    "tblhUuES8IxQyoBqe",  # WX (from thermostat script)
    "tblvd80WJDrMLCUfm",  # Thermostat Events
    "tbld4NkVaJZMXUDcZ",  # Therm Zone Daily
]

META_TABLES_URL = "https://api.airtable.com/v0/meta/bases/{base_id}/tables"


def http_get_json(url: str, token: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def sanitize_filename(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "table"


def write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)


def write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def table_index(tables: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    by_id = {}
    by_name = {}
    for t in tables:
        tid = t.get("id")
        name = t.get("name")
        if tid:
            by_id[tid] = t
        if name:
            by_name[name] = t
    return by_id, by_name


def flatten_fields(table: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for fld in table.get("fields", []):
        out.append({
            "name": fld.get("name"),
            "type": fld.get("type"),
            # keep useful schema hints deterministic and small:
            "options": fld.get("options", None),
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-id", default=DEFAULT_BASE_ID)
    ap.add_argument(
        "--table-id",
        action="append",
        default=[],
        help="Airtable table ID to extract (repeatable). If omitted, uses WX + Thermostat Events + Therm Zone Daily defaults.",
    )
    ap.add_argument(
        "--table-name",
        action="append",
        default=[],
        help="Airtable table name to extract (repeatable). Optional; IDs are preferred.",
    )
    ap.add_argument("--observed-dir", default="docs/schema/observed")
    ap.add_argument("--generated-dir", default="docs/schema/generated")
    args = ap.parse_args()

    token = (os.environ.get("AIRTABLE_TOKEN") or "").strip()
    if not token:
        print("ERROR: AIRTABLE_TOKEN is not set. Provide a PAT with schema.bases:read.", file=sys.stderr)
        sys.exit(2)

    base_id = args.base_id
    url = META_TABLES_URL.format(base_id=base_id)
    schema = http_get_json(url, token)

    tables = schema.get("tables", [])
    by_id, by_name = table_index(tables)

    # Determine target tables
    target_ids = args.table_id[:] if args.table_id else DEFAULT_TABLE_IDS[:]
    target_names = args.table_name[:] if args.table_name else []

    selected: List[Dict[str, Any]] = []
    missing: List[str] = []

    for tid in target_ids:
        t = by_id.get(tid)
        if t:
            selected.append(t)
        else:
            missing.append(f"id:{tid}")

    for name in target_names:
        t = by_name.get(name)
        if t:
            # avoid duplicates if also selected by id
            if t.get("id") not in {x.get("id") for x in selected}:
                selected.append(t)
        else:
            missing.append(f"name:{name}")

    # Write base schema snapshot (raw)
    now = datetime.now(timezone.utc).isoformat()
    base_schema_path = os.path.join(args.observed_dir, "airtable_base_schema_observed.json")
    write_json(base_schema_path, schema)

    # Write a compact tables list
    tables_compact = [
        {"id": t.get("id"), "name": t.get("name"), "field_count": len(t.get("fields", []))}
        for t in tables
    ]
    tables_path = os.path.join(args.observed_dir, "airtable_tables_observed.json")
    write_json(tables_path, tables_compact)

    # Write per-table field inventories
    extracted_info = []
    for t in selected:
        tid = t.get("id") or "unknown"
        tname = t.get("name") or tid
        flat = flatten_fields(t)

        out_by_id = os.path.join(args.observed_dir, f"airtable_fields_{tid}.json")
        out_by_name = os.path.join(args.observed_dir, f"airtable_fields_{sanitize_filename(tname)}.json")
        write_json(out_by_id, flat)
        write_json(out_by_name, flat)

        extracted_info.append({
            "id": tid,
            "name": tname,
            "field_count": len(flat),
            "fields_file_by_id": out_by_id,
            "fields_file_by_name": out_by_name,
        })

    # Write manifest for drift tooling
    manifest = {
        "generated_utc": now,
        "base_id": base_id,
        "targets": {"table_ids": target_ids, "table_names": target_names},
        "missing_targets": missing,
        "tables_compact_file": tables_path,
        "base_schema_file": base_schema_path,
        "extracted": extracted_info,
    }
    manifest_path = os.path.join(args.generated_dir, "airtable_schema_manifest.json")
    write_json(manifest_path, manifest)

    # Write a human report
    lines = []
    lines.append("# Airtable Schema Probe Report\n")
    lines.append(f"- Generated (UTC): `{now}`\n")
    lines.append(f"- Base ID: `{base_id}`\n")
    lines.append(f"- Raw base schema: `{base_schema_path}`\n")
    lines.append(f"- Tables list: `{tables_path}`\n")
    lines.append(f"- Manifest: `{manifest_path}`\n\n")

    if missing:
        lines.append("## Missing requested tables\n")
        for m in missing:
            lines.append(f"- {m}\n")
        lines.append("\n")

    lines.append("## Extracted tables\n")
    for info in extracted_info:
        lines.append(f"### {info['name']} ({info['id']})\n")
        lines.append(f"- Field count: {info['field_count']}\n")
        lines.append(f"- Fields (by id): `{info['fields_file_by_id']}`\n")
        lines.append(f"- Fields (by name): `{info['fields_file_by_name']}`\n\n")

        # Print a short field list inline for quick scanning
        try:
            with open(info["fields_file_by_id"], "r", encoding="utf-8") as f:
                fld_list = json.load(f)
            lines.append("| Field | Type |\n")
            lines.append("|---|---|\n")
            for fld in fld_list:
                nm = fld.get("name", "")
                ty = fld.get("type", "")
                lines.append(f"| {nm} | {ty} |\n")
            lines.append("\n")
        except Exception as e:
            lines.append(f"_Could not inline fields: {e}_\n\n")

    report_path = os.path.join(args.generated_dir, "AIRTABLE_SCHEMA_REPORT.md")
    write_text(report_path, "".join(lines))

    print("OK: schema probe complete.")
    print(f"Wrote: {base_schema_path}")
    print(f"Wrote: {tables_path}")
    for info in extracted_info:
        print(f"Wrote: {info['fields_file_by_id']}")
        print(f"Wrote: {info['fields_file_by_name']}")
    print(f"Wrote: {manifest_path}")
    print(f"Wrote: {report_path}")

    if missing:
        sys.exit(10)


if __name__ == "__main__":
    main()
