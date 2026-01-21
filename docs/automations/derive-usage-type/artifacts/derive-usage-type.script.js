/**
 * Usage Type Derivation — Airtable Automation Script
 *
 * Threshold logic:
 *   - "ON" means: any segment has sp > 7
 *   - "OFF all day" means: every segment has sp <= 7 (or zone missing segments => treated as OFF)
 *   - "System Off" means: all zones OFF all day
 */

async function main() {
  const cfg = input.config();

  // ========= TIME ZONE =========
  const TIME_ZONE =
    (typeof cfg.TIME_ZONE === "string" && cfg.TIME_ZONE.trim() !== "")
      ? cfg.TIME_ZONE.trim()
      : "America/New_York";

  // ========= CONFIG =========
  const WX_TABLE = "WX";
  const WX_DATE_FIELD = "datetime";
  const TIMELINE_FIELD = "Therm SP Timeline (Derived)";
  const USAGE_TYPE_FIELD_NAME = "Usage Type"; // used only to look up field id

  // Zone names used in your rules
  const Z_MASTER = "Master";
  const Z_MANC = "MANC";
  const Z_GUEST_ROOM = "Guest Room";

  // Treat sp <= 7 as OFF (low hold). Treat sp > 7 as ON.
  const SP_ON_MIN = 7;

  // kWh noise threshold for "Enabled, No Heat Needed"
  const KWH_EPS = 0.001;

  // ========= Target date =========
  const targetDate =
    (cfg.targetDate && String(cfg.targetDate).trim())
      ? String(cfg.targetDate).trim().slice(0, 10)
      : yesterdayYMD(TIME_ZONE);

  // ========= Load WX records =========
  const wx = base.getTable(WX_TABLE);
  const usageField = wx.getField(USAGE_TYPE_FIELD_NAME); // ensures field exists + gives stable id

  const q = await wx.selectRecordsAsync();

  const wxRec = q.records.find(r =>
    dateFieldToYYYYMMDD(r.getCellValue(WX_DATE_FIELD), TIME_ZONE) === targetDate
  );

  if (!wxRec) {
    console.log(`[Usage Type] No WX record found where ${WX_DATE_FIELD} == ${targetDate}`);
    output.set("TIME_ZONE", TIME_ZONE);
    output.set("targetDate", targetDate);
    output.set("status", "NO_WX_RECORD");
    return;
  }

  const timelineRaw = wxRec.getCellValue(TIMELINE_FIELD);
  if (!timelineRaw) {
    console.log(`[Usage Type] Missing ${TIMELINE_FIELD} on WX ${targetDate}. Leaving unchanged.`);
    output.set("TIME_ZONE", TIME_ZONE);
    output.set("targetDate", targetDate);
    output.set("status", "MISSING_TIMELINE");
    return;
  }

  const timeline = (typeof timelineRaw === "string") ? safeJsonParse(timelineRaw) : timelineRaw;
  if (!timeline || typeof timeline !== "object") {
    console.log(`[Usage Type] Could not parse ${TIMELINE_FIELD} JSON on ${targetDate}. Leaving unchanged.`);
    output.set("TIME_ZONE", TIME_ZONE);
    output.set("targetDate", targetDate);
    output.set("status", "BAD_TIMELINE_JSON");
    return;
  }

  // ========= Derive zone ON/OFF =========
  const zoneNames = Object.keys(timeline);
  const isOn = {};
  const isOffAllDay = {};

  for (const z of zoneNames) {
    const segs = Array.isArray(timeline[z]) ? timeline[z] : [];

    const anyOn = segs.some(s => Number(s?.sp) > SP_ON_MIN);
    const offAllDay =
      (segs.length === 0)
        ? true
        : segs.every(s => Number(s?.sp) <= SP_ON_MIN);

    isOn[z] = anyOn;
    isOffAllDay[z] = offAllDay;
  }

  // Treat zones missing from JSON as OFF (conservative)
  const zoneOn = (z) => Boolean(isOn[z]);
  const zoneOffAllDay = (z) => (z in isOffAllDay) ? Boolean(isOffAllDay[z]) : true;

  const anyZoneOn = zoneNames.some(z => zoneOn(z));
  const allZonesOff = zoneNames.every(z => zoneOffAllDay(z));

  // ========= Compute total kWh =========
  let totalKwh = 0;
  for (const f of wx.fields) {
    if (!f.name.endsWith(" KWH (Auto)")) continue;
    const v = wxRec.getCellValue(f.name);
    const n = (typeof v === "number") ? v : (v == null ? 0 : Number(v));
    if (Number.isFinite(n)) totalKwh += n;
  }

  // ========= Classify =========
  let usageType = null;

  if (allZonesOff) {
    usageType = "System Off";
  } else if (anyZoneOn && totalKwh <= KWH_EPS) {
    usageType = "Enabled, No Heat Needed";
  } else if (zoneOn(Z_GUEST_ROOM)) {
    usageType = "Guests";
  } else if (zoneOn(Z_MASTER) && zoneOn(Z_MANC)) {
    usageType = "All";
  } else if (zoneOn(Z_MASTER) && !zoneOn(Z_MANC)) {
    usageType = "Just DC";
  } else if (zoneOffAllDay(Z_MASTER) && zoneOffAllDay(Z_MANC)) {
    usageType = "Empty House";
  } else {
    console.log(`[Usage Type] No rule matched for ${targetDate}. Leaving unchanged.`);
    output.set("TIME_ZONE", TIME_ZONE);
    output.set("targetDate", targetDate);
    output.set("status", "NO_RULE_MATCH");
    output.set("totalKwh", totalKwh);
    output.set("anyZoneOn", anyZoneOn);
    return;
  }

  // ========= Write result (use field ID to avoid any name parsing/paste issues) =========
  await wx.updateRecordAsync(wxRec, {
    [usageField.id]: { name: usageType }
  });

  console.log(`[Usage Type] ${targetDate}: set to "${usageType}" (totalKwh=${totalKwh.toFixed(3)}, anyZoneOn=${anyZoneOn})`);

  output.set("TIME_ZONE", TIME_ZONE);
  output.set("targetDate", targetDate);
  output.set("status", "OK");
  output.set("usageType", usageType);
  output.set("totalKwh", totalKwh);
  output.set("anyZoneOn", anyZoneOn);
}

// ---------- Helpers ----------

function ymdInTZ(date, timeZone) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function yesterdayYMD(timeZone) {
  const now = new Date();
  const today = ymdInTZ(now, timeZone);
  const [y, m, d] = today.split("-").map(Number);
  const utcNoon = new Date(Date.UTC(y, m - 1, d, 12, 0, 0));
  utcNoon.setUTCDate(utcNoon.getUTCDate() - 1);
  return ymdInTZ(utcNoon, timeZone);
}

function safeJsonParse(s) {
  try { return JSON.parse(s); } catch { return null; }
}

function dateFieldToYYYYMMDD(v, timeZone) {
  if (!v) return null;

  if (v instanceof Date) {
    return ymdInTZ(v, timeZone);
  }

  if (typeof v === "string") {
    const s = v.trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    const d = new Date(s);
    if (!isNaN(d.getTime())) return ymdInTZ(d, timeZone);
    return null;
  }

  if (typeof v === "object") {
    if (v.iso) return String(v.iso).slice(0, 10);
    if (v.dateTime) return String(v.dateTime).slice(0, 10);
    if (v.value) return String(v.value).slice(0, 10);
  }

  return null;
}

await main();
