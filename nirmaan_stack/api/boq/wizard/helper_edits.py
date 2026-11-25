# Copyright (c) 2026, Nirmaan (Stratos Infra Technologies Pvt. Ltd.) and contributors
# For license information, please see license.txt

"""A field changed in a row's rate helper, saved for that row (slice BCS-4; design BCS-D0 P3).

The pricing page's rate helper opens from a row's Supply, Install or Combined rate box, or from its BCS supply cost box.
A field the user changes in ANY of those views is saved here per ROW, so every other view of the same row -- and the same
view after a page reload -- starts from it (owner R1). The panel seeds its attribute overrides from these edits before its
first compute, and the compute already prefers an override to the extraction, so there is no new pricing path.

WHAT THIS NEVER DOES (owner R2: "only suggested rate changes"):
  * it writes ONLY `BoQ Row Helper Edit`. There is no path from here to `save_cell_price` or `save_row_bcs_rates`: a cell's
    rate (BoQ Cell Pricing) and a BCS cost (BoQ Row BCS Rate) are never written, so a value already in a cell is never
    altered. This module imports neither `bcs` nor the pricing writers.
  * a typed final value is never stored (the panel keeps it per session).
  * a new committed version reads no edit of an older one (owner R4: rates are copied to the next version explicitly);
    every read and write is keyed on the committed version.
  * a fresh Suggest run does NOT keep an edit on a row it writes: owner R-BCS-140 (2026-11-26, replacing R-BCS-45 / R3)
    -- the run's own output replaces it. The worker calls `supersede_edits_for_rows` with the rows its model read, after
    its commit; the superseded records stay as history. Rows the run did not write keep their edits.

GATES (the shape of `save_row_bcs_rates`, every gate before any write so a refusal writes nothing):
  1. the session user may price on the BoQ pages (BCS-4 Question 1 option (a): the backend wizard set
     `create_from_template._WIZARD_ROLE_PROFILES`, imported, never re-listed; Administrator allowed). No cost is stored
     here, so this is NOT the cost gate.
  2. the committed cell exists      (pricing._resolve_committed_cell -- the same refusal save_row_bcs_rates gives)
  3. the sheet is not locked        (pricing._guard_sheet_not_locked -- the same refusal)
  4. the single-editor pricing lock (pricing_lock.acquire_or_refresh -- the same BOQ_PRICING_LOCKED refusal)
The BCS readiness gate is NOT run: an edit is not a cost.

STORAGE: freeze-and-supersede, one is_current=1 record per (boq, sheet_name VERBATIM #152, excel_row, committed_version).
`edits` = {attr_id: {value, from_kind, by, at}}. A save writes a new current record carrying every earlier key plus the new
one; clearing one key writes a new current record without it; clearing the last key, or all keys, ends the current record
(no new one). The prior current is frozen with frappe.db.set_value(is_current=0): `BoQ Row Helper Edit` has no doc_events
and nothing is derived from the flag, so the raw write skips nothing.

Public API:
  get_row_helper_edits(boq_name, sheet_name, committed_version)                               [whitelisted, GET]
  save_row_helper_edit(boq_name, sheet_name, excel_row, committed_version, attr_id, value,
                       from_kind, category_id=None)                                           [whitelisted POST]
  clear_row_helper_edits(boq_name, sheet_name, excel_row, committed_version, attr_id=None)    [whitelisted POST]
"""
from __future__ import annotations

import json

import frappe
from frappe.utils import now_datetime

from nirmaan_stack.api.boq.wizard.create_from_template import _WIZARD_ROLE_PROFILES
from nirmaan_stack.api.boq.wizard.pricing import (
    _coerce_int,
    _current_sheet_name,
    _guard_sheet_not_locked,
    _resolve_committed_cell,
)
from nirmaan_stack.api.boq.wizard.pricing_lock import acquire_or_refresh

_EDIT = "BoQ Row Helper Edit"

# The views of a row's helper an edit can be made in -- the stored vocabulary of `from_kind` (BCS-D0 P3b). The panel
# names them from its own kind labels; the server only checks the word is one of these.
FROM_KINDS = ("supply", "install", "combined", "bcs_supply")

# BCS-4 Question 1 option (a): plain words, no mention of cost (none is stored here).
_ROLE_REFUSAL = "You are not permitted to change the rate helper on this sheet."


# -- small shared helpers -----------------------------------------------------------------------------------------
def _require(value, field: str) -> None:
    """The same required-argument refusal as bcs._require."""
    if value is None or value == "":
        frappe.throw(f"{field} is required.", title=f"Missing field: {field}")


def _role_profile_of(user: str | None):
    """The user's role profile, read where `create_from_template._ensure_wizard_role` reads it (Nirmaan Users)."""
    if not user or user == "Guest":
        return None
    return frappe.db.get_value("Nirmaan Users", user, "role_profile")


