"""SRS-2 - the suggested rates for every stored row (SRS-D0 D3; owner R1 25 Nov 23:30, QR-RATES (a) 27 Nov 12:50).

After every Suggest pass that read rows, a follow-up background operation prices that pass's Row Records with the SERVER
PRICING STEP (`services/boq_rate_match/pricing_step.price_rows`: the panel's own pricing code, run under `node`) and
writes, per row: `supply_rate` / `install_rate` / `combined_rate`, `rates_status`, `rates_detail`, `pricing_stamp`.
Nothing here prices: there is no pricing logic in Python.

THE STATUS (owner QR-C3, 27 Nov 15:03: `rates_status` is the ONLY truth for "priced"; a 0 is never shown as a price):
  * "priced"                        - the helper priced the row; the figures of the kinds in `rates_detail.scope` are real;
  * "not priced: <reason>"          - the step ran and the helper priced nothing for this row (e.g. no SKU);
  * "rates not computed: <reason>"  - the step could not run (no bundle, a timeout, an error, a re-committed sheet).
A kind the helper did not price (outside `scope`) stays 0 in the column (Currency is NOT NULL on Postgres) and is never
shown. `bcs_supply_rate` is NEVER written here (R9: the BCS lane fills it after its merge).

THE ROW RECORDS the step reads (QR-INPUTS): `attributes` / `items` / `description` / `category_id` come from the STORE
(`final_attributes` is the run's own result row, never re-derived). The step also needs what the store does not hold -
the row's unit (`BOQ Nodes.unit`), its headings (`build_sheet_context`), its resolved category / discipline
(`extraction._resolved_categories`) and the sheet's page rows (`review_screen.get_committed_rows`, read only) - read at
pricing time by the SAME functions `pricing_step.sheet_inputs` uses for the tracked replay, and ONLY when the sheet's
current committed version is the record's; what was read goes into `rates_detail.inputs`. `sheet_inputs` itself is not
used: it reads the ACTIVE run, which skips a partial pass.

NEVER FAILS ANYTHING. The job is its own operation, queued after the Suggest run's commit and the store's finish; every
public function here has its own try / except, writes at most ONE Error Log per pass (`ERROR_TITLE`) and never raises.

RAW SQL, on purpose (CODING_STANDARDS § Writing raw SQL): the Row Record doctype has no doc_events, no controller hooks,
`track_changes` 0 and nothing derived from it (SRS-1's stated reason), so a raw UPDATE skips nothing; and the job runs as
the user who started Suggest, who must be able to fill records they cannot read. Each UPDATE names the read it priced
(`run_record` AND `run_date`): a row a LATER pass has re-read since (reset to 0 + "pending" by the store) is left for that
later pass's own job, never overwritten with an older read's figures.
"""

import json
import time
import uuid

import frappe

from nirmaan_stack.services.boq_suggest_store import store as suggest_store

DT_ROW = suggest_store.DT_ROW
DT_RUN = suggest_store.DT_RUN
PRICED = "priced"
NOT_PRICED = "not priced: "
NOT_COMPUTED = "rates not computed: "
KINDS = ("supply_rate", "install_rate", "combined_rate")
ERROR_TITLE = "BoQ suggest store rates failed"
TRIGGER_ERROR_TITLE = "BoQ suggest store rates trigger failed"
OPERATION_KIND = "boq_suggest_rates"
WORKER = "nirmaan_stack.services.boq_suggest_store.rates.rates_worker"
JOB_TIMEOUT_SEC = 1800
STATUS_MAX = 140          # rates_status is a Data column: varchar(140)
STAMP_MAX = 140           # pricing_stamp is a Data column: varchar(140)
DETAIL_LINES_MAX = 12     # rates_detail keeps the priced lines SHORT
DETAIL_BLANKS_MAX = 8


# ── the status rule (pure: no database) ──────────────────────────────────────────────────────────────────────────────
def _clip(text, limit):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def not_computed(reason):
    return _clip(NOT_COMPUTED + (reason or "unknown reason"), STATUS_MAX)


def row_outcome(priced_row):
    """What ONE row of `price_rows(...)["rows"]` means for the store. Pure. -> (status, {kind: figure}, detail).

    `priced_row` is None when the step returned nothing for the row. Figures are given only for the kinds the pricer
    priced (its `scope`), and only when the row is priced."""
    if not priced_row:
        return not_computed("the pricing step returned nothing for this row"), {}, {}
    rec = priced_row.get("rec") or {}
    values = rec.get("values") if isinstance(rec.get("values"), dict) else {}
    scope = [k for k in (rec.get("scope") or []) if k in KINDS and isinstance(values.get(k), (int, float))]
    detail = {
        "mode": rec.get("mode"),
        "scope": scope,
        "lines": list(rec.get("lines") or [])[:DETAIL_LINES_MAX],
        "blanks": list(rec.get("blanks") or [])[:DETAIL_BLANKS_MAX],
    }
    if rec.get("kind") == "error":
        return not_computed("the pricing step failed on this row"), {}, detail
    if priced_row.get("priced") and scope:
        return PRICED, {k: float(values[k]) for k in scope}, detail
    reason = rec.get("reason") or "; ".join(str(b) for b in (rec.get("blanks") or [])[:3]) or "the helper priced nothing"
    return _clip(NOT_PRICED + str(reason), STATUS_MAX), {}, detail


