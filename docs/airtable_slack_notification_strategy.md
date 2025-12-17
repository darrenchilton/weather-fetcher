# Airtable → Slack Notification Strategy
## WX Thermostat & Energy Monitoring

**Project:** Albert Court Maintenance  
**Purpose:** Low-noise, high-signal operational notifications  
**Audience:** Operator / maintainer  
**Status:** Recommended baseline configuration

---

## 1. Design Principles

1. **No false positives**
   - Never alert before Home Assistant has had a full opportunity to complete overnight rollups.
   - Empty-house and testing days must not generate alerts.

2. **Schedule over events (by default)**
   - Time-based checks are preferred to “record enters view” for any condition dependent on overnight processing.

3. **Human intent matters**
   - `{Usage Type}` → `{Manual Expected?}` gates validation-related alerts.
   - Alerts should align with when you realistically act on them.

4. **Actionable only**
   - If an alert does not lead to a clear action, do not create it.

---

## 2. Core Fields Used by Notifications

The following fields are assumed to exist in the WX table:

- `{datetime}`
- `{Usage Type}`
- `{Manual Expected?}`
- `{Manual kWh Missing Count}`
- `{kWh Comparison Count}`
- `{kWh Diff Max Abs (No Kitchen)}`
- `{Kitchen kWh Abs Diff}`
- `{Therm Confidence Score}`
- One HA-owned rollup presence indicator, e.g.:
  - `{Thermostat Settings (Auto)}` not blank, or
  - `{Data Source}` = `HA`

---

## 3. Notification Types

### A) HA Rollup Missing (Critical)

**Purpose:** Detect when yesterday’s Home Assistant rollup did not materialize into Airtable.

**Trigger type:** Scheduled  
**Schedule:** Daily at **06:30 America/New_York**

**View:** `ALERT — HA Rollup Missing`

**View filters:**
- `{datetime}` = yesterday
- AND rollup-present indicator = false  
  (e.g. `{Thermostat Settings (Auto)} is blank`)

**Slack message (example):**
```
⚠️ WX rollup missing for {{datetime}}.
Home Assistant did not populate thermostat/energy fields.
Action: check HA automations, shell_command, and logs.
```

**Notes:**
- Do NOT use “record enters view” for this alert.
- This alert should be rare; when it fires, it matters.

---

### B) Manual Data Missing on Validation Days (Optional)

**Purpose:** Keep manual validation disciplined when you are actively validating.

**Trigger type:** Scheduled  
**Schedule:** Daily at **18:00 America/New_York**

**View:** `ALERT — Manual Missing (Validation Days)`

**View filters:**
- `{Manual Expected?}` = 1
- `{Manual kWh Missing Count}` > 0

**Slack message (example):**
```
ℹ️ Manual kWh missing for {{datetime}} ({{Manual kWh Missing Count}} zones).
Usage Type: {{Usage Type}}
This is a validation day — consider entering remaining manual values.
```

**Notes:**
- Suppressed automatically on empty/no-usage/testing days.
- Useful only during active validation windows.

---

### C) Non-Kitchen Divergence (High Signal)

**Purpose:** Detect meaningful discrepancies in non-Kitchen zones.

**Trigger type:** Scheduled  
**Schedule:** Daily at **06:45 America/New_York**

**View:** `ALERT — Non-Kitchen Divergence`

**View filters:**
- `{Manual Expected?}` = 1
- `{kWh Comparison Count}` ≥ 5
- `{kWh Diff Max Abs (No Kitchen)}` > 1.50  
  (tune threshold as desired)

**Slack message (example):**
```
⚠️ Non-Kitchen energy divergence detected for {{datetime}}.
Max abs diff (non-Kitchen): {{kWh Diff Max Abs (No Kitchen)}} kWh
Confidence Score: {{Therm Confidence Score}}
```

**Notes:**
- Kitchen is explicitly excluded.
- Consider adding a “2 consecutive days” requirement later if needed.

---

### D) Extreme Kitchen Divergence (Optional)

**Purpose:** Alert only on extreme Kitchen behavior beyond known tolerance.

**Trigger type:** Scheduled  
**Schedule:** Daily at **06:45 America/New_York**

**View:** `ALERT — Kitchen Extreme`

**View filters:**
- `{Kitchen kWh Abs Diff}` ≥ 12  
- Optional: `{HDD (18C)}` ≥ threshold to suppress mild-weather noise

**Slack message (example):**
```
⚠️ Kitchen-only divergence exceeds tolerance for {{datetime}}.
Kitchen abs diff: {{Kitchen kWh Abs Diff}} kWh
HDD: {{HDD (18C)}}
```

**Notes:**
- Designed to be rare.
- Useful as a “something changed” indicator.

---

## 4. Why Scheduled Triggers Are Preferred

Using **scheduled automations** avoids early false alerts:

- WX records exist at midnight
- HA rollups complete between 00:30–04:30
- A 06:30–06:45 evaluation window guarantees stability

Views should remain **purely logical**; time awareness belongs in the automation trigger.

---

## 5. Optional Enhancements (Later)

- Add `HA Rollup Status` field (`PENDING / COMPLETE / ERROR`) as a latch.
- Add weekly digest summarizing confidence trends instead of daily alerts.
- Require multi-day persistence before divergence alerts fire.

---

## 6. Minimal Recommended Starter Set

To begin with minimal noise:

1. **HA Rollup Missing** (Critical)
2. **Non-Kitchen Divergence** (High signal)

Add the others only if you find them useful during active validation.

---

**End of document**
