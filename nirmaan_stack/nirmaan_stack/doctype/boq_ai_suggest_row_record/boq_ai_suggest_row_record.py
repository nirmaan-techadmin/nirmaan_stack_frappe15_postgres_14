# Copyright (c) 2026, Nirmaan (Stratos Infra Technologies Pvt. Ltd.) and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

# SRS-1: the overwrite key - ONE record per (boq, sheet_name, committed_version, excel_row). The store's upsert
# (`services/boq_suggest_store/store.py`, `INSERT ... ON CONFLICT`) names exactly these columns.
ROW_KEY_FIELDS = ["boq", "sheet_name", "committed_version", "excel_row"]
ROW_KEY_CONSTRAINT = "boq_ai_suggest_row_record_key_unique"


class BoQAISuggestRowRecord(Document):
	pass


def on_doctype_update():
	"""The UNIQUE overwrite key, and the project filter's index (Frappe runs this on every migrate). Names are explicit:
	Postgres index names are schema-wide, and the field-named index `search_index` asks for ("project") already exists
	on another table, so Frappe's own `CREATE INDEX IF NOT EXISTS project` silently made none here."""
	frappe.db.add_unique("BoQ AI Suggest Row Record", ROW_KEY_FIELDS, constraint_name=ROW_KEY_CONSTRAINT)
	frappe.db.add_index("BoQ AI Suggest Row Record", ["project"], index_name="boq_ai_suggest_row_record_project_index")
