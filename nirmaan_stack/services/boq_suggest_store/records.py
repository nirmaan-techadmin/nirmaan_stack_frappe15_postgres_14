"""SRS-2 - the "AI Suggest Records" reads: the filtered, paged list, one record's detail, the filter choices, and the
display rules every reader shares (the page, the row detail and both Excel downloads; SRS-D0 D8, owner R4 27 Nov 13:53).

ADMIN ONLY. This module does not check who is asking: the ONE gate is in the endpoints (`api/boq/suggest_records.py`,
`_is_nirmaan_admin` FIRST); the doctypes' own permission hooks (SRS-1) keep Desk and the generic list APIs closed too.

THE DISPLAY RULES (one place):
  * rates (owner R8 / QR-C3): a figure is shown ONLY when `rates_status` is "priced" AND the kind is in the pricer's
    `scope` (`rates_detail.scope`); otherwise None - never a 0 (`shown_rates`);
  * the BCS supply figure (BCS-FX, owner R-BCS-182): the SUGGESTED BCS supply the rates job recorded at the run
    (`rates_detail.bcs`), never the column `bcs_supply_rate` alone (its 0 is Currency's NOT NULL default) - a figure, or
    `NO_FIGURE` ("-") when the helper gave none or the row is still pending, or `BCS_NOT_RECORDED` for a record written
    before the BCS merge (no `bcs` key; never recomputed by the readers - SRS-2's Admin reprice, no button, re-prices the
    whole record, BCS included) - `shown_bcs`;
  * final values (owner R6): "attr = value; ..." in the category's attribute order (`final_pairs` / `final_text`).
"""

import json

import frappe

from nirmaan_stack.services.boq_suggest_store import rates as suggest_rates
from nirmaan_stack.services.boq_suggest_store import store as suggest_store

PAGE_SIZE = 50
DEFAULT_DAYS = 30
BCS_NOT_RECORDED = "not recorded (run before BCS)"
NO_FIGURE = "-"
STATUS_GROUPS = ("priced", "not priced", "rates not computed", "pending")
FILTER_KEYS = ("date_from", "date_to", "project", "boq", "sheet_name", "discipline", "category_id", "rates_status",
               "run_by", "search")
FIRST_VALUES = 3


# ── display rules (pure) ─────────────────────────────────────────────────────────────────────────────────────────────
def _j(v):
    if v is None or isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return None


def shown_rates(row):
    """{kind: figure or None} - a figure only for a priced row and a kind the pricer priced (R8)."""
    detail = _j(row.get("rates_detail")) or {}
    scope = set(detail.get("scope") or []) if row.get("rates_status") == suggest_rates.PRICED else set()
    return {k: (float(row.get(k) or 0) if k in scope else None) for k in suggest_rates.KINDS}


def shown_bcs(row):
    """The BCS supply as the readers show it (BCS-FX, owner R-BCS-182): a figure, "-" or "not recorded (run before BCS)".

    Read from `rates_detail.bcs` FIRST - a None there is "-", never the column's 0. A row still "pending" (read, not yet
    priced) shows "-"; a row with no `bcs` key was priced before BCS-FX and is never recomputed from today's rules."""
    if row.get("rates_status") == suggest_store.RATES_PENDING:
        return NO_FIGURE
    detail = _j(row.get("rates_detail")) or {}
    if not isinstance(detail, dict) or "bcs" not in detail:
        return BCS_NOT_RECORDED
    v = (detail.get("bcs") or {}).get("supply_rate")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else NO_FIGURE


def _value(v):
    """An attribute's value as text: the reading's `value` when it is a reading, else the value itself."""
    if isinstance(v, dict) and "value" in v:
        v = v.get("value")
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return "None" if v is None else str(v)


def _confidence(v):
    return v.get("confidence") if isinstance(v, dict) else None


def final_pairs(final_attributes, order=()):
    """[(label, value text, confidence)] of a stored result row: the row's attributes in `order` first (the
    category's attribute order), then any other in the row's own order; an item-list row's items after, each
    attribute labelled "<section> / <attr>" (or "item <n> / <attr>" for an item without a section; the first item
    without a section is unlabelled, as the mockup shows it)."""
    fa = _j(final_attributes) or {}
    out = []

    def add(attrs, prefix):
        attrs = attrs or {}
        keys = [k for k in order if k in attrs] + [k for k in attrs if k not in order]
        for k in keys:
            out.append(((prefix + k) if prefix else k, _value(attrs[k]), _confidence(attrs[k])))

    add(fa.get("attributes"), "")
    plain_seen = bool(fa.get("attributes"))
    for n, item in enumerate(fa.get("items") or [], start=1):
        if not isinstance(item, dict):
            continue
        if item.get("section"):
            prefix = "%s / " % item["section"]
        elif not plain_seen:
            prefix, plain_seen = "", True
        else:
            prefix = "item %d / " % n
        add(item.get("attributes"), prefix)
    return out


