# Copyright (c) 2026, Nirmaan (Stratos Infra Technologies Pvt. Ltd.) and contributors
# For license information, please see license.txt

"""The BoQ summary's stored inputs and the server half of the summary block (slice BCS-5; design BCS-D0 P4).

The BoQ's main page shows, for Admin and Estimates only, one summary of the whole BoQ: one line per priceable sheet (BoQ amount,
BCS supply, BCS installation, margin), the sheets one Electrical installation cost covers as ONE clubbed block, and that
installation cost: area x the live Pricing Input `elec_bcs_install_per_sqft` + floor cutting at our cost (owner R1 - R8).

WHAT IS STORED HERE: ONE versioned `BoQ Summary Inputs` record per BoQ (freeze-and-supersede, one current record) holding what the
user enters: the area, the ticked sheets, and an edit or removal of either installation part (R-BCS-144). Keyed by the BoQ alone,
so a sheet re-commit keeps it and "Merge BoQs" keeps it; a revision gets a copy through `carry_summary_inputs`, called from
`revision.confirm_revision_mapping` (both revision entry paths end there).

WHAT THIS NEVER DOES: it writes ONLY `BoQ Summary Inputs`. No cell rate (BoQ Cell Pricing), no BCS cost (BoQ Row BCS Rate), no
helper edit, no rate file and no Pricing Input is written; this module imports no writer of any of them. BoQ amount, BCS supply and
typed installation are NOT computed here: the block computes them in the browser with the same functions the sheet's own Summary
uses, so a sheet's figures in both places are equal.

WHO: Admin and Estimates only, the BCS cost rule (`bcs._require_bcs_cost_access`, the pricing-access set; never a new role list),
checked before any argument is read, with its refusal words.

STORED SHAPE (owner R4 - R6; Question 3): `area_sqft` (0 or blank = not entered: an area of 0 sq ft is no area); `covered_sheets` =
{"sheets": [names VERBATIM]} or blank = the default ticks; each installation part has a Currency figure and a Check - Check 0 =
the system's figure, Check 1 = the user's figure (0 = removed). The Check is needed because Frappe writes a blank Currency as 0.

Public API:
  get_boq_summary_inputs(boq)                                                          [whitelisted, GET]
  save_boq_summary_inputs(boq, area_sqft?, covered_sheets?, area_cost_override?, floor_cut_override?)   [whitelisted POST]
      a field not sent is carried unchanged; "" sent = cleared (area not entered / default ticks / back to system figure).
  carry_summary_inputs(source_boq, new_boq, sheet_mapping)                             [internal: revision.py]
"""
from __future__ import annotations

import json
import re

import frappe
from frappe.utils import flt

from nirmaan_stack.api.boq.wizard.bcs import _require_bcs_cost_access

_STORE = "BoQ Summary Inputs"

# The two Pricing Inputs the summary reads, by their `attributes.item` (rate file v75; read live from the database).
INSTALL_PER_SQFT_INPUT = "elec_bcs_install_per_sqft"
TRAY_CUTTING_INPUT = "tray_cutting_amount"
_PRICING_INPUT_SUFFIX = "_pricing_input"

# The floor-cutting rule (R-BCS-30, design P4e, owner Q2 = (a)).
TRAY_CATEGORY = "cabletray_raceway"
FLOOR_ATTR = "floor_cutting"
_CHARGED_RATE_KINDS = ("install_rate", "combined_rate")

# The two installation parts a user may edit or remove (R-BCS-144): part -> (figure field, Check field).
PARTS = {"area_part": ("area_cost_override", "area_cost_overridden"),
         "floor_part": ("floor_cut_override", "floor_cut_overridden")}

# ONE declared list of LENGTH units (Question 1, chat-Claude 15:13 point 1 = (b)): read only through `is_length_unit`. Every form
# BCS-S5 S3d saw on caught floor rows (RM, MTS, M, Mtr, Mts., m, Rmt, Mtrs, Rm, Metre, mtr, Rmtrs, Mtrs., Rmt.) and every length
# spelling of the matching normaliser `services/boq_rate_match/match_text._UNITS["rmt"]` except `mt` (a metric tonne in some
# BoQs) - a test pins the second half, so the two lists cannot quietly disagree. Keys are written as `is_length_unit` folds a unit:
# lower-case, no dots, no spaces.
LENGTH_UNITS = frozenset({
    "m", "mtr", "mtrs", "mts", "meter", "meters", "metre", "metres",
    "rm", "rmt", "rmts", "rmtr", "rmtrs",
    "lm", "lnm", "runningmeter", "runningmetre", "runningmtr",
})


