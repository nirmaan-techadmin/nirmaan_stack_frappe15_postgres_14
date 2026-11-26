# Copyright (c) 2026, Nirmaan (Stratos Infra Technologies Pvt. Ltd.) and contributors
# For license information, please see license.txt

"""BoQ Summary Inputs -- what the user enters on the BoQ summary of a BoQ's main page (slice BCS-5; owner R4 - R6).

ONE record per BoQ is current (freeze-and-supersede, input_version / is_current / edited_at), enforced by the write path
(api/boq/wizard/boq_summary.py), not this controller. It holds the area (blank or 0 = not entered), the ticked sheets the one
Electrical installation cost covers ({"sheets": [...]}, blank = the default ticks), and an edit or removal of either installation
part: a Currency figure plus a Check each (Check 0 = the system's figure; Check 1 = the user's figure, 0 = removed) - Frappe writes
a blank Currency as 0, so the Check is what tells "no edit" from "removed" (BCS-5 Question 3 = (a)).

Keyed by the BoQ alone: a sheet re-commit keeps it, "Merge BoQs" keeps it (the BoQ moves, its id does not), and a revision gets a
copy at its sheet-mapping confirmation. Nothing here writes a price, a cost, a rate or a Pricing Input.

A bare controller plus the read-index hook, as boq_row_helper_edit.py.
"""

import frappe
from frappe.model.document import Document


class BoQSummaryInputs(Document):
	pass


def on_doctype_update():
	# The read index for every access shape (the current record of a BoQ: boq + is_current, both equality predicates).
	# Idempotent: add_index no-ops when it exists.
	# AN EXPLICIT, SCHEMA-UNIQUE NAME (BCS-4 lesson): Postgres index names are unique per SCHEMA, and add_index's default name is
	# built from the field names alone (boq_is_current_index), which another table could already hold; add_index runs CREATE
	# INDEX IF NOT EXISTS, so a clashing default would silently give this table NO index.
	frappe.db.add_index(
		"BoQ Summary Inputs",
		["boq", "is_current"],
		index_name="boq_summary_inputs_boq_current_index",
	)