def final_text(final_attributes, order=(), limit=None):
    pairs = final_pairs(final_attributes, order)[:limit] if limit else final_pairs(final_attributes, order)
    return "; ".join("%s = %s" % (k, v) for k, v, _ in pairs)


def attribute_order(discipline, category_id):
    """The category's attribute order from its ACTIVE config (`attribute_definitions`), [] when there is none."""
    cfg = frappe.db.get_value("BoQ Rate Category Config", {"discipline": discipline, "category_id": category_id,
                                                           "active": 1}, "config")
    cfg = _j(cfg) or {}
    return [d.get("id") for d in (cfg.get("attribute_definitions") or []) if isinstance(d, dict) and d.get("id")]


# ── filters ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def normalise(filters):
    """The filters as the server applies them (unknown keys dropped; run dates default to the last 30 days)."""
    f = _j(filters) if not isinstance(filters, dict) else filters
    f = {k: (str(v).strip() if v is not None else "") for k, v in (f or {}).items() if k in FILTER_KEYS}
    f = {k: v for k, v in f.items() if v}
    today = frappe.utils.getdate(frappe.utils.nowdate())
    f.setdefault("date_to", str(today))
    f.setdefault("date_from", str(frappe.utils.add_days(today, -DEFAULT_DAYS)))
    if f.get("rates_status") and f["rates_status"] not in STATUS_GROUPS:
        frappe.throw("Unknown rates status filter: %s" % f["rates_status"])
    return f


