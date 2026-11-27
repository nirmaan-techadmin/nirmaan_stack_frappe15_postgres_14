"""SRS-2 - the "AI Suggest Records" endpoints (owner R2 25 Nov 23:34 "only admins"; R3 QR-WHERE (a); R4 the mockup).

ADMIN ONLY, checked FIRST in every method: Administrator or the Nirmaan Admin Profile (`wizard/pricing._is_nirmaan_admin`,
imported, never copied - the Rate Master's own rule). Everyone else gets PermissionError before anything is read.
Thin (CODING_STANDARDS B4): the reads, the display rules and the downloads live in `services/boq_suggest_store`.

  list_records(filters, page)       50 a page, newest run first           -> {rows, total, page, page_size, filters}
  filter_options()                  the dropdowns' choices                -> {projects, boqs, sheets, ...}
  get_record(name)                  one row + its question + its run      -> the detail
  export_records(filters, kind)     "summary" (<= 50,000) / "full" (<= 5,000) -> {filename, content_type, content_base64, ...}
  reprice_run_record(name)          (re)price one Run Record's rows now (no screen button; SRS-2 B3)
Nothing here edits or deletes a record.
"""

import frappe

from nirmaan_stack.api.boq.wizard.pricing import _is_nirmaan_admin
from nirmaan_stack.services.boq_suggest_store import export, rates, records


def _require_admin():
    if not _is_nirmaan_admin(frappe.session.user):
        frappe.throw("Only an admin may open the AI Suggest Records.", frappe.PermissionError, title="Not permitted")


@frappe.whitelist()
def list_records(filters=None, page=1):
    _require_admin()
    return records.list_records(filters, page)


@frappe.whitelist()
def filter_options():
    _require_admin()
    return records.filter_options()


@frappe.whitelist()
def get_record(name=None):
    _require_admin()
    return records.get_record(name)


@frappe.whitelist(methods=["POST"])
def export_records(filters=None, kind=None):
    _require_admin()
    return export.build(filters, kind or export.SUMMARY)


@frappe.whitelist(methods=["POST"])
def reprice_run_record(name=None):
    _require_admin()
    if not name or not frappe.db.exists(rates.DT_RUN, name):
        frappe.throw("No such AI Suggest run record: %s" % name, frappe.DoesNotExistError)
    return rates.price_run_record(name)
