/**
 * Thermostat Data Quality Check (Active-Only) — Airtable Automation Script
 *
 * Purpose:
 *   Data-quality PASS/FAIL based ONLY on zones that were ACTIVE (had thermostat events)
 *   for the target date. No “Just DC”, no expected-vs-auto comparisons.
 *
 * Trigger:
 *   Airtable Automation -> Scheduled (e.g., daily 06:45)
 *
 * Inputs (Automation script input variables):
 *   - targetDate (optional): "YYYY-MM-DD". If omitted, uses yesterday (local).
 */

// -------------------- INPUTS --------------------
const cfg = input.config();
const explicitTargetDate = (cfg.targetDate || "").trim();


const TIME_ZONE =
  (typeof cfg.TIME_ZONE === "string" && cfg.TIME_ZONE.trim() !== "")
    ? cfg.TIME_ZONE.trim()
    : "America/New_York";


// -------------------- CONFIG (EDIT THESE IF NEEDED) --------------------
const WX_TABLE_NAME = "WX";
const EVENTS_TABLE_NAME = "Thermostat Events";

const WX_DATE_FIELD = "datetime";
const EV_DATE_FIELD = "Date";
const EV_ZONE_FIELD = "Thermostat"; // zone name in Events table

const ALL_ZONES = [
  "Stairs", "LR", "Kitchen", "Up Bath", "MANC", "Master", "Den",
  "Guest Hall", "Laundry", "Guest Bath", "Entryway", "Guest Room"
];

// Zones to never require for DQ (even if active)
const EXCLUDED_ZONES = new Set(["Guest Hall"]);

// Map zone -> WX field name for Auto kWh (must match exactly)
const ZONE_TO_AUTO_FIELD = {
  "Stairs": "Stairs KWH (Auto)",
  "LR": "LR KWH (Auto)",
  "Kitchen": "Kitchen KWH (Auto)",
  "Up Bath": "Up Bath KWH (Auto)",
  "MANC": "MANC KWH (Auto)",
  "Master": "Master KWH (Auto)",
  "Den": "Den KWH (Auto)",
  "Guest Hall": "Guest Hall KWH (Auto)",
  "Laundry": "Laundry KWH (Auto)",
  "Guest Bath": "Guest Bath KWH (Auto)",
  "Entryway": "Entryway KWH (Auto)",
  "Guest Room": "Guest Room KWH (Auto)"
};

// Output fields in WX table (must exist)
const OUT_STATUS_FIELD = "Therm DQ Status";           // single select
const OUT_SCORE_FIELD = "Therm DQ Score";             // number
const OUT_REQUIRED_FIELD = "Therm DQ Required Zones"; // long text
const OUT_MISSING_FIELD = "Therm DQ Missing Zones";   // long text
const OUT_NEG_FIELD = "Therm DQ Negative Zones";      // long text
const OUT_NOTES_FIELD = "Therm DQ Notes";             // long text

// Scoring
const PENALTY_MISSING_PER_ZONE = 25;
const PENALTY_NEGATIVE_PER_ZONE = 60;

// Guardrail: if there are zero thermostat events for the day, emit WARN
const WARN_IF_NO_EVENTS = true;

// Optional: treat missing field mapping as missing
const COUNT_MISSING_MAPPING_AS_MISSING = true;

// -------------------- NOTES (initialize ONCE, early; never redeclare) --------------------
let notesLines = [];

// -------------------- HELPERS --------------------
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


function normalizeZone(v) {
  return (v || "").toString().trim();
}

function isBlank(v) {
  return v === null || v === undefined || v === "";
}