def where(f):
    """(SQL WHERE text, params) for normalised filters, over w = Row Record, rr = Run Record."""
    clauses = ["w.run_date >= %(date_from)s", "w.run_date < %(date_to_next)s"]
    params = {"date_from": f["date_from"], "date_to_next": str(frappe.utils.add_days(f["date_to"], 1))}
    for key in ("project", "boq", "sheet_name", "discipline", "category_id"):
        if f.get(key):
            clauses.append("w.%s = %%(%s)s" % (key, key))
            params[key] = f[key]
    if f.get("run_by"):
        clauses.append("rr.run_by = %(run_by)s")
        params["run_by"] = f["run_by"]
    if f.get("rates_status"):
        if f["rates_status"] in (suggest_rates.PRICED, suggest_store.RATES_PENDING):
            clauses.append("w.rates_status = %(rates_status)s")
            params["rates_status"] = f["rates_status"]
        else:
            clauses.append("w.rates_status like %(rates_status_like)s")
            params["rates_status_like"] = f["rates_status"] + ":%"
    if f.get("search"):
        clauses.append("w.description ilike %(search)s")
        params["search"] = "%" + f["search"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return " and ".join(clauses), params


FROM = ('from "tabBoQ AI Suggest Row Record" w left join "tabBoQ AI Suggest Run Record" rr on rr.name = w.run_record '
        'left join "tabProjects" p on p.name = w.project')
LIST_COLS = ("w.name, w.run_date, w.project, p.project_name, w.boq, w.sheet_name, w.committed_version, w.excel_row, "
             "w.boq_node, w.description, w.discipline, w.category_id, w.final_attributes, w.supply_rate, w.install_rate, "
             "w.combined_rate, w.rates_status, w.rates_detail, w.catalogue_stamp, w.pricing_stamp, w.question, "
             "w.batch_rows, rr.run_by, rr.model, rr.pass_kind, rr.run_id")
ORDER = "order by w.run_date desc, w.boq, w.sheet_name, w.excel_row"


def count(f):
    sql, params = where(f)
    return frappe.db.sql("select count(*) %s where %s" % (FROM, sql), params)[0][0]


def fetch(f, limit=None, offset=0, extra_cols=""):
    sql, params = where(f)
    tail = ""
    if limit is not None:
        tail = " limit %d offset %d" % (int(limit), int(offset))
    return frappe.db.sql("select %s%s %s where %s %s%s" % (LIST_COLS, extra_cols, FROM, sql, ORDER, tail), params,
                         as_dict=True)


def _orders(rows):
    cache = {}
    for r in rows:
        key = (r.get("discipline"), r.get("category_id"))
        if key not in cache:
            cache[key] = attribute_order(*key)
    return cache


def list_row(r, order=()):
    rates = shown_rates(r)
    return {
        "name": r["name"], "run_date": str(r["run_date"]) if r.get("run_date") else None,
        "project": r.get("project"), "project_name": r.get("project_name") or r.get("project"),
        "boq": r["boq"], "sheet_name": r["sheet_name"], "committed_version": r.get("committed_version"),
        "excel_row": r["excel_row"], "boq_node": r.get("boq_node"), "description": r.get("description"),
        "discipline": r.get("discipline"), "category_id": r.get("category_id"),
        "first_values": final_text(r.get("final_attributes"), order, limit=FIRST_VALUES),
        "supply_rate": rates["supply_rate"], "install_rate": rates["install_rate"], "combined_rate": rates["combined_rate"],
        "bcs_supply_rate": shown_bcs(r), "rates_status": r.get("rates_status"), "run_by": r.get("run_by"),
        "model": r.get("model"),
    }


def list_records(filters=None, page=1):
    f = normalise(filters)
    page = max(1, int(page or 1))
    total = count(f)
    rows = fetch(f, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE)
    orders = _orders(rows)
    return {"rows": [list_row(r, orders[(r.get("discipline"), r.get("category_id"))]) for r in rows],
            "total": total, "page": page, "page_size": PAGE_SIZE, "filters": f}


def filter_options():
    """The choices the page's dropdowns offer: what the store holds (names only)."""
    def distinct(col, join=""):
        return [r[0] for r in frappe.db.sql(
            'select distinct %s from "tabBoQ AI Suggest Row Record" w %s where %s is not null and %s != \'\' order by 1'
            % (col, join, col, col))]
    projects = frappe.db.sql(
        'select distinct w.project, coalesce(p.project_name, w.project) from "tabBoQ AI Suggest Row Record" w '
        'left join "tabProjects" p on p.name = w.project where w.project is not null order by 2')
    return {
        "projects": [{"value": a, "label": b} for a, b in projects],
        "boqs": distinct("w.boq"), "sheets": distinct("w.sheet_name"), "disciplines": distinct("w.discipline"),
        "categories": distinct("w.category_id"),
        "run_by": distinct("rr.run_by", 'left join "tabBoQ AI Suggest Run Record" rr on rr.name = w.run_record'),
        "rates_statuses": list(STATUS_GROUPS),
    }


def get_record(name):
    """One record: the row, its question, its run (with the row's own batch entry)."""
    rows = frappe.db.sql("select w.*, p.project_name from \"tabBoQ AI Suggest Row Record\" w left join \"tabProjects\" p "
                         "on p.name = w.project where w.name = %s", (name,), as_dict=True)
    if not rows:
        frappe.throw("No such AI Suggest record: %s" % name, frappe.DoesNotExistError)
    r = rows[0]
    order = attribute_order(r.get("discipline"), r.get("category_id"))
    q = None
    if r.get("question"):
        qs = frappe.db.sql('select name, question_text, category_id, discipline, bytes, first_seen, last_used '
                           'from "tabBoQ AI Suggest Question" where name = %s', (r["question"],), as_dict=True)
        q = qs[0] if qs else None
    run = None
    if r.get("run_record"):
        runs = frappe.db.sql('select name, run_id, suggestion_run, pass_kind, run_by, started_at, finished_at, model, '
                             'ai_status, run_status, halt_reason, catalogue_stamps, batches, rows_read, rows_written '
                             'from "tabBoQ AI Suggest Run Record" where name = %s', (r["run_record"],), as_dict=True)
        run = runs[0] if runs else None
    batch = None
    if run:
        for b in (_j(run.pop("batches")) or {}).get("batches") or []:
            if b.get("batch_no") == r.get("batch_no"):
                batch = b
        run["catalogue_stamps"] = _j(run.get("catalogue_stamps"))
    rates = shown_rates(r)
    return {
        "name": r["name"], "project": r.get("project"), "project_name": r.get("project_name") or r.get("project"),
        "boq": r["boq"], "committed_version": r.get("committed_version"), "sheet_name": r["sheet_name"],
        "excel_row": r["excel_row"], "boq_node": r.get("boq_node"), "description": r.get("description"),
        "discipline": r.get("discipline"), "category_id": r.get("category_id"),
        "run_date": str(r["run_date"]) if r.get("run_date") else None, "run_id": r.get("run_id"),
        "batch_no": r.get("batch_no"), "batch_rows": r.get("batch_rows"), "batch": batch,
        "catalogue_stamp": r.get("catalogue_stamp"),
        "ai_input": r.get("ai_input"), "raw_reply": r.get("raw_reply"), "reply_status": r.get("reply_status"),
        "final_attributes": [{"attribute": k, "value": v, "confidence": c}
                             for k, v, c in final_pairs(r.get("final_attributes"), order)],
        "coercion_trail": _j(r.get("coercion_trail")), "earlier_replies": _j(r.get("earlier_replies")),
        "rates": {**rates, "bcs_supply_rate": shown_bcs(r), "rates_status": r.get("rates_status"),
                  "pricing_stamp": r.get("pricing_stamp"), "detail": _j(r.get("rates_detail"))},
        "question": ({"name": q["name"], "text": q["question_text"], "category_id": q.get("category_id"),
                      "discipline": q.get("discipline"), "bytes": q.get("bytes"),
                      "first_seen": str(q.get("first_seen")), "last_used": str(q.get("last_used"))} if q else None),
        "run": ({k: (str(v) if k in ("started_at", "finished_at") and v else v) for k, v in run.items()} if run else None),
    }