def stamp_text(stamp):
    """The pricing stamp as one short text: `<code hash>|<asset version>` (pricing_step.current_stamp's two parts)."""
    if not isinstance(stamp, dict):
        return None
    return _clip("%s|%s" % (stamp.get("code") or "", stamp.get("asset") or ""), STAMP_MAX)


# ── the trigger (called by the Suggest worker after the run's commit and store.finish) ─────────────────────────────────
def queue_after_pass(store_pass):
    """Queue the rates job for a pass whose Run Record has rows written. -> the operation id, or None (store off, no
    Run Record, no row written, or the queue call failed). Never raises; never touches the run."""
    try:
        if not getattr(store_pass, "enabled", False) or not getattr(store_pass, "name", None):
            return None
        if not getattr(store_pass, "rows_written", 0):
            return None   # no row written = the model read nothing in this pass: nothing to price
        from nirmaan_stack.services import background_ops

        op_id = str(uuid.uuid4())
        background_ops.start(OPERATION_KIND, WORKER, op_id=op_id, timeout=JOB_TIMEOUT_SEC, run_record=store_pass.name)
        # background_ops.start queues on the commit; the run and the store have committed already, so this commit
        # carries only the queue call (CODING_STANDARDS § Queuing a background operation).
        frappe.db.commit()
        return op_id
    except Exception:  # noqa: BLE001 -- never fail or change the Suggest run
        try:
            frappe.db.rollback()
            frappe.log_error(title=TRIGGER_ERROR_TITLE, message=frappe.get_traceback())
            frappe.db.commit()
        except Exception:  # noqa: BLE001
            pass
        return None


def rates_worker(run_record=None):
    """The operation's work (runs as the Suggest user, under background_ops.run). Never raises."""
    return price_run_record(run_record)


# ── the job ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def _rows_of(run_record):
    return frappe.db.sql(
        """select name, boq, sheet_name, committed_version, excel_row, boq_node, description, discipline, category_id,
                  run_record, run_date, final_attributes
           from "tabBoQ AI Suggest Row Record" where run_record = %s order by boq, sheet_name, excel_row""",
        (run_record,), as_dict=True)


def _json(v):
    if isinstance(v, (dict, list)) or v is None:
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return None


def sheet_inputs_for(boq, sheet_name, committed_version, records):
    """What the step needs beyond the store, read from the sheet NOW (see the module docstring).
    -> (page_rows, {excel_row: {"unit", "headings", "resolved_category", "discipline", "description"}}, None) or
       (None, None, reason) when the sheet's current committed version is not the records'."""
    from nirmaan_stack.api.boq.wizard.review_screen import get_committed_rows
    from nirmaan_stack.services.boq_category.context_builder import build_sheet_context
    from nirmaan_stack.services.boq_rate_master.extraction import _resolved_categories
    from nirmaan_stack.services.boq_rate_match.pricing_step import PAGE_KEYS

    cur = frappe.db.get_value("BoQ Sheet", {"boq": boq, "sheet_name": sheet_name, "is_current": 1},
                              ["name", "commit_version"], as_dict=True)
    if not cur:
        return None, None, "the sheet has no current committed version"
    if int(cur["commit_version"] or 0) != int(committed_version or 0):
        return None, None, "the sheet was re-committed (version %s, now %s)" % (committed_version, cur["commit_version"])
    ctx = build_sheet_context(boq, sheet_name)
    by_row = {x["excel_row"]: x for x in ctx["rows"]}
    page = [{k: pr.get(k) for k in PAGE_KEYS}
            for pr in (get_committed_rows(boq_name=boq, sheet_name=sheet_name).get("rows") or [])]
    resolved = _resolved_categories(boq, sheet_name, cur["commit_version"])
    nodes = [r["boq_node"] for r in records if r.get("boq_node")]
    units = dict(frappe.db.sql('select name, unit from "tabBOQ Nodes" where name in %s', (tuple(nodes),))) if nodes else {}
    out = {}
    for r in records:
        er = int(r["excel_row"])
        cx = by_row.get(er) or {}
        cat, disc = resolved.get(er, (None, None))
        out[er] = {"unit": units.get(r.get("boq_node")),
                   "headings": [a.get("description") or "" for a in cx.get("ancestors") or []],
                   "resolved_category": cat, "discipline": disc, "description": cx.get("description")}
    return {f"{boq}|{sheet_name}": page}, out, None


