"""SRS-1 (SRS-D0 D7; owner R-BCS-139 "2 only admins", 27 Nov walk-through): the Suggest run store is readable by
Admins only - Administrator, or a Nirmaan Users row with the Admin profile (`pricing._is_nirmaan_admin`, imported,
never edited; the same rule as the Rate Master's `_require_rate_admin`).

Why hooks and not only DocPerm rows: System Manager - the role the three doctypes' DocPerm rows name - is also held by
the Estimates, PMO and HR profiles (SRS-D0 roles_out.txt), and no Frappe role singles out Admin. So `hooks.py` wires
these two functions for the three doctypes; they are what `frappe.client.get_list / get / get_count`, the Desk list and
report views and `reportview.export_query` honour. A `has_permission` hook can only DENY, never grant.

The worker writes with raw SQL (store.py), so an Estimates user's Suggest run still produces records they cannot read.
"""

import frappe

from nirmaan_stack.api.boq.wizard.pricing import _is_nirmaan_admin

STORE_DOCTYPES = ("BoQ AI Suggest Question", "BoQ AI Suggest Run Record", "BoQ AI Suggest Row Record")


def is_store_reader(user=None):
    """True for Administrator or an Admin-profile user; False for everyone else (Guest included)."""
    user = user or frappe.session.user
    if not user or user == "Guest":
        return False
    return bool(_is_nirmaan_admin(user))


def has_permission(doc, ptype=None, user=None, debug=False):
    """`has_permission` hook for the three store doctypes: None (defer to DocPerm) for a store reader, False otherwise."""
    return None if is_store_reader(user) else False


def get_permission_query_conditions(user=None, doctype=None):
    """`permission_query_conditions` hook: no extra condition for a store reader; no rows for anyone else."""
    return "" if is_store_reader(user) else "1=0"