def is_length_unit(unit) -> bool:
    """True when a BoQ row's unit is a LENGTH (the floor rule's guard, owner Q2 = (a)): trim, lower-case, drop dots and spaces,
    then look the unit up in LENGTH_UNITS. "Mtrs." / "Rmt." / "R.M.T" count; "Nos." / "Sqm" / blank do not."""
    key = re.sub(r"[.\s]", "", str(unit or "").strip().lower())
    return key in LENGTH_UNITS


# -- small helpers ----------------------------------------------------------------------------------------------------------
def _parse_json(value, default):
    if isinstance(value, str):
        try:
            return json.loads(value) if value else default
        except (ValueError, TypeError):
            return default
    return default if value is None else value


def _validate_boq(boq) -> str:
    if not boq:
        frappe.throw("boq is required.", title="Missing field: boq")
    if not frappe.db.exists("BOQs", boq):
        frappe.throw(f"BOQs '{boq}' not found.", title="Not found")
    return boq


def _number(value, field: str) -> float:
    """A figure the user typed: a number >= 0, else a refusal naming the field."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        frappe.throw(f"{field} must be a number.", title=f"Invalid {field}")
    if n != n or n < 0 or n in (float("inf"), float("-inf")):
        frappe.throw(f"{field} must be a number of 0 or more.", title=f"Invalid {field}")
    return n


def _current_record(boq):
    """(names of the current records, the newest one as a dict or None). Normally 0 or 1 record (the invariant)."""
    rows = frappe.get_all(_STORE, filters={"boq": boq, "is_current": 1}, order_by="input_version desc",
                          fields=["name", "area_sqft", "covered_sheets", "area_cost_override", "area_cost_overridden",
                                  "floor_cut_override", "floor_cut_overridden", "input_version", "edited_by", "edited_at"])
    return [r.name for r in rows], (rows[0] if rows else None)


def _stored_values(rec) -> dict:
    """The user's inputs of one record, in the save path's own vocabulary (None = not entered / defaults / system figure)."""
    if not rec:
        return {"area_sqft": None, "covered_sheets": None, "area_part": None, "floor_part": None}
    area = flt(rec.get("area_sqft"))
    cov = _parse_json(rec.get("covered_sheets"), None)
    sheets = cov.get("sheets") if isinstance(cov, dict) else None
    out = {"area_sqft": area if area > 0 else None,
           "covered_sheets": [str(s) for s in sheets] if isinstance(sheets, list) else None}
    for part, (fig, chk) in PARTS.items():
        out[part] = flt(rec.get(fig)) if rec.get(chk) else None
    return out


def _supersede(boq, prior_names, values) -> str:
    """Freeze every prior current record, then write the new current one carrying `values`. The freeze is a raw write
    (frappe.db.set_value): `BoQ Summary Inputs` has no doc_events and nothing is derived from is_current, so it skips nothing."""
    for name in prior_names:
        frappe.db.set_value(_STORE, name, "is_current", 0)
    agg = frappe.get_all(_STORE, filters={"boq": boq}, fields=["max(input_version) as mv"])
    doc = frappe.new_doc(_STORE)
    doc.boq = boq
    doc.area_sqft = values["area_sqft"] or 0
    doc.covered_sheets = (json.dumps({"sheets": values["covered_sheets"]}) if values["covered_sheets"] is not None else None)
    for part, (fig, chk) in PARTS.items():
        doc.set(fig, values[part] if values[part] is not None else 0)
        doc.set(chk, 1 if values[part] is not None else 0)
    doc.input_version = ((agg[0].mv if agg else None) or 0) + 1
    doc.is_current = 1
    doc.edited_by = frappe.session.user
    doc.edited_at = frappe.utils.now()
    doc.insert(ignore_permissions=True)
    return doc.name


# -- what the summary reads -------------------------------------------------------------------------------------------------
def _pricing_input_amounts() -> dict:
    """{input item: rates.amount} for the ACTIVE Pricing Input rows, read from the database (the `cladding_cost._pricing_input_rates`
    pattern) - never from the rate-master HTTP payload, which withholds a summary-only input from non-cost users."""
    rows = frappe.get_all("BoQ Rate Master Item", filters={"active": 1, "kind": ["like", "%pricing_input"]},
                          fields=["kind", "attributes", "rates"])
    out = {}
    for r in rows:
        if not str(r.kind or "").endswith(_PRICING_INPUT_SUFFIX):
            continue
        item = (_parse_json(r.attributes, {}) or {}).get("item")
        amount = (_parse_json(r.rates, {}) or {}).get("amount")
        if item in (INSTALL_PER_SQFT_INPUT, TRAY_CUTTING_INPUT) and isinstance(amount, (int, float)) and not isinstance(amount, bool):
            out[item] = float(amount)
    return out


def _carpet_area(boq):
    project = frappe.db.get_value("BOQs", boq, "project")
    area = frappe.db.get_value("Projects", project, "carpet_area") if project else None
    return int(area) if area and int(area) > 0 else None


def _priceable_sheets(boq) -> list:
    """The current committed `treat_as = "data"` sheets (the priceable definition, commit_pipeline._DISPOSITION_TO_TREAT_AS), in
    the committed-state reader's order: sheet_order ascending, None last, then the name (commit_gate.get_committed_state)."""
    rows = frappe.get_all("BoQ Sheet", filters={"boq": boq, "is_current": 1, "treat_as": "data"},
                          fields=["name", "sheet_name", "sheet_order", "commit_version"])
    rows.sort(key=lambda r: (r.sheet_order is None, r.sheet_order or 0, r.sheet_name))
    return [{"sheet_doc": r.name, "sheet_name": r.sheet_name, "sheet_order": r.sheet_order,
             "committed_version": r.commit_version} for r in rows]