def step_row(record, inputs):
    """ONE row record for `price_rows`, built as `pricing_step.sheet_inputs` builds it, from the store's
    `final_attributes` (the run's own result row) plus the sheet inputs."""
    fa = _json(record.get("final_attributes")) or {}
    inp = inputs.get(int(record["excel_row"])) or {}
    category = fa.get("category_id") or record.get("category_id")
    return {"boq": record["boq"], "sheet_name": record["sheet_name"], "excel_row": int(record["excel_row"]),
            "run_id": None, "category_id": category,
            "resolved_category": inp.get("resolved_category") if inp.get("resolved_category") is not None else category,
            "discipline": inp.get("discipline"),
            "description": fa.get("description") or inp.get("description") or record.get("description") or "",
            "unit": inp.get("unit"), "headings": inp.get("headings") or [],
            "attributes": fa.get("attributes") or {}, "items": fa.get("items")}


def _write(record, status, figures, detail, stamp):
    """Write ONE row's rates - only while the row still holds the read that was priced. -> rows updated (0 or 1)."""
    frappe.db.sql(
        """update "tabBoQ AI Suggest Row Record"
           set supply_rate = %s, install_rate = %s, combined_rate = %s, rates_status = %s, rates_detail = %s,
               pricing_stamp = %s
           where name = %s and run_record = %s and run_date = %s""",
        (figures.get("supply_rate", 0), figures.get("install_rate", 0), figures.get("combined_rate", 0), status,
         json.dumps(detail, default=str), stamp_text(stamp), record["name"], record["run_record"], record["run_date"]))
    return 1


def _log(run_record, reason):
    try:
        frappe.log_error(title=ERROR_TITLE, message="run_record=%s\n%s\n%s" % (run_record, reason, frappe.get_traceback()))
        frappe.db.commit()
    except Exception:  # noqa: BLE001
        try:
            frappe.db.rollback()
        except Exception:  # noqa: BLE001
            pass


def price_run_record(run_record, *, build_dir=None, timeout=None):
    """Price every Row Record of one Run Record and write the outcome on each. -> {"run_record", "rows", "counts",
    "ms", "reason"}. Never raises; on any failure the rows read "rates not computed: <reason>" and ONE Error Log is
    written for the pass."""
    from nirmaan_stack.services.boq_rate_match import pricing_step

    t0 = time.monotonic()
    counts = {}
    rows = []
    try:
        rows = _rows_of(run_record) if run_record else []
        groups = {}
        for r in rows:
            groups.setdefault((r["boq"], r["sheet_name"], r["committed_version"]), []).append(r)
        failed = None
        for (boq, sheet_name, cv), recs in groups.items():
            page_rows, inputs, why = sheet_inputs_for(boq, sheet_name, cv, recs)
            if why:
                outcomes = [(r, not_computed(why), {}, {"inputs": {"committed_version": cv}}, None) for r in recs]
            else:
                step_rows = [step_row(r, inputs) for r in recs]
                kw = {"build_dir": build_dir}
                if timeout:
                    kw["timeout"] = timeout
                res = pricing_step.price_rows(page_rows, step_rows, **kw)
                outcomes = []
                for r, sr in zip(recs, step_rows):
                    used = {"committed_version": cv, "unit": sr["unit"], "resolved_category": sr["resolved_category"],
                            "discipline": sr["discipline"], "headings": len(sr["headings"])}
                    if not res.get("available"):
                        failed = failed or res.get("reason")
                        outcomes.append((r, not_computed(res.get("reason")), {}, {"inputs": used}, None))
                        continue
                    status, figures, detail = row_outcome(res["rows"].get(f"{boq}|{sheet_name}|{sr['excel_row']}"))
                    detail["inputs"] = used
                    detail["stamp"] = res.get("stamp")
                    outcomes.append((r, status, figures, detail, res.get("stamp")))
            ms = round((time.monotonic() - t0) * 1000)
            for r, status, figures, detail, stamp in outcomes:
                detail["job"] = {"rows": len(rows), "ms": ms, "at": str(frappe.utils.now_datetime())}
                _write(r, status, figures, detail, stamp)
                key = status if status == PRICED else status.split(":", 1)[0]
                counts[key] = counts.get(key, 0) + 1
        frappe.db.commit()
        if failed:
            _log(run_record, "pricing step unavailable: %s" % failed)
        return {"run_record": run_record, "rows": len(rows), "counts": counts,
                "ms": round((time.monotonic() - t0) * 1000), "reason": failed}
    except Exception as e:  # noqa: BLE001 -- never raise into anything (the job, the Admin method)
        reason = "pricing step error: %s: %s" % (type(e).__name__, e)
        try:
            frappe.db.rollback()
        except Exception:  # noqa: BLE001
            pass
        _mark_all_not_computed(rows, reason)
        _log(run_record, reason)
        return {"run_record": run_record, "rows": len(rows), "counts": {"rates not computed": len(rows)},
                "ms": round((time.monotonic() - t0) * 1000), "reason": reason}


def _mark_all_not_computed(rows, reason):
    try:
        for r in rows:
            _write(r, not_computed(reason), {}, {"error": _clip(reason, 500)}, None)
        frappe.db.commit()
    except Exception:  # noqa: BLE001
        try:
            frappe.db.rollback()
        except Exception:  # noqa: BLE001
            pass
