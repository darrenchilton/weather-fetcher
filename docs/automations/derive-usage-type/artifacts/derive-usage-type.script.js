/**
 * Usage Type Derivation — Airtable Automation Script
 *
 * Writes [Usage Type] on the WX record for a target date using:
 *   - {Therm SP Timeline (Derived)} JSON (authoritative for ON/OFF state)
 *   - Sum of "* KWH (Auto)" fields (only for "Enabled, No Heat Needed")
 *
 * Default targetDate: yesterday in TIME_ZONE (default America/New_York).
 *
 * Usage Types expected (Single select options):
 *   - Guests
 *   - Just DC
 *   - All
 *   - Empty House
 *   - Enabled, No Heat Needed
 *   - System Off
 *
 * Notes:
 *   - "ON" means: any segment has sp > 0
 *   - "OFF all day" means: every segment has sp == 0 (or zone missing segments => treated as OFF)
 *   - "System Off" means: all zones OFF all day
 */

async function main() {
  const cfg = input.config();

  // ========= TIME ZONE =========
  const TIME_ZONE =
    (typeof cfg.TIME_ZONE === "string" && cfg.TIME_ZONE.trim() !== "")
      ? cfg.TIME_ZONE.trim()
      : "America/New_York";

  // ========= CONFIG (adjust only if your base uses different names) =========
  const WX_TABLE = "WX";
  const WX_DATE_FIELD = "datetime"; // If your canonical identity field is "datetime", change here.
  const TIMELINE_FIELD = "Therm SP Timeline (Derived)";
  const USAGE_TYPE_FIELD = "Usage Type";

  // Zone names used in your rules
  const Z_MASTER = "Master";
  const Z_MANC = "MANC";
  const Z_GUEST_ROOM = "Guest Room";

  // kWh noise threshold for "Enabled, No Heat Needed"
  const KWH_EPS = 0.001;

  // ========= Target date =========
  // Allow automation input variable "targetDate" optionally (YYYY-MM-DD).
  const targetDate =
    (cfg.targetDate && String(cfg.targetDate).trim())
      ? String(cfg.targetDate).trim().slice(0, 10)
      : yesterdayYMD(TIME_ZONE);

  // ========= Load WX records =========
  const wx = base.getTable(WX_TABLE);
  const q = await wx.selectRecordsAsync();

  // Find the WX record for targetDate
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
    console.log(`[Usage Type] Missing ${TIMELINE_FIELD} on WX ${targetDate}. Leaving ${USAGE_TYPE_FIELD} unchanged.`);
    output.set("TIME_ZONE", TIME_ZONE);
    output.set("targetDate", targetDate);
    output.set("status", "MISSING_TIMELINE");
    return;
  }

  // Airtable may store JSON field as string; handle object/string.
  const timeline = (typeof timelineRaw === "string") ? safeJsonParse(timelineRaw) : timelineRaw;
  if (!timeline || typeof timeline !== "object") {
    console.log(`[Usage Type] Could not parse ${TIMELINE_FIELD} JSON on ${targetDate}. Leaving ${USAGE_TYPE_FIELD} unchanged.`);
    output.set("TIME_ZONE", TIME_ZONE);
    output.set("targetDate", targetDate);
    output.set("status", "BAD_TIMELINE_JSON");
    return;
  }

  // ========= Derive zone ON/OFF =========
  // ON: any segment sp > 0
  // OFF all day: all segments sp == 0 (or no segments)
  const zoneNames = Object.keys(timeline);
  const isOn = {};
  const isOffAllDay = {};

  for (const z of zoneNames) {
    const segs = Array.isArray(timeline[z]) ? timeline[z] : [];
    const anyOn = segs.some(s => Number(s?.sp) > 0);
    const allZero = (segs.length === 0) ? true : segs.every(s => Number(s?.sp) === 0);
    isOn[z] = anyOn;
    isOffAllDay[z] = allZero;
  }

  // Treat zones missing from JSON as OFF (conservative)
  const zoneOn = (z) => Boolean(isOn[z]);
  const zoneOffAllDay = (z) => (z in isOffAllDay) ? Boolean(isOffAllDay[z]) : true;

  const anyZoneOn = zoneNames.some(z => zoneOn(z));
  const allZonesOff = zoneNames.every(z => zoneOffAllDay(z));

  // ========= Compute total kWh (for warm-day enabled case) =========
  // Sum every numeric field that ends with " KWH (Auto)"
  let totalKwh = 0;
  for (const f of wx.fields) {
    if (!f.name.endsWith(" KWH (Auto)")) continue;
    const v = wxRec.getCellValue(f.name);
    const n = (typeof v === "number") ? v : (v == null ? 0 : Number(v));
    if (Number.isFinite(n)) totalKwh += n;
  }

  // ========= Classify =========
  let usageType = null;

  // 1) System Off: everything sp==0 all day
  if (allZonesOff) {
    usageType = "System Off";
  }
  // 2) Enabled, No Heat Needed
  else if (anyZoneOn && totalKwh <= KWH_EPS) {
    usageType = "Enabled, No Heat Needed";
  }
  // 3) Guests
  else if (zoneOn(Z_GUEST_ROOM)) {
    usageType = "Guests";
  }
  // 4) All
  else if (zoneOn(Z_MASTER) && zoneOn(Z_MANC)) {
    usageType = "All";
  }
  // 5) Just DC
  else if (zoneOn(Z_MASTER) && !zoneOn(Z_MANC)) {
    usageType = "Just DC";
  }
  // 6) Empty House
  else if (zoneOffAllDay(Z_MASTER) && zoneOffAllDay(Z_MANC)) {
    usageType = "Empty House";
  }
  // Fallback: leave unchanged
  else {
    console.log(`[Usage Type] No rule matched for ${targetDate}. Leaving ${USAGE_TYPE_FIELD} unchanged.`);
    output.set("TIME_ZONE", TIME_ZONE);
    output.set("targetDate", targetDate);
    output.set("status", "NO_RULE_MATCH");
    output.set("totalKwh", totalKwh);
    output.set("anyZoneOn", anyZoneOn);
    return;
  }

  // ========= Write result =========
  await wx.updateRecordAsync(wxRec, {
    [USAGE_TYPE_FIELD]: { name: usageType }
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

// DST-safe yesterday: anchor at UTC noon, then subtract one day, then format in TZ.
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

// Convert Airtable date field value to YYYY-MM-DD in TIME_ZONE
function dateFieldToYYYYMMDD(v, timeZone) {
  if (!v) return null;

  // Airtable date fields commonly come back as Date objects
  if (v instanceof Date) {
    return ymdInTZ(v, timeZone);
  }

  // If it's a string, it might already be YYYY-MM-DD or ISO
  if (typeof v === "string") {
    const s = v.trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
    const d = new Date(s);
    if (!isNaN(d.getTime())) return ymdInTZ(d, timeZone);
    return null;
  }

  // Some Airtable contexts return objects like {iso: "..."} or {dateTime: "..."}
  if (typeof v === "object") {
    if (v.iso) return String(v.iso).slice(0, 10);
    if (v.dateTime) return String(v.dateTime).slice(0, 10);
    if (v.value) return String(v.value).slice(0, 10);
  }

  return null;
}

await main();