def _population_reader(boq):
    """A cached reader: sheet name -> the sheet's Suggest population (extraction.assemble_population, the population a Suggest run
    takes). Lazy, because it is the slow part of the summary: it is read for every sheet only when the default ticks are needed
    (no ticks stored), and otherwise only for the ticked sheets the floor rule reads."""
    from nirmaan_stack.services.boq_rate_master.extraction import assemble_population

    cache = {}

    def read(sheet_name):
        if sheet_name not in cache:
            cache[sheet_name] = assemble_population(boq, sheet_name)[1]
        return cache[sheet_name]

    return read


def _electrical_discipline():
    from nirmaan_stack.services.boq_category import engines

    return (engines.get_engine("electrical") or {}).get("discipline")


def _floor_readings(boq, sheet_name, cv) -> dict:
    """{excel_row: floor_cutting value} for one sheet at its committed version: the row's CURRENT `BoQ Row Helper Edit` first,
    else the ACTIVE Suggest run's result at that version (design P4e). A row with neither is absent (no reading)."""
    readings = {}
    run = frappe.get_all("BoQ Rate Suggestion Run", filters={"boq": boq, "sheet_name": sheet_name, "active": 1,
                                                              "committed_version": cv}, fields=["results"], limit=1)
    for it in (_parse_json(run[0].results, []) if run else []) or []:
        if isinstance(it, dict) and it.get("category_id") == TRAY_CATEGORY:
            v = (it.get("attributes") or {}).get(FLOOR_ATTR)
            readings[it.get("excel_row")] = v.get("value") if isinstance(v, dict) else v
    for r in frappe.get_all("BoQ Row Helper Edit", filters={"boq": boq, "sheet_name": sheet_name, "committed_version": cv,
                                                            "is_current": 1}, fields=["excel_row", "edits"]):
        edit = (_parse_json(r.edits, {}) or {}).get(FLOOR_ATTR)
        if edit is not None:
            readings[r.excel_row] = edit.get("value") if isinstance(edit, dict) else edit
    return readings


