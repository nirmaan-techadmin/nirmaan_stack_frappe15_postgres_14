# Copyright (c) 2026, Nirmaan (Stratos Infra Technologies Pvt. Ltd.) and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class BoQAISuggestRunRecord(Document):
	pass


def on_doctype_update():
	"""SRS-1: the run_id index, by an explicit name (Frappe runs this on every migrate). Postgres index names are
	schema-wide and the field-named index `search_index` asks for ("run_id") already exists on another table, so
	Frappe's own `CREATE INDEX IF NOT EXISTS run_id` silently made none here."""
	frappe.db.add_index("BoQ AI Suggest Run Record", ["run_id"], index_name="boq_ai_suggest_run_record_run_id_index")
