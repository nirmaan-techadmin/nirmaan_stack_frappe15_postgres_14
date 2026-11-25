# Copyright (c) 2026, Nirmaan (Stratos Infra Technologies Pvt. Ltd.) and contributors
# For license information, please see license.txt

"""BoQ Row Helper Edit -- a field the user changed in a row's rate helper, saved for that row (slice BCS-4).

The pricing page's rate helper opens from a row's Supply, Install or Combined rate box, or from its BCS supply cost box.
A field changed in ANY of those views is saved here, per ROW, and every other view of the same row starts from it, after a
page reload too (owner R1, BCS-D0 P3). Only the helper's SUGGESTED figures change: nothing here writes a cell's rate
(BoQ Cell Pricing) or a BCS cost (BoQ Row BCS Rate), and a typed final value is never stored (owner R2).

IDENTITY = (boq, sheet_name [VERBATIM #152], excel_row, committed_version), per row with no column. A new committed version
reads no edit of an older one (owner R4: rates are copied to the next version explicitly).

`edits` = {attr_id: {value, from_kind, by, at}} for every key the helper's setAttr takes; from_kind = the view the edit was
made in (supply / install / combined / bcs_supply), which the panel turns into its "changed by you" / "carried from the ...
helper" tag.

LIFECYCLE = freeze-and-supersede (edit_version / is_current / edited_at), as BoQ Row BCS Rate: exactly one is_current=1
record per identity, enforced by the write path (api/boq/wizard/helper_edits.py), not this controller. A save writes a new
current record carrying every earlier key plus the new one; clearing every key ends the current record.

A bare controller plus the read-index hook, as boq_row_bcs_rate.py.
"""

import frappe
from frappe.model.document import Document


class BoQRowHelperEdit(Document):
	pass


def on_doctype_update():
	# Composite read index for both access shapes, all equality predicates:
	#   sheet read (get_row_helper_edits)        -> the 4-column prefix (boq, sheet_name, committed_version, is_current)
	#   row lookup (save / clear, the supersede) -> all 5 columns.
	# The same columns as BoQ Row BCS Rate's index. Idempotent: add_index no-ops when it exists.
	# ⚠️ AN EXPLICIT NAME, NOT add_index's DEFAULT (BCS-4, found at the migrate): Postgres index names are unique per SCHEMA,
	# not per table, and the default name is built from the field names alone -- boq_sheet_name_committed_version_is_current_
	# excel_row_index -- which BoQ Row BCS Rate's index already holds. add_index runs CREATE INDEX IF NOT EXISTS, so with the
	# default name this table silently got NO index (the migrate printed nothing).
	frappe.db.add_index(
		"BoQ Row Helper Edit",
		["boq", "sheet_name", "committed_version", "is_current", "excel_row"],
		index_name="boq_row_helper_edit_sheet_row_index",
	)