def floor_cutting(boq, sheets, ticked, populations, tray_rate) -> dict:
    """THE FLOOR-CUTTING RULE (R-BCS-30, design P4e, owner Q2 = (a)). A row of a TICKED sheet adds qty x the live
    `tray_cutting_amount` when ALL hold: its category is Cable Tray & Raceway; its reading says floor_cutting = Yes; the BoQ charges
    for it (a current install or combined rate > 0); its unit is a LENGTH. A Yes row that fails the charge or the unit goes to
    MENTIONED-NOT-ADDED with its reason; a tray row with no reading is counted only."""
    caught, mentioned, no_reading = [], [], 0
    for s in sheets:
        name, cv = s["sheet_name"], s["committed_version"]
        if name not in ticked:
            continue
        tray = [p["excel_row"] for p in populations.get(name) or [] if p.get("category_id") == TRAY_CATEGORY]
        if not tray:
            continue
        readings = _floor_readings(boq, name, cv)
        no_reading += sum(1 for er in tray if er not in readings)
        yes = [er for er in tray if str(readings.get(er) or "").strip().lower() == "yes"]
        if not yes:
            continue
        charged = {r[0] for r in frappe.db.sql(
            """select distinct excel_row from "tabBoQ Cell Pricing" where boq=%s and sheet_name=%s and committed_version=%s
               and is_current=1 and rate > 0 and rate_kind in %s""", (boq, name, cv, _CHARGED_RATE_KINDS))}
        nodes = {n.source_row_number: n for n in frappe.get_all(
            "BOQ Nodes", filters={"boq": boq, "sheet": s["sheet_doc"], "is_current": 1, "source_row_number": ["in", yes]},
            fields=["source_row_number", "qty", "unit", "description"])}
        for er in sorted(yes):
            n = nodes.get(er) or {}
            row = {"sheet_name": name, "excel_row": er, "text": (n.get("description") or "").strip()[:200],
                   "qty": flt(n.get("qty")), "unit": n.get("unit") or ""}
            reasons = []
            if er not in charged:
                reasons.append("the BoQ does not charge for it (no install or combined rate on the row)")
            if not is_length_unit(row["unit"]):
                reasons.append(f"its unit ({row['unit'] or 'blank'}) is not a length")
            if reasons:
                mentioned.append({**row, "reason": "; ".join(reasons)})
            else:
                caught.append({**row, "amount": row["qty"] * tray_rate if tray_rate is not None else None})
    metres = sum(r["qty"] for r in caught)
    return {"caught": caught, "mentioned": mentioned, "no_reading_rows": no_reading, "metres": metres, "rate": tray_rate,
            "system_amount": metres * tray_rate if tray_rate is not None else None}


def _installation(values, install_rate, floor_system) -> dict:
    """The installation figure: the area part (area x the live Rs per sq ft) and the floor part, each the system's figure unless
    the user edited or removed it (R-BCS-144). Blank (None) when there is no area part: the screen then asks for the area."""
    area = values["area_sqft"]
    area_system = area * install_rate if area and install_rate is not None else None
    area_part = values["area_part"] if values["area_part"] is not None else area_system
    floor_part = values["floor_part"] if values["floor_part"] is not None else floor_system
    return {"area_part_system": area_system, "area_part": area_part, "area_part_changed": values["area_part"] is not None,
            "floor_part_system": floor_system, "floor_part": floor_part, "floor_part_changed": values["floor_part"] is not None,
            "total": None if area_part is None else area_part + (floor_part or 0.0)}


def _summary(boq) -> dict:
    _names, rec = _current_record(boq)
    values = _stored_values(rec)
    amounts = _pricing_input_amounts()
    sheets = _priceable_sheets(boq)
    population = _population_reader(boq)
    stored = values["covered_sheets"]
    default_ticks = None
    if stored is None:  # the default ticks: sheets whose Suggest population is majority Electrical (the design's rule)
        electrical = _electrical_discipline()
        for s in sheets:
            pop = population(s["sheet_name"])
            s["suggest_rows"] = len(pop)
            s["electrical_rows"] = sum(1 for p in pop if electrical and p.get("discipline") == electrical)
            s["default_ticked"] = s["electrical_rows"] * 2 > s["suggest_rows"]
        default_ticks = [s["sheet_name"] for s in sheets if s["default_ticked"]]
    ticked = default_ticks if stored is None else [s["sheet_name"] for s in sheets if s["sheet_name"] in set(stored)]
    floor = floor_cutting(boq, sheets, set(ticked), {n: population(n) for n in ticked}, amounts.get(TRAY_CUTTING_INPUT))
    for s in sheets:
        s["ticked"] = s["sheet_name"] in ticked
        s.pop("sheet_doc", None)
    return {
        "boq": boq,
        "has_record": rec is not None,
        "area_sqft": values["area_sqft"],
        "covered_sheets": stored,
        "rates": {"install_per_sqft": amounts.get(INSTALL_PER_SQFT_INPUT), "tray_cutting": amounts.get(TRAY_CUTTING_INPUT)},
        "carpet_area": _carpet_area(boq),
        "sheets": sheets,
        "default_ticks": default_ticks,
        "ticked": ticked,
        "floor": floor,
        "installation": _installation(values, amounts.get(INSTALL_PER_SQFT_INPUT), floor["system_amount"]),
        "input_version": rec.input_version if rec else None,
        "edited_by": rec.edited_by if rec else None,
        "edited_at": rec.edited_at if rec else None,
    }


