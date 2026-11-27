"""BCS-6b K2 -- "Previously priced": the PAST row's BCS figures beside its BoQ figures (owner R-BCS-152 Q4 / Q5 a; board 3;
BCS6B Answer 1 Q1-C).

THE ONE READER. `get_match_results` (api/boq/rate_match.py) hands it the shown matches of a sheet; each match names its past
row (boq, sheet_name, excel_row). For a caller who may see cost (`bcs.may_see_bcs_cost`: Administrator or the pricing-access
set, the check BCS-3 / BCS-5 reuse), each match gains three keys:
  bcs_supply / bcs_install / bcs_combined -- that past row's CURRENT `BoQ Row BCS Rate` record (is_current = 1) on the past
  sheet's CURRENT committed version (`BoQ Sheet.commit_version` where is_current = 1), i.e. what that past BoQ holds today (the
  same record filter `bcs.get_sheet_bcs_rates` uses for its grid). No record -> all three None (the pop-up shows "-"); a stored
  0 stays 0. Shown whether or not the past sheet's BCS switch is on ("as stored on that past BoQ").
For anyone else the three keys are ABSENT from the response (not None, not hidden on screen): nothing is read.

READ ONLY: no write, no commit, no new table, no model call. The stored match results are never changed (only the response
dicts). One query per batch of up to `_CHUNK` past rows (a sheet's whole match list in one or a few round trips), never one
per row.
"""
import frappe

BCS_KEYS = ("bcs_supply", "bcs_install", "bcs_combined")
_CHUNK = 500


def _past_row_key(m):
    """(boq, sheet_name, excel_row) of a shown match, or None when the match names no past row."""
    if not m.get("boq") or not m.get("sheet_name") or m.get("excel_row") in (None, ""):
        return None
    return (m["boq"], m["sheet_name"], int(m["excel_row"]))


def past_row_bcs(keys):
    """{(boq, sheet_name, excel_row): (supply_rate, install_rate, combined_rate)} for every key that has a current BCS record on
    its sheet's current committed version. Keys without one are simply absent. Read only."""
    keys = sorted(set(keys))
    out = {}
    for i in range(0, len(keys), _CHUNK):
        chunk = keys[i:i + _CHUNK]
        cond = " or ".join(["(r.boq = %s and r.sheet_name = %s and r.excel_row = %s)"] * len(chunk))
        vals = [v for k in chunk for v in k]
        for b, sn, er, sup, ins, comb in frappe.db.sql(f'''select r.boq, r.sheet_name, r.excel_row,
                    r.supply_rate, r.install_rate, r.combined_rate
                from "tabBoQ Row BCS Rate" r
                join "tabBoQ Sheet" s on s.boq = r.boq and s.sheet_name = r.sheet_name and s.is_current = 1
                    and r.committed_version = s.commit_version
                where r.is_current = 1 and ({cond})''', vals):
            out[(b, sn, int(er))] = (sup, ins, comb)
    return out


def attach_past_row_bcs(rows, user=None):
    """Give every shown match of `rows` (get_match_results' rows, each with "matches") the three BCS keys - ONLY when the
    caller may see cost; otherwise leave every match untouched (the keys absent). Returns True when the keys were attached."""
    from nirmaan_stack.api.boq.wizard.bcs import may_see_bcs_cost

    if not may_see_bcs_cost(user):
        return False
    matches = [m for r in rows or [] for m in (r.get("matches") or [])]
    found = past_row_bcs(k for k in (_past_row_key(m) for m in matches) if k)
    for m in matches:
        k = _past_row_key(m)
        fig = found.get(k) if k else None
        for key, v in zip(BCS_KEYS, fig or (None, None, None)):
            m[key] = None if v is None else float(v)
    return True