function asNumber(v) {
  if (typeof v === "number") return v;
  if (isBlank(v)) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

// Airtable date cell values can vary (string/date/object). Normalize to YYYY-MM-DD.
function cellToDateString(cellVal) {
  if (cellVal === null || cellVal === undefined) return null;

  if (typeof cellVal === "string") return cellVal.slice(0, 10);

  if (cellVal instanceof Date) return ymdInTZ(cellVal, TIME_ZONE);

  if (typeof cellVal === "object" && cellVal.value) {
    return String(cellVal.value).slice(0, 10);
  }

  return String(cellVal).slice(0, 10);
}


// -------------------- TARGET DATE --------------------
let targetDate;
if (explicitTargetDate) {
  targetDate = explicitTargetDate;
} else {
  targetDate = yesterdayYMD(TIME_ZONE);
}


// -------------------- LOAD TABLES --------------------
const wxTable = base.getTable(WX_TABLE_NAME);
const evTable = base.getTable(EVENTS_TABLE_NAME);

// -------------------- FIND WX RECORD FOR targetDate --------------------
notesLines.push(`TIME_ZONE: ${TIME_ZONE}`);
const wxFieldsToLoad = [
  WX_DATE_FIELD,
  ...Object.values(ZONE_TO_AUTO_FIELD),
  OUT_STATUS_FIELD,
  OUT_SCORE_FIELD,
  OUT_REQUIRED_FIELD,
  OUT_MISSING_FIELD,
  OUT_NEG_FIELD,
  OUT_NOTES_FIELD
];

const wxQuery = await wxTable.selectRecordsAsync({ fields: wxFieldsToLoad });

let wxRecord = null;
for (const r of wxQuery.records) {
  const dStr = cellToDateString(r.getCellValue(WX_DATE_FIELD));
  if (dStr === targetDate) {
    wxRecord = r;
    break;
  }
}
if (!wxRecord) {
  throw new Error(`WX record not found for targetDate=${targetDate}. Check WX table/Date field.`);
}

// -------------------- DERIVE ACTIVE ZONES FROM EVENTS --------------------
const evQuery = await evTable.selectRecordsAsync({ fields: [EV_DATE_FIELD, EV_ZONE_FIELD] });

const activeZones = new Set();
let eventsCount = 0;

for (const r of evQuery.records) {
  const dStr = cellToDateString(r.getCellValue(EV_DATE_FIELD));
  if (dStr !== targetDate) continue;

  eventsCount += 1;

  const zCell = r.getCellValue(EV_ZONE_FIELD);
  // Single select returns {name: "..."}; text returns string; etc.
  const zName = (zCell && typeof zCell === "object" && zCell.name) ? zCell.name : zCell;
  const z = normalizeZone(zName);

  if (!z) continue;
  if (!ALL_ZONES.includes(z)) continue;

  activeZones.add(z);
}

// Required zones = active zones minus excluded zones
const requiredZones = new Set(activeZones);
for (const z of EXCLUDED_ZONES) requiredZones.delete(z);

// -------------------- VALIDATE AUTO kWh FOR REQUIRED ZONES --------------------
const missingZones = [];
const negativeZones = [];
const presentZones = [];

for (const z of Array.from(requiredZones).sort()) {
  const fieldName = ZONE_TO_AUTO_FIELD[z];

  if (!fieldName) {
    if (COUNT_MISSING_MAPPING_AS_MISSING) {
      missingZones.push(`${z} (no field mapping)`);
    }
    continue;
  }

  const raw = wxRecord.getCellValue(fieldName);
  const n = asNumber(raw);

  if (n === null) {
    missingZones.push(z);
    continue;
  }

  presentZones.push(z);

  if (n < 0) {
    negativeZones.push(`${z} (${n})`);
  }
}

// -------------------- SCORE + STATUS --------------------
let score = 100;
score -= PENALTY_MISSING_PER_ZONE * missingZones.length;
score -= PENALTY_NEGATIVE_PER_ZONE * negativeZones.length;
score = Math.max(0, Math.min(100, score));

let status = "PASS";

if (WARN_IF_NO_EVENTS && eventsCount === 0) {
  status = "WARN";
  notesLines.push(
    "WARN: No thermostat events found for targetDate; requiredZones is empty. " +
    "Not asserting zone-level kWh completeness for this day."
  );
} else if (negativeZones.length > 0 || missingZones.length > 0) {
  status = "FAIL";
}

// -------------------- NOTES (build final summary) --------------------
notesLines = notesLines.concat([
  `targetDate: ${targetDate}`,
  `eventsCount: ${eventsCount}`,
  `activeZones: ${Array.from(activeZones).sort().join(", ") || "(none)"}`,
  `excludedZones: ${Array.from(EXCLUDED_ZONES).sort().join(", ") || "(none)"}`,
  `requiredZones: ${Array.from(requiredZones).sort().join(", ") || "(none)"}`,
  `presentZones: ${presentZones.join(", ") || "(none)"}`,
  `missingZones: ${missingZones.join(", ") || "(none)"}`,
  `negativeZones: ${negativeZones.join(", ") || "(none)"}`,
  `score: ${score}`,
  `status: ${status}`,
]);

// -------------------- WRITE BACK TO WX --------------------
await wxTable.updateRecordAsync(wxRecord.id, {
  [OUT_STATUS_FIELD]: { name: status },
  [OUT_SCORE_FIELD]: score,
  [OUT_REQUIRED_FIELD]: Array.from(requiredZones).sort().join(", "),
  [OUT_MISSING_FIELD]: missingZones.join(", "),
  [OUT_NEG_FIELD]: negativeZones.join(", "),
  [OUT_NOTES_FIELD]: notesLines.join("\n"),
});

// Optional outputs for Automation debugging
output.set("targetDate", targetDate);
output.set("eventsCount", eventsCount);
output.set("activeZones", Array.from(activeZones).sort().join(", "));
output.set("requiredZones", Array.from(requiredZones).sort().join(", "));
output.set("status", status);
output.set("score", score);
