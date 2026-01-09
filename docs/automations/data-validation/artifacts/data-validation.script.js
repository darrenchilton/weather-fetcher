/**
 * Thermostat Validation (Manual vs Auto) — Airtable Automation Script
 * UPDATED VERSION with Hybrid Tolerance Thresholds
 *
 * Purpose:
 *   VALIDATION ONLY: Compare per-zone kWh Auto vs kWh Manual/Mysa on a single WX record.
 *   Does NOT assess data integrity (DQ does that) and does NOT drive alerts.
 *
 * Key Changes from Original:
 *   - Uses HYBRID thresholds (absolute kWh AND percentage)
 *   - A zone must fail BOTH thresholds to be marked SEVERE
 *   - More lenient absolute thresholds (0.50 for PASS, 2.00 for FAIL)
 *   - Adds percentage-based thresholds (5% for PASS, 15% for FAIL)
 *   - Includes percentage error in output for better visibility
 *
 * Trigger:
 *   Button click on WX record -> Automation -> Run script with input variable wxRecordId
 */

// ========== INPUTS ==========
const inputConfig = input.config();
const wxRecordId = inputConfig.wxRecordId;

if (!wxRecordId) {
  throw new Error("Missing required input: wxRecordId");
}

// ========== HYBRID TOLERANCE THRESHOLDS ==========
// A zone passes if EITHER absolute OR percentage is within tolerance
// A zone fails SEVERE only if BOTH absolute AND percentage exceed thresholds

const PASS_TOL_KWH = (typeof inputConfig.PASS_TOL_KWH === "number")
  ? inputConfig.PASS_TOL_KWH : 0.50;  // Relaxed from 0.20

const FAIL_TOL_KWH = (typeof inputConfig.FAIL_TOL_KWH === "number")
  ? inputConfig.FAIL_TOL_KWH : 2.00;  // Relaxed from 0.75

const PASS_TOL_PERCENT = (typeof inputConfig.PASS_TOL_PERCENT === "number")
  ? inputConfig.PASS_TOL_PERCENT : 5;  // 5% error

const FAIL_TOL_PERCENT = (typeof inputConfig.FAIL_TOL_PERCENT === "number")
  ? inputConfig.FAIL_TOL_PERCENT : 15;  // 15% error

const MIN_COMPARED_ZONES = (typeof inputConfig.MIN_COMPARED_ZONES === "number")
  ? inputConfig.MIN_COMPARED_ZONES : 1;

// Zones that should NEVER be validated (hallway placeholder, etc.)
const ALWAYS_EXCLUDED_ZONES = Array.isArray(inputConfig.EXCLUDED_ZONES)
  ? inputConfig.EXCLUDED_ZONES
  : ["Guest Hall"];

// Zones that are OPTIONAL: do not expect manual values unless they were actually used.
// Your policy: Laundry + Guest Room behave this way.
const OPTIONAL_ZONES = Array.isArray(inputConfig.OPTIONAL_ZONES)
  ? inputConfig.OPTIONAL_ZONES
  : ["Laundry", "Guest Room"];

const EXCLUDE_KITCHEN_FROM_MAX = (typeof inputConfig.EXCLUDE_KITCHEN_FROM_MAX === "boolean")
  ? inputConfig.EXCLUDE_KITCHEN_FROM_MAX
  : true;

const KITCHEN_ZONE_NAME = "Kitchen";
const USAGE_TYPE_FIELD = inputConfig.USAGE_TYPE_FIELD || "Usage Type";
const USAGE_EMPTY_HOUSE = "Empty House";
const USAGE_SYSTEM_OFF = "System Off";
const USAGE_NO_HEAT_NEEDED = "Enabled, No Heat Needed";

// For these usage types, we skip manual-vs-auto validation entirely
const SKIP_VALIDATION_USAGE_TYPES = new Set([
  USAGE_SYSTEM_OFF.toLowerCase(),
  USAGE_NO_HEAT_NEEDED.toLowerCase(),
]);