def _require_pricing_page_user() -> str:
    """Refuse (PermissionError) unless the session user may price on the BoQ pages, checked the way
    `_ensure_wizard_role` checks it (BCS-4 Question 1 (a), NOTE 2). Returns the user. A Billing user can open the page but
    is outside the set: refused a save (a one-line switch -- the imported set -- if Billing is to be included)."""
    user = frappe.session.user
    if user == "Administrator":
        return user
    if _role_profile_of(user) not in _WIZARD_ROLE_PROFILES:
        frappe.throw(_ROLE_REFUSAL, frappe.PermissionError)
    return user


def _validate_common_args(boq_name, sheet_name, committed_version) -> int:
    """The same argument checks as bcs._validate_common_args."""
    _require(boq_name, "boq_name")
    _require(sheet_name, "sheet_name")
    _require(committed_version, "committed_version")
    if not frappe.db.exists("BOQs", boq_name):
        frappe.throw(f"BOQs '{boq_name}' not found.", title="Not found")
    return _coerce_int(committed_version, "committed_version")


def _parse_edits(value) -> dict:
    """A JSON column arrives parsed (dict) or raw (str) depending on the read path."""
    if isinstance(value, str):
        try:
            value = json.loads(value) if value else {}
        except (ValueError, TypeError):
            return {}
    return value if isinstance(value, dict) else {}


def _guard_row_writable(boq_name, sheet_name, excel_row, committed_version) -> None:
    """Gates 2 - 4 in save_row_bcs_rates' order, then a row lock so two saves of one sheet cannot both supersede the same
    record. Every refusal comes before any write."""
    _resolve_committed_cell(boq_name, sheet_name, excel_row, committed_version)
    _guard_sheet_not_locked(boq_name, sheet_name, committed_version)
    acquire_or_refresh(boq_name, sheet_name, committed_version, frappe.session.user, now_datetime())
    sheet_row = _current_sheet_name(boq_name, sheet_name, committed_version)
    if sheet_row:
        # Serialises this sheet's helper-edit writes until the commit (Postgres row lock on the committed sheet row).
        frappe.db.sql('select name from "tabBoQ Sheet" where name = %s for update', (sheet_row,))


def _current_record(boq_name, sheet_name, excel_row, committed_version):
    """(names of the is_current=1 records, the newest one's edits). Normally 0 or 1 record (the invariant)."""
    rows = frappe.get_all(
        _EDIT,
        filters={"boq": boq_name, "sheet_name": sheet_name, "excel_row": excel_row,
                 "committed_version": committed_version, "is_current": 1},
        fields=["name", "edits", "edit_version"],
        order_by="edit_version desc",
    )
    return [r.name for r in rows], (_parse_edits(rows[0].edits) if rows else {})


def _next_edit_version(boq_name, sheet_name, excel_row, committed_version) -> int:
    agg = frappe.get_all(
        _EDIT,
        filters={"boq": boq_name, "sheet_name": sheet_name, "excel_row": excel_row,
                 "committed_version": committed_version},
        fields=["max(edit_version) as mv"],
    )
    return ((agg[0].mv if agg else None) or 0) + 1


def _supersede(boq_name, sheet_name, excel_row, committed_version, prior_names, edits, category_id=None):
    """Freeze every prior current record, then write the new current one carrying `edits` -- or none when `edits` is
    empty (the row's current record is ended). Returns the new record's name, or None."""
    for name in prior_names:
        frappe.db.set_value(_EDIT, name, "is_current", 0)
    if not edits:
        return None
    doc = frappe.new_doc(_EDIT)
    doc.boq = boq_name
    doc.sheet_name = sheet_name  # VERBATIM (#152)
    doc.excel_row = excel_row
    doc.committed_version = committed_version
    doc.category_id = category_id
    doc.edits = json.dumps(edits, sort_keys=True)
    doc.edit_version = _next_edit_version(boq_name, sheet_name, excel_row, committed_version)
    doc.is_current = 1
    doc.edited_by = frappe.session.user
    doc.edited_at = frappe.utils.now()
    doc.insert(ignore_permissions=True)
    return doc.name


# -- a fresh Suggest run replaces the edits of the rows it wrote (owner R-BCS-140) -------------------------------------
def supersede_edits_for_rows(boq_name, sheet_name, rows, committed_version) -> int:
    """Owner R-BCS-140 (2026-11-26 00:37, "yes replcae"; replaces R-BCS-45): when a Suggest run WRITES results for a row, that
    row's saved helper edits give way to the run's own output. Every CURRENT record of (boq, sheet_name, excel_row,
    committed_version) for the given rows is frozen (is_current = 0) -- kept as history, never deleted; rows not given keep
    theirs. Called ONCE by the Suggest worker after its own commit (rate_master._suggest_worker), with the rows the pass wrote.

    INTERNAL, not whitelisted: no role check (the run's owner passed start_suggest's gates), no lock (the run already holds
    the sheet's suggest marker). Commits once. NEVER raises -- it is a side effect of a run and must never fail it: any error
    is rolled back and logged once. Returns how many records it froze. Raw write: `BoQ Row Helper Edit` has no doc_events and
    nothing derives from is_current, so frappe.db.set_value skips nothing."""
    try:
        wanted = sorted({int(r) for r in rows or []})
        if not wanted:
            return 0
        names = frappe.get_all(
            _EDIT,
            filters={"boq": boq_name, "sheet_name": sheet_name, "committed_version": int(committed_version),
                     "is_current": 1, "excel_row": ["in", wanted]},
            pluck="name",
        )
        for name in names:
            frappe.db.set_value(_EDIT, name, "is_current", 0)
        if names:
            frappe.db.commit()
        return len(names)
    except Exception:  # noqa: BLE001 -- a side effect of the run: it must never fail it
        try:
            frappe.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        frappe.log_error(title="BoQ suggest: helper edits not replaced", message=frappe.get_traceback())
        return 0


