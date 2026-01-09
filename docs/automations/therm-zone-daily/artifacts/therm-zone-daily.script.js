/**
 * Therm Zone Daily — Daily Upsert (Timezone-aligned with Therm SP script)
 *
 * Inputs (optional):
 * - targetDate: "YYYY-MM-DD" (override)
 * - TIME_ZONE: IANA tz string (default "America/New_York")
 */

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

function safeParseJsonCell(cell) {
  if (!cell) return {};
  if (typeof cell === "object") return cell;
  try { return JSON.parse(cell); } catch { return {}; }
}

async function chunkedCreate(table, records) {
  for (let i = 0; i < records.length; i += 50) {
    await table.createRecordsAsync(records.slice(i, i + 50));
  }
}

async function chunkedUpdate(table, records) {
  for (let i = 0; i < records.length; i += 50) {
    await table.updateRecordsAsync(records.slice(i, i + 50));
  }
}

async function main() {
  const cfg = input.config();

  // =====================
  // CONFIG
  // =====================
  const TIME_ZONE =
    (typeof cfg.TIME_ZONE === "string" && cfg.TIME_ZONE.trim() !== "")
      ? cfg.TIME_ZONE.trim()
      : "America/New_York";

  const WX_TABLE = "WX";
  const WX_DATE_FIELD = "datetime";
  const WX_DQ_FIELD = "Therm DQ Status";
  const WX_USAGE_FIELD = "Usage Type";

  const OUT_DEGREE_HOURS_JSON = "Therm SP Degree-Hours (Derived)";
  const OUT_HOURS_JSON = "Therm SP Setpoint-Hours (Derived)";
  const OUT_EFF_JSON = "Therm Efficiency Index (Derived)";
  const OUT_SRC_JSON = "Therm SP Source (Derived)";
  const OUT_CHG_JSON = "Therm SP Changes Count (Derived)";

  const ZONE_DAILY_TABLE = "Therm Zone Daily";
  const ZD_DATE_FIELD = "Date";
  const ZD_ZONE_FIELD = "Zone";
  const ZD_WX_LINK_FIELD = "WX Record";
  const ZD_KWH_FIELD = "kWh Auto";
  const ZD_DH_FIELD = "Degree Hours";
  const ZD_SPH_FIELD = "Setpoint Hours";
  const ZD_EI_FIELD = "Efficiency Index";
  const ZD_SRC_FIELD = "SP Source";
  const ZD_CHG_FIELD = "SP Changes Count";
  const ZD_DQ_FIELD = "DQ Status";
  const ZD_USAGE_FIELD = "Usage Type";

  const ZONES = [
    "Den",
    "Entryway",
    "Guest Bath",
    "Guest Hall",
    "Guest Room",
    "Kitchen",
    "LR",
    "Laundry",
    "MANC",
    "Master",
    "Stairs",
    "Up Bath",
  ];

  // =====================
  // Determine target date (local TZ)
  // =====================
  const override =
    (typeof cfg.targetDate === "string" && cfg.targetDate.trim() !== "")
      ? cfg.targetDate.trim().slice(0, 10)
      : null;

  const targetYmd = override || yesterdayYMD(TIME_ZONE);

  // =====================
  // Find WX record for target date (same logic style as your 6AM script)
  // =====================
  const wxTable = base.getTable(WX_TABLE);
  const wxQuery = await wxTable.selectRecordsAsync({
    fields: [
      WX_DATE_FIELD,
      WX_DQ_FIELD,
      WX_USAGE_FIELD,
      OUT_DEGREE_HOURS_JSON,
      OUT_HOURS_JSON,
      OUT_EFF_JSON,
      OUT_SRC_JSON,
      OUT_CHG_JSON,
      ...ZONES.map((z) => `${z} KWH (Auto)`),
    ],
  });

  let wxRecord = null;
  for (const r of wxQuery.records) {
    const dtVal = r.getCellValue(WX_DATE_FIELD);
    let d = null;
    if (dtVal instanceof Date) d = ymdInTZ(dtVal, TIME_ZONE);
    else if (typeof dtVal === "string" && dtVal.trim() !== "") d = dtVal.trim().slice(0, 10);
    if (d === targetYmd) { wxRecord = r; break; }
  }

  if (!wxRecord) {
    throw new Error(`No WX record found where "${WX_DATE_FIELD}" matches ${targetYmd}.`);
  }

  // =====================
  // Read values/maps from WX
  // =====================
  const dqStatus = wxRecord.getCellValueAsString(WX_DQ_FIELD) || null;
  const usageType = wxRecord.getCellValueAsString(WX_USAGE_FIELD) || null;

  const degreeHoursMap = safeParseJsonCell(wxRecord.getCellValue(OUT_DEGREE_HOURS_JSON));
  const setpointHoursMap = safeParseJsonCell(wxRecord.getCellValue(OUT_HOURS_JSON));
  const effMap = safeParseJsonCell(wxRecord.getCellValue(OUT_EFF_JSON));
  const srcMap = safeParseJsonCell(wxRecord.getCellValue(OUT_SRC_JSON));
  const chgMap = safeParseJsonCell(wxRecord.getCellValue(OUT_CHG_JSON));

  // =====================
  // Load existing Therm Zone Daily for upsert
  // =====================
  const zd = base.getTable(ZONE_DAILY_TABLE);
  const zdQuery = await zd.selectRecordsAsync({ fields: [ZD_DATE_FIELD, ZD_ZONE_FIELD] });

  const existingByKey = new Map(); // "YYYY-MM-DD|Zone" -> recordId
  for (const r of zdQuery.records) {
    const dVal = r.getCellValue(ZD_DATE_FIELD);
    const z = r.getCellValueAsString(ZD_ZONE_FIELD);
    if (!dVal || !z) continue;

    const ymd = dVal instanceof Date ? ymdInTZ(dVal, TIME_ZONE) : ymdInTZ(new Date(dVal), TIME_ZONE);
    existingByKey.set(`${ymd}|${z}`, r.id);
  }

  // For Date field writes, Airtable accepts a JS Date. Use UTC noon to avoid TZ edge weirdness.
  const [yy, mm, dd] = targetYmd.split("-").map(Number);
  const dateForWrite = new Date(Date.UTC(yy, mm - 1, dd, 12, 0, 0));

  const creates = [];
  const updates = [];
  let createdCount = 0;
  let updatedCount = 0;

  for (const zone of ZONES) {
    const key = `${targetYmd}|${zone}`;

    const kwh = wxRecord.getCellValue(`${zone} KWH (Auto)`);
    const dh = degreeHoursMap?.[zone] ?? null;
    const sph = setpointHoursMap?.[zone] ?? null;
    const ei = effMap?.[zone] ?? null;
    const src = srcMap?.[zone] ?? null;
    const chg = chgMap?.[zone] ?? null;

    const fields = {
      [ZD_DATE_FIELD]: dateForWrite,
      [ZD_ZONE_FIELD]: { name: zone },
      [ZD_WX_LINK_FIELD]: [{ id: wxRecord.id }],
      [ZD_KWH_FIELD]: (typeof kwh === "number" && Number.isFinite(kwh)) ? kwh : null,
      [ZD_DH_FIELD]: (typeof dh === "number" && Number.isFinite(dh)) ? dh : null,
      [ZD_SPH_FIELD]: (typeof sph === "number" && Number.isFinite(sph)) ? sph : null,
      [ZD_EI_FIELD]: (typeof ei === "number" && Number.isFinite(ei)) ? ei : null,
      [ZD_SRC_FIELD]: src ? { name: String(src) } : null,
      [ZD_CHG_FIELD]: (typeof chg === "number" && Number.isFinite(chg)) ? chg : null,
      [ZD_DQ_FIELD]: dqStatus ? { name: String(dqStatus) } : null,
      [ZD_USAGE_FIELD]: usageType ? { name: String(usageType) } : null,
    };

    const existingId = existingByKey.get(key);
    if (existingId) {
      updates.push({ id: existingId, fields });
      updatedCount++;
    } else {
      creates.push({ fields });
      createdCount++;
    }
  }

  await chunkedCreate(zd, creates);
  await chunkedUpdate(zd, updates);

  output.set("TIME_ZONE", TIME_ZONE);
  output.set("targetDate", targetYmd);
  output.set("created", createdCount);
  output.set("updated", updatedCount);
}

await main();