// ========== CONFIG: ZONE -> FIELD NAMES ==========
/**
 * Update these to match your WX field names exactly.
 * Keep this explicit; do not attempt dynamic field discovery.
 */
const ZONES = [
  { zone: "LR", autoField: "LR KWH (Auto)", manualField: "LR KWH" },
  { zone: "Kitchen", autoField: "Kitchen KWH (Auto)", manualField: "Kitchen KWH" },
  { zone: "Up Bath", autoField: "Up Bath KWH (Auto)", manualField: "Up Bath KWH" },
  { zone: "MANC", autoField: "MANC KWH (Auto)", manualField: "MANC KWH" },
  { zone: "Master", autoField: "Master KWH (Auto)", manualField: "Master KWH" },
  { zone: "Stairs", autoField: "Stairs KWH (Auto)", manualField: "Stairs KWH" },
  { zone: "Den", autoField: "Den KWH (Auto)", manualField: "Den KWH" },
  { zone: "Guest Hall", autoField: "Guest Hall KWH (Auto)", manualField: "Guest Hall KWH" },
  { zone: "Laundry", autoField: "Laundry KWH (Auto)", manualField: "Laundry KWH" },
  { zone: "Guest Bath", autoField: "Guest Bath KWH (Auto)", manualField: "Guest Bath KWH" },
  { zone: "Guest Room", autoField: "Guest Room KWH (Auto)", manualField: "Guest Room KWH" },
  { zone: "Entryway", autoField: "Entryway KWH (Auto)", manualField: "Entryway KWH" },
];

// ========== HELPERS ==========
function isBlank(v) {
  return v === null || v === undefined || (typeof v === "string" && v.trim() === "");
}