# -- the two endpoints ------------------------------------------------------------------------------------------------------
@frappe.whitelist()
def get_boq_summary_inputs(boq=None):
    """The BoQ summary's server half for one BoQ: the current stored inputs, the live Rs per sq ft and Rs per metre, the project's
    carpet area (a hint only), the priceable sheets in sheet order with the default ticks, and the floor-cutting rows of the ticked
    sheets (caught / mentioned-not-added), with the installation figure. PURE READ. Admin and Estimates only.
    URL: /api/method/nirmaan_stack.api.boq.wizard.boq_summary.get_boq_summary_inputs"""
    _require_bcs_cost_access()
    return _summary(_validate_boq(boq))


@frappe.whitelist(methods=["POST"])
def save_boq_summary_inputs(boq=None, area_sqft=None, covered_sheets=None, area_cost_override=None, floor_cut_override=None):
    """Supersede the BoQ's current inputs: every earlier field carried, the sent ones changed. A field not sent (None) stays; ""
    clears it - the area becomes not entered, the ticks go back to the defaults, an installation part goes back to the system's
    figure (R-BCS-144). A number sets it (an override of 0 = the part removed). `covered_sheets` = a list of sheet names (VERBATIM),
    each a priceable sheet of this BoQ. A save that changes nothing writes nothing. Admin and Estimates only. Commits once.
    Returns the summary (as get_boq_summary_inputs) plus `wrote`.
    URL: /api/method/nirmaan_stack.api.boq.wizard.boq_summary.save_boq_summary_inputs"""
    _require_bcs_cost_access()
    boq = _validate_boq(boq)
    # Serialises this BoQ's summary saves until the commit, so two saves cannot both supersede the same record.
    frappe.db.sql('select name from "tabBOQs" where name = %s for update', (boq,))
    prior_names, rec = _current_record(boq)
    old = _stored_values(rec)
    new = dict(old)
    if area_sqft is not None:
        new["area_sqft"] = None if area_sqft == "" else (_number(area_sqft, "area_sqft") or None)
    if covered_sheets is not None:
        new["covered_sheets"] = None if covered_sheets == "" else _valid_ticks(boq, covered_sheets)
    for part, sent in (("area_part", area_cost_override), ("floor_part", floor_cut_override)):
        if sent is not None:
            new[part] = None if sent == "" else _number(sent, PARTS[part][0])
    wrote = new != old
    if wrote:
        _supersede(boq, prior_names, new)
        frappe.db.commit()
    return {**_summary(boq), "wrote": bool(wrote)}


def _valid_ticks(boq, covered_sheets) -> list:
    ticks = frappe.parse_json(covered_sheets) if isinstance(covered_sheets, str) else covered_sheets
    if not isinstance(ticks, list) or not all(isinstance(t, str) for t in ticks):
        frappe.throw("covered_sheets must be a list of sheet names.", title="Invalid covered_sheets")
    priceable = [s["sheet_name"] for s in _priceable_sheets(boq)]
    unknown = [t for t in ticks if t not in priceable]
    if unknown:
        frappe.throw(f"Not a priceable sheet of this BoQ: {', '.join(unknown)}.", title="Invalid covered_sheets")
    return [n for n in priceable if n in set(ticks)]


# -- carrying to a revision (R-BCS-29) --------------------------------------------------------------------------------------
def carry_summary_inputs(source_boq, new_boq, sheet_mapping) -> dict:
    """Copy the source BoQ's CURRENT inputs to a revision (a new BOQs), from `revision.confirm_revision_mapping` - the one place
    both revision entry paths end. The area and both overrides as they are; stored ticks MAPPED through the confirmed sheet
    mapping {original sheet: revised tab}; a ticked sheet with no successor drops (named in the result). Default ticks (none
    stored) stay default. A source with no record copies nothing. Writes in the caller's transaction (no commit); no role check
    (the confirm endpoint's own gates ran). Returns {copied, dropped_ticks, ticks}."""
    if not source_boq or not new_boq:
        return {"copied": False, "dropped_ticks": [], "ticks": None}
    _names, rec = _current_record(source_boq)
    if rec is None or _current_record(new_boq)[1] is not None:
        return {"copied": False, "dropped_ticks": [], "ticks": None}
    values = _stored_values(rec)
    dropped = []
    if values["covered_sheets"] is not None:
        mapped = []
        for t in values["covered_sheets"]:
            if sheet_mapping.get(t):
                mapped.append(sheet_mapping[t])
            else:
                dropped.append(t)
        values["covered_sheets"] = mapped
    _supersede(new_boq, [], values)
    return {"copied": True, "dropped_ticks": dropped, "ticks": values["covered_sheets"]}
