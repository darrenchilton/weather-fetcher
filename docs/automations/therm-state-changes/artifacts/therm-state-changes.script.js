async function main() {
  const cfg = input.config();

  // =====================
  // CONFIG
  // =====================
  const WX_TABLE = "WX";
  const WX_DATE_FIELD = "datetime";
  const WX_OM_TEMP_FIELD = "om_temp"; // daily avg outdoor temp in °C

  const EVENTS_TABLE = "Thermostat Events";
  const EVT_TIME_FIELD = "Timestamp";
  const EVT_SETPOINT_FIELD = "New Setpoint";
  const EVT_THERMOSTAT_FIELD = "Thermostat";
  const EVT_NAME_FALLBACK = "Name";

  // Outputs (WX)
  const OUT_START_JSON = "Therm SP Start (Derived)";
  const OUT_END_JSON = "Therm SP End (Derived)";
  const OUT_TIMELINE_JSON = "Therm SP Timeline (Derived)";
  const OUT_HOURS_JSON = "Therm SP Setpoint-Hours (Derived)";
  const OUT_DEGREE_HOURS_JSON = "Therm SP Degree-Hours (Derived)";
  const OUT_DEGREE_HOURS_BY_SP_JSON = "Therm SP Degree-Hours by Setpoint (Derived)";
  const OUT_EFF_INDEX_JSON = "Therm Efficiency Index (Derived)";
  const OUT_SOURCE_JSON = "Therm SP Source (Derived)";
  const OUT_CHANGES_JSON = "Therm SP Changes Count (Derived)";
  const OUT_STALE_ZONES = "Therm SP Stale Zones (Derived)";
  const OUT_SUMMARY = "Therm SP Summary (Derived)";
  const OUT_LAST_RUN = "Therm SP Last Run";

  // Manual trigger checkbox on WX (NOT used by daily run, but kept as a constant if you want logging)
  const MANUAL_CHECKBOX_FIELD = "Temp Therm Calc";

  // Policy
  const STALE_HOURS = (typeof cfg.STALE_HOURS === "number") ? cfg.STALE_HOURS : 36;
  const EXCLUDED_ZONES = Array.isArray(cfg.EXCLUDED_ZONES) ? cfg.EXCLUDED_ZONES : [];
  const TIME_ZONE =
    (typeof cfg.TIME_ZONE === "string" && cfg.TIME_ZONE.trim() !== "")
      ? cfg.TIME_ZONE.trim()
      : "America/New_York";

  // If an event occurs within this many minutes after midnight, treat it as the midnight schedule-set
  const MIDNIGHT_GRACE_MINUTES =
    (typeof cfg.MIDNIGHT_GRACE_MINUTES === "number")
      ? cfg.MIDNIGHT_GRACE_MINUTES
      : 10;

  // OPTIONAL input variable for backfills / testing: targetDate = "YYYY-MM-DD"
  const OVERRIDE_TARGET_DATE =
    (typeof cfg.targetDate === "string" && cfg.targetDate.trim() !== "")
      ? cfg.targetDate.trim().slice(0, 10)
      : null;

  // =====================
  // Helpers
  // =====================
  function isBlank(v) {
    return v === null || v === undefined || (typeof v === "string" && v.trim() === "");
  }
  function asNumberOrNull(v) {
    if (isBlank(v)) return null;
    if (typeof v === "number" && Number.isFinite(v)) return v;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  function asFiniteNumberOrNull(v) {
    return (typeof v === "number" && Number.isFinite(v)) ? v : null;
  }
  function hoursBetween(a, b) {
    return Math.abs(a.getTime() - b.getTime()) / (1000 * 60 * 60);
  }
  function uniq(arr) { return [...new Set(arr)]; }
  function round3(n) { return Math.round(n * 1000) / 1000; }

  function zoneFromEventRecord(rec) {
    const tVal = rec.getCellValue(EVT_THERMOSTAT_FIELD);
    if (tVal) {
      if (Array.isArray(tVal) && tVal.length) return String(tVal[0].name || tVal[0].id || "");
      if (typeof tVal === "object" && tVal.name) return String(tVal.name);
      return String(tVal);
    }
    const nVal = rec.getCellValue(EVT_NAME_FALLBACK);
    if (nVal) return String(nVal);
    return "";
  }

  function ymdInTZ(date, timeZone) {
    return new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  }

  function tzMidnightToUTC(dateStr, timeZone) {
    const [y, m, d] = dateStr.split("-").map(Number);
    const utcApprox = new Date(Date.UTC(y, m - 1, d, 0, 0, 0));
    const tzInterpreted = new Date(utcApprox.toLocaleString("en-US", { timeZone }));
    const offsetMs = utcApprox.getTime() - tzInterpreted.getTime();
    return new Date(utcApprox.getTime() + offsetMs);
  }

  function startOfDayTZ(dateStr, timeZone) { return tzMidnightToUTC(dateStr, timeZone); }
  function endOfDayTZ(dateStr, timeZone) {
    const start = tzMidnightToUTC(dateStr, timeZone);
    return new Date(start.getTime() + (24 * 60 * 60 * 1000) - 1);
  }

  function buildTimelineAndHours({ dayStart, dayEnd, dayZoneEventsSorted, lastBeforeStart }) {
    const graceMs = MIDNIGHT_GRACE_MINUTES * 60 * 1000;
    const firstOnOrAfterStart = dayZoneEventsSorted.length ? dayZoneEventsSorted[0] : null;

    let effectiveAtStart = null;
    if (firstOnOrAfterStart && (firstOnOrAfterStart.t.getTime() - dayStart.getTime()) <= graceMs) {
      effectiveAtStart = firstOnOrAfterStart.sp;
    } else if (lastBeforeStart) {
      effectiveAtStart = lastBeforeStart.sp;
    }

    const intervals = [];
    let currentSp = effectiveAtStart;
    let cursor = dayStart;

    for (const ev of dayZoneEventsSorted) {
      const t = ev.t;
      if (t.getTime() < dayStart.getTime() || t.getTime() > dayEnd.getTime()) continue;

      if (currentSp !== null && t.getTime() > cursor.getTime()) {
        intervals.push({ from: cursor, to: t, sp: currentSp });
      }
      currentSp = ev.sp;
      cursor = t;
    }

    const dayClose = new Date(dayEnd.getTime() + 1);
    if (currentSp !== null && dayClose.getTime() > cursor.getTime()) {
      intervals.push({ from: cursor, to: dayClose, sp: currentSp });
    }

    let totalHours = 0;
    let setpointHours = 0;
    const hoursBySetpoint = {};

    for (const it of intervals) {
      const durHrs = (it.to.getTime() - it.from.getTime()) / 3_600_000;
      totalHours += durHrs;
      setpointHours += durHrs * it.sp;
      const key = String(it.sp);
      hoursBySetpoint[key] = (hoursBySetpoint[key] || 0) + durHrs;
    }

    const intervalsOut = intervals.map(it => ({
      from: it.from.toISOString(),
      to: it.to.toISOString(),
      sp: it.sp
    }));

    const hoursOut = {
      totalHours: round3(totalHours),
      setpointHours: round3(setpointHours),
      hoursBySetpoint: Object.fromEntries(
        Object.entries(hoursBySetpoint).map(([k, v]) => [k, round3(v)])
      )
    };

    return { intervalsOut, hoursOut };
  }

  function computeDegreeHours(intervalsOut, omTempC) {
    if (typeof omTempC !== "number" || !Number.isFinite(omTempC)) {
      return { total: null, bySetpoint: null };
    }

    let total = 0;
    const bySetpoint = {};

    for (const it of intervalsOut) {
      const fromMs = new Date(it.from).getTime();
      const toMs = new Date(it.to).getTime();
      const hours = (toMs - fromMs) / 3_600_000;

      const delta = Math.max(0, it.sp - omTempC);
      const dh = delta * hours;

      total += dh;
      const key = String(it.sp);
      bySetpoint[key] = (bySetpoint[key] || 0) + dh;
    }

    return {
      total: round3(total),
      bySetpoint: Object.fromEntries(Object.entries(bySetpoint).map(([k, v]) => [k, round3(v)]))
    };
  }

  function kwhFieldForZone(zoneName) {
    return `${zoneName} KWH (Auto)`;
  }

  function getKwhForZoneSafe(wxTable, wxRecord, zoneName) {
    const fieldName = kwhFieldForZone(zoneName);
    try {
      const field = wxTable.getField(fieldName);
      return asFiniteNumberOrNull(wxRecord.getCellValue(field.name));
    } catch (e) {
      return null;
    }
  }

  function yesterdayYMD(timeZone) {
    // Build "today" in TZ, then subtract one calendar day safely by going through UTC noon
    const now = new Date();
    const today = ymdInTZ(now, timeZone);
    const [y, m, d] = today.split("-").map(Number);
    const utcNoon = new Date(Date.UTC(y, m - 1, d, 12, 0, 0));
    utcNoon.setUTCDate(utcNoon.getUTCDate() - 1);
    return ymdInTZ(utcNoon, timeZone);
  }

  // =====================
  // Locate WX record + targetDate (DAILY: yesterday)
  // =====================
  const wxTable = base.getTable(WX_TABLE);

  const targetDate = OVERRIDE_TARGET_DATE || yesterdayYMD(TIME_ZONE);

  // NOTE: we select all records because we also need to read per-zone "___ KWH (Auto)" fields
  const wxQuery = await wxTable.selectRecordsAsync();

  // Find matching WX record by date
  let wxRecord = null;
  for (const r of wxQuery.records) {
    const dtVal = r.getCellValue(WX_DATE_FIELD);
    let d = null;
    if (dtVal instanceof Date) d = ymdInTZ(dtVal, TIME_ZONE);
    else if (typeof dtVal === "string" && dtVal.trim() !== "") d = dtVal.trim().slice(0, 10);
    if (d === targetDate) { wxRecord = r; break; }
  }

  if (!wxRecord) {
    throw new Error(`No WX record found where "${WX_DATE_FIELD}" matches ${targetDate}.`);
  }

  const omTempC = wxRecord.getCellValue(WX_OM_TEMP_FIELD);
  const dayStart = startOfDayTZ(targetDate, TIME_ZONE);
  const dayEnd = endOfDayTZ(targetDate, TIME_ZONE);

  console.log(`Daily recompute for ${targetDate} (${TIME_ZONE}) WX=${wxRecord.id}`);

  // =====================
  // Load Thermostat Events
  // =====================
  const evTable = base.getTable(EVENTS_TABLE);
  const evQuery = await evTable.selectRecordsAsync();

  let scanned = 0, hasTime = 0, hasSetpoint = 0, kept = 0;
  const events = [];

  for (const r of evQuery.records) {
    scanned++;

    const zoneName = zoneFromEventRecord(r);
    if (isBlank(zoneName)) continue;
    if (EXCLUDED_ZONES.includes(zoneName)) continue;

    const tRaw = r.getCellValue(EVT_TIME_FIELD);
    let t = null;
    if (tRaw instanceof Date) t = tRaw;
    else if (typeof tRaw === "string" && tRaw.trim() !== "") {
      t = new Date(tRaw.trim());
      if (isNaN(t.getTime())) t = null;
    }
    if (!t) continue;
    hasTime++;

    const eventDay = ymdInTZ(t, TIME_ZONE);
    if (eventDay > targetDate) continue;

    const sp = asNumberOrNull(r.getCellValue(EVT_SETPOINT_FIELD));
    if (sp === null) continue;
    hasSetpoint++;

    kept++;
    events.push({ zone: zoneName, t, sp, eventDay });
  }

  let zones = uniq(events.map(e => e.zone)).filter(z => !EXCLUDED_ZONES.includes(z)).sort();

  if (zones.length === 0) {
    const summary = [
      `Therm SP Baseline (Derived) for ${targetDate}`,
      `No zones inferred.`,
      `Diagnostics: scanned=${scanned} hasTime=${hasTime} hasSetpoint=${hasSetpoint} kept=${kept}`,
      `Time zone: ${TIME_ZONE}`,
    ].join("\n");

    await wxTable.updateRecordAsync(wxRecord.id, {
      [OUT_START_JSON]: "{}",
      [OUT_END_JSON]: "{}",
      [OUT_TIMELINE_JSON]: "{}",
      [OUT_HOURS_JSON]: "{}",
      [OUT_DEGREE_HOURS_JSON]: "{}",
      [OUT_DEGREE_HOURS_BY_SP_JSON]: "{}",
      [OUT_EFF_INDEX_JSON]: "{}",
      [OUT_SOURCE_JSON]: "{}",
      [OUT_CHANGES_JSON]: "{}",
      [OUT_STALE_ZONES]: "",
      [OUT_SUMMARY]: summary,
      [OUT_LAST_RUN]: new Date(),
      // Do NOT touch MANUAL_CHECKBOX_FIELD in daily runs
    });

    return;
  }

  // =====================
  // Build per-zone snapshots + timelines + degree-hours + efficiency index
  // =====================
  const startMap = {}, endMap = {}, sourceMap = {}, changesCountMap = {};
  const timelineMap = {}, hoursMap = {};
  const degreeHoursMap = {}, degreeHoursBySPMap = {};
  const effIndexMap = {};
  const staleZones = [];

  for (const z of zones) {
    const zoneEvents = events.filter(e => e.zone === z).sort((a, b) => a.t - b.t);

    const dayZoneEvents = zoneEvents.filter(e => e.t >= dayStart && e.t <= dayEnd);
    changesCountMap[z] = dayZoneEvents.length;

    const lastUpToEnd = zoneEvents.filter(e => e.t <= dayEnd).pop() || null;
    const lastBeforeStart = zoneEvents.filter(e => e.t < dayStart).pop() || null;

    const startSP_snapshot = lastBeforeStart ? lastBeforeStart.sp : (dayZoneEvents.length ? dayZoneEvents[0].sp : null);
    const endSP_snapshot = lastUpToEnd ? lastUpToEnd.sp : null;

    let source = "Observed";
    const hadEventOnDay = dayZoneEvents.length > 0;
    if (!hadEventOnDay) source = (lastBeforeStart || lastUpToEnd) ? "CarriedForward" : "Stale";
    if (lastUpToEnd) {
      const ageHrs = hoursBetween(lastUpToEnd.t, dayEnd);
      if (ageHrs > STALE_HOURS) source = "Stale";
    }
    if (source === "Stale") staleZones.push(z);

    const { intervalsOut, hoursOut } = buildTimelineAndHours({
      dayStart,
      dayEnd,
      dayZoneEventsSorted: dayZoneEvents,
      lastBeforeStart
    });

    const dh = computeDegreeHours(intervalsOut, omTempC);

    startMap[z] = startSP_snapshot;
    endMap[z] = endSP_snapshot;
    sourceMap[z] = source;
    timelineMap[z] = intervalsOut;
    hoursMap[z] = hoursOut;
    degreeHoursMap[z] = dh.total;
    degreeHoursBySPMap[z] = dh.bySetpoint;

    const kwhVal = getKwhForZoneSafe(wxTable, wxRecord, z);
    const dhVal = (typeof dh.total === "number" && Number.isFinite(dh.total)) ? dh.total : null;

    let eff = null;
    if (source !== "Stale" && kwhVal !== null && dhVal !== null && dhVal > 0) {
      eff = round3(kwhVal / dhVal);
    }
    effIndexMap[z] = eff;
  }

  // =====================
  // Summary + update
  // =====================
  const summaryLines = [];
  summaryLines.push(`Therm SP Baseline (Derived) for ${targetDate}`);
  summaryLines.push(`Diagnostics: scanned=${scanned} hasTime=${hasTime} hasSetpoint=${hasSetpoint} kept=${kept}`);
  summaryLines.push(`Zones: ${zones.join(", ")}`);
  summaryLines.push(`Time zone: ${TIME_ZONE}`);
  summaryLines.push(`Midnight grace: ${MIDNIGHT_GRACE_MINUTES} minutes`);
  summaryLines.push(`Stale threshold: ${STALE_HOURS} hours`);
  summaryLines.push(`WX.om_temp (°C): ${typeof omTempC === "number" ? omTempC : "(missing)"}`);
  summaryLines.push(`Stale zones: ${staleZones.length ? staleZones.join(", ") : "(none)"}`);
  summaryLines.push("");
  summaryLines.push("Per-zone snapshot (EffIndex=kWh/°C·hr):");

  for (const z of zones) {
    summaryLines.push(
      `- ${z}: start=${startMap[z]}, end=${endMap[z]}, changes=${changesCountMap[z]}, source=${sourceMap[z]}, ` +
      `setpointHours=${hoursMap[z].setpointHours}, degreeHours=${degreeHoursMap[z]}, effIndex=${effIndexMap[z]}`
    );
  }

  await wxTable.updateRecordAsync(wxRecord.id, {
    [OUT_START_JSON]: JSON.stringify(startMap),
    [OUT_END_JSON]: JSON.stringify(endMap),
    [OUT_TIMELINE_JSON]: JSON.stringify(timelineMap),
    [OUT_HOURS_JSON]: JSON.stringify(hoursMap),
    [OUT_DEGREE_HOURS_JSON]: JSON.stringify(degreeHoursMap),
    [OUT_DEGREE_HOURS_BY_SP_JSON]: JSON.stringify(degreeHoursBySPMap),
    [OUT_EFF_INDEX_JSON]: JSON.stringify(effIndexMap),
    [OUT_SOURCE_JSON]: JSON.stringify(sourceMap),
    [OUT_CHANGES_JSON]: JSON.stringify(changesCountMap),
    [OUT_STALE_ZONES]: staleZones.join(", "),
    [OUT_SUMMARY]: summaryLines.join("\n"),
    [OUT_LAST_RUN]: new Date(),
  });

  console.log(`✓ Updated ${targetDate} record successfully`);
}

await main();