function asNumberOrNull(v) {
  if (isBlank(v)) return null;
  if (typeof v === "number" && Number.isFinite(v)) return v;
  // Airtable can sometimes pass numeric-looking strings
  if (typeof v === "string") {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function selectValue(name) {
  return { name };
}

function clamp(n, min, max) {
  return Math.max(min, Math.min(max, n));
}

function stringCell(v) {
  // Airtable single select returns {name}; plain text is string
  if (v && typeof v === "object" && typeof v.name === "string") return v.name;
  if (typeof v === "string") return v;
  return "";
}

function isKitchenOnlyCompared(comparedZones, kitchenName) {
  return comparedZones.length === 1 && comparedZones[0] === kitchenName;
}

// ========== MAIN ==========
const wxTable = base.getTable("WX");
const wxRecord = await wxTable.selectRecordAsync(wxRecordId);

if (!wxRecord) {
  throw new Error(`WX record not found: ${wxRecordId}`);
}

const usageType = stringCell(wxRecord.getCellValue(USAGE_TYPE_FIELD));
const usageTypeNorm = (usageType || "").trim().toLowerCase();

if (SKIP_VALIDATION_USAGE_TYPES.has(usageTypeNorm)) {
  const notes =
    `Thermostat Validation (Manual vs Auto) — SKIPPED\n` +
    `Usage Type: ${usageType}\n` +
    `Policy: Validation skipped for this Usage Type (manual entry not expected).\n`;

  await wxTable.updateRecordAsync(wxRecordId, {
    "Therm Validation Status": selectValue("PASS"),
    "Therm Validation Score": 100,
    "Therm Validation Compared Zones": "(skipped)",
    "Therm Validation Missing Manual Zones": "(skipped)",
    "Therm Validation Missing Auto Zones": "(skipped)",
    "Therm Validation Max Abs Diff": 0,
    "Therm Validation Mean Abs Diff": null,
    "Therm Validation Notes": notes,
    "Therm Validation Needs Review": false,
    "Therm Validation Last Run": new Date(),
  });

  return;
}


// ---- Determine which zones are EXPECTED for this record ----
// Default expected: everything except ALWAYS_EXCLUDED + OPTIONAL (optional are opt-in)
let expectedZones = new Set(
  ZONES
    .map(z => z.zone)
    .filter(z => !ALWAYS_EXCLUDED_ZONES.includes(z))
    .filter(z => !OPTIONAL_ZONES.includes(z))
);

// "Empty House" => only Kitchen is expected (plus optional zones if manually entered)
if (usageTypeNorm === USAGE_EMPTY_HOUSE.toLowerCase()) {
  expectedZones = new Set([KITCHEN_ZONE_NAME]);
}


// Optional zones: include ONLY if manual is present (opt-in)
for (const z of ZONES) {
  if (!OPTIONAL_ZONES.includes(z.zone)) continue;
  const manualRaw = wxRecord.getCellValue(z.manualField);
  if (!isBlank(manualRaw)) expectedZones.add(z.zone);
}

// zonesToValidate = expected zones only (and never include always-excluded)
const zonesToValidate = [];
for (const z of ZONES) {
  if (ALWAYS_EXCLUDED_ZONES.includes(z.zone)) continue;
  if (!expectedZones.has(z.zone)) continue;
  zonesToValidate.push(z);
}

// Stats accumulators
const compared = [];
const missingManualZones = [];
const missingAutoZones = [];

let absDiffSum = 0;
let pctDiffSum = 0;
let comparedCount = 0;

let maxAbsDiffAll = 0;
let maxAbsDiffNoKitchen = 0;
let maxPctDiffAll = 0;

let severeCount = 0;
let warnCount = 0;

const perZoneLines = [];

for (const z of zonesToValidate) {
  const auto = asNumberOrNull(wxRecord.getCellValue(z.autoField));
  const manual = asNumberOrNull(wxRecord.getCellValue(z.manualField));

  if (manual === null) {
    missingManualZones.push(z.zone);
    continue;
  }
  if (auto === null) {
    missingAutoZones.push(z.zone);
    continue;
  }

  const diff = auto - manual;
  const absDiff = Math.abs(diff);

  // Calculate percentage error (avoid division by zero)
  const pctDiff = auto > 0 ? (absDiff / auto * 100) : 0;

  compared.push(z.zone);
  comparedCount += 1;
  absDiffSum += absDiff;
  pctDiffSum += pctDiff;

  if (absDiff > maxAbsDiffAll) maxAbsDiffAll = absDiff;
  if (z.zone !== KITCHEN_ZONE_NAME && absDiff > maxAbsDiffNoKitchen) maxAbsDiffNoKitchen = absDiff;
  if (pctDiff > maxPctDiffAll) maxPctDiffAll = pctDiff;

  // ========== HYBRID THRESHOLD LOGIC ==========
  // Pass if EITHER absolute OR percentage is within PASS threshold
  // Fail SEVERE if BOTH absolute AND percentage exceed FAIL threshold
  // Otherwise WARN

  const passesAbsolute = (absDiff <= PASS_TOL_KWH);
  const passesPercent = (pctDiff <= PASS_TOL_PERCENT);
  const failsAbsolute = (absDiff > FAIL_TOL_KWH);
  const failsPercent = (pctDiff > FAIL_TOL_PERCENT);

  if (failsAbsolute && failsPercent) {
    // Both thresholds exceeded = SEVERE
    severeCount += 1;
  } else if (!passesAbsolute && !passesPercent) {
    // Neither threshold passed = WARN
    warnCount += 1;
  }
  // else: at least one threshold passed = OK

  perZoneLines.push(
    `- ${z.zone}: manual=${manual.toFixed(2)} kWh, auto=${auto.toFixed(2)} kWh, ` +
    `diff=${diff.toFixed(2)} (abs ${absDiff.toFixed(2)}, ${pctDiff.toFixed(1)}%)`
  );
}

const meanAbsDiff = comparedCount > 0 ? (absDiffSum / comparedCount) : null;
const meanPctDiff = comparedCount > 0 ? (pctDiffSum / comparedCount) : null;
const headlineMax = EXCLUDE_KITCHEN_FROM_MAX ? maxAbsDiffNoKitchen : maxAbsDiffAll;

// Determine status
let status = "PASS";
const missingManualCount = missingManualZones.length;
const missingAutoCount = missingAutoZones.length;

const kitchenOnlyCompared = isKitchenOnlyCompared(compared, KITCHEN_ZONE_NAME);

if (comparedCount < MIN_COMPARED_ZONES) {
  status = "WARN";
} else if (severeCount > 0) {
  // Downgrade Kitchen-only FAILs to WARN
  status = kitchenOnlyCompared ? "WARN" : "FAIL";
} else if (warnCount > 0 || missingManualCount > 0 || missingAutoCount > 0) {
  status = "WARN";
}

// Score (script-owned, simple)
let score = 100;
score -= (10 * severeCount);
score -= (5 * warnCount);
score -= (5 * missingAutoCount);
score -= (2 * missingManualCount);
score = clamp(Math.round(score), 0, 100);

// Notes
const zonesValidatedLabel = zonesToValidate.map(z => z.zone).join(", ") || "(none)";
const comparedLabel = compared.join(", ") || "(none)";
const missingManualLabel = missingManualZones.join(", ") || "(none)";
const missingAutoLabel = missingAutoZones.join(", ") || "(none)";

let notes = `Thermostat Validation (Manual vs Auto) — HYBRID THRESHOLDS\n`;
notes += `Usage Type: ${usageType || "(blank)"}\n`;
notes += `Zones expected for this record: ${zonesValidatedLabel}\n`;
notes += `Compared zones: ${comparedLabel}\n`;
notes += `Missing manual zones: ${missingManualLabel}\n`;
notes += `Missing auto zones: ${missingAutoLabel}\n\n`;

notes += `HYBRID THRESHOLDS:\n`;
notes += `  PASS: ≤${PASS_TOL_KWH.toFixed(2)} kWh OR ≤${PASS_TOL_PERCENT}%\n`;
notes += `  FAIL: >${FAIL_TOL_KWH.toFixed(2)} kWh AND >${FAIL_TOL_PERCENT}%\n`;
notes += `  (Zone must exceed BOTH thresholds to be SEVERE)\n\n`;

notes += `RESULTS:\n`;
notes += `  Compared count: ${comparedCount}\n`;
notes += `  Warn count: ${warnCount}\n`;
notes += `  Severe count: ${severeCount}\n`;

if (kitchenOnlyCompared && severeCount > 0) {
  notes += `  Policy: Kitchen-only severe diff downgraded from FAIL to WARN\n`;
}

if (meanAbsDiff !== null) {
  notes += `  Mean abs diff: ${meanAbsDiff.toFixed(2)} kWh\n`;
}
if (meanPctDiff !== null) {
  notes += `  Mean % diff: ${meanPctDiff.toFixed(1)}%\n`;
}
notes += `  Max abs diff${EXCLUDE_KITCHEN_FROM_MAX ? " (no Kitchen)" : ""}: ${headlineMax.toFixed(2)} kWh\n`;
notes += `  Max % diff: ${maxPctDiffAll.toFixed(1)}%\n`;

if (perZoneLines.length > 0) {
  notes += `\nPer-zone details:\n${perZoneLines.join("\n")}\n`;
} else {
  notes += `\nPer-zone details: (none compared)\n`;
}

// Needs Review checkbox
const needsReview = (status !== "PASS");

// Write outputs
await wxTable.updateRecordAsync(wxRecordId, {
  "Therm Validation Status": selectValue(status),
  "Therm Validation Score": score,
  "Therm Validation Compared Zones": comparedLabel,
  "Therm Validation Missing Manual Zones": missingManualLabel,
  "Therm Validation Missing Auto Zones": missingAutoLabel,
  "Therm Validation Max Abs Diff": headlineMax,
  ...(meanAbsDiff !== null ? { "Therm Validation Mean Abs Diff": meanAbsDiff } : { "Therm Validation Mean Abs Diff": null }),
  "Therm Validation Notes": notes,
  "Therm Validation Needs Review": needsReview,
  "Therm Validation Last Run": new Date(),
});