# -- the three endpoints ----------------------------------------------------------------------------------------------
@frappe.whitelist()
def get_row_helper_edits(boq_name=None, sheet_name=None, committed_version=None):
    """Every CURRENT helper edit of one committed (boq, sheet_name VERBATIM #152, committed_version), for the page's one
    load. PURE READ. Returns {boq, sheet_name, committed_version, rows: {excel_row: edits}}; a superseded or ended record,
    and every record of another committed version, is left out.
    URL: /api/method/nirmaan_stack.api.boq.wizard.helper_edits.get_row_helper_edits"""
    _require_pricing_page_user()
    committed_version = _validate_common_args(boq_name, sheet_name, committed_version)
    records = frappe.get_all(
        _EDIT,
        filters={"boq": boq_name, "sheet_name": sheet_name, "committed_version": committed_version, "is_current": 1},
        fields=["excel_row", "edits", "edit_version"],
        order_by="excel_row asc, edit_version asc",
    )
    rows: dict = {}
    for r in records:
        edits = _parse_edits(r.edits)
        if edits:
            rows[int(r.excel_row)] = edits  # the newest current wins should the invariant ever be broken
    return {"boq": boq_name, "sheet_name": sheet_name, "committed_version": committed_version, "rows": rows}


@frappe.whitelist(methods=["POST"])
def save_row_helper_edit(boq_name=None, sheet_name=None, excel_row=None, committed_version=None,
                         attr_id=None, value=None, from_kind=None, category_id=None):
    """Save ONE helper field for one committed row: a new current record carrying every earlier key plus this one
    ({value, from_kind, by, at}). `value` is the text the panel's setAttr took ("" is a value: it overrides with empty).
    A save that changes nothing (same value, same view) writes nothing. Commits once.
    Returns {ok, name, edits, wrote}.
    URL: /api/method/nirmaan_stack.api.boq.wizard.helper_edits.save_row_helper_edit"""
    user = _require_pricing_page_user()
    committed_version = _validate_common_args(boq_name, sheet_name, committed_version)
    _require(excel_row, "excel_row")
    excel_row = _coerce_int(excel_row, "excel_row")
    _require(attr_id, "attr_id")
    if value is None:
        frappe.throw("value is required.", title="Missing field: value")
    if from_kind not in FROM_KINDS:
        frappe.throw(f"from_kind must be one of {', '.join(FROM_KINDS)}.", title="Invalid from_kind")
    attr_id, value = str(attr_id), str(value)

    _guard_row_writable(boq_name, sheet_name, excel_row, committed_version)

    prior_names, edits = _current_record(boq_name, sheet_name, excel_row, committed_version)
    old = edits.get(attr_id) or {}
    if old.get("value") == value and old.get("from_kind") == from_kind:
        return {"ok": True, "name": prior_names[0] if prior_names else None, "edits": edits, "wrote": False}
    edits = {**edits, attr_id: {"value": value, "from_kind": from_kind, "by": user, "at": frappe.utils.now()}}
    name = _supersede(boq_name, sheet_name, excel_row, committed_version, prior_names, edits, category_id)
    frappe.db.commit()
    return {"ok": True, "name": name, "edits": edits, "wrote": True}


@frappe.whitelist(methods=["POST"])
def clear_row_helper_edits(boq_name=None, sheet_name=None, excel_row=None, committed_version=None, attr_id=None):
    """Clear a row's saved helper edits: with `attr_id`, that one key (a new current record without it, or the record
    ended when it was the last); without, every key (the row's current record ended). Nothing saved = nothing written.
    Commits once. Returns {ok, name, edits, wrote}.
    URL: /api/method/nirmaan_stack.api.boq.wizard.helper_edits.clear_row_helper_edits"""
    _require_pricing_page_user()
    committed_version = _validate_common_args(boq_name, sheet_name, committed_version)
    _require(excel_row, "excel_row")
    excel_row = _coerce_int(excel_row, "excel_row")

    _guard_row_writable(boq_name, sheet_name, excel_row, committed_version)

    prior_names, edits = _current_record(boq_name, sheet_name, excel_row, committed_version)
    if not prior_names or (attr_id not in (None, "") and str(attr_id) not in edits):
        return {"ok": True, "name": prior_names[0] if prior_names else None, "edits": edits, "wrote": False}
    remaining = {} if attr_id in (None, "") else {k: v for k, v in edits.items() if k != str(attr_id)}
    name = _supersede(boq_name, sheet_name, excel_row, committed_version, prior_names, remaining)
    frappe.db.commit()
    return {"ok": True, "name": name, "edits": remaining, "wrote": True}
