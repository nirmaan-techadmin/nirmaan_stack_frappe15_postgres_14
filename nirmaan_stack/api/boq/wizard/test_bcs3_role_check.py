# Copyright (c) 2026, Nirmaan (Stratos Infra Technologies Pvt. Ltd.) and contributors
"""BCS-3 -- THE SERVER ROLE CHECK FOR BCS COST (owner R2 "1a", 2026-11-24 13:54; answer 1 "1a, 2a", 15:38).

Only Admin and Estimates (the pricing-access set, `api/pricing/workbook.py` PRICING_ACCESS_SET) may switch BCS on, write a
cost or READ a cost. What each test protects:
  (+) an Estimates user passes the gate on every BCS service (switch on, save, read) and on the cost content of the two
      rate-master data services;
  (-) a Procurement user (and a PMO user) is refused on every BCS service, on /api/resource read / list / insert of
      `BoQ Row BCS Rate`, and gets NO cost content from the two data services;
  (+) their non-cost content is unchanged for every caller, and a Python caller inside the server (the match path) always
      gets the full content;
  red if the check or a hooks entry is removed (the switch-off proofs flip exactly these).

The users are made-up names with `frappe.get_roles` patched: no User record is created and a refused write never reaches
the database. The one allowed /api/resource insert writes a test row that tearDown deletes.
"""

from types import SimpleNamespace
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.api.boq import rate_master
from nirmaan_stack.api.boq.wizard import bcs
from nirmaan_stack.api.boq.wizard.test_review_screen import _cleanup_project, _make_project
from nirmaan_stack.services.boq_fixture_teardown import fixture_boq_name, purge_boq

ESTIMATES = "bcs3.estimates@example.invalid"
PROCUREMENT = "bcs3.procurement@example.invalid"
PMO = "bcs3.pmo@example.invalid"
ROLES = {
    ESTIMATES: ["Nirmaan Estimates Executive", "All"],
    PROCUREMENT: ["Nirmaan Procurement Executive", "All"],   # FULL rights on the doctype's own rows -- the hook must narrow it
    PMO: ["Nirmaan PMO Executive", "All"],                   # read on the doctype's own rows -- the hook must narrow it
}
DT = "BoQ Row BCS Rate"
SERVICES = ("set_bcs_enabled", "confirm_bcs_columns", "get_sheet_bcs_rates", "save_row_bcs_rates")


def _roles(user=None, *args, username=None, **kwargs):
    return list(ROLES.get(user or username or frappe.session.user, ["All", "Guest"]))


# every name a permission check reads the roles through (frappe.get_roles, frappe.permissions.get_roles and the copy
# frappe.utils.user imported by name)
_ROLE_READERS = ("frappe.get_roles", "frappe.permissions.get_roles", "frappe.utils.user.get_roles")


class _AsUser:
    """Run as a made-up user whose roles are ROLES[user]; restores Administrator."""

    def __init__(self, user, request_path=None):
        self.user, self.path = user, request_path

    def __enter__(self):
        self.p = [mock.patch(name, side_effect=_roles) for name in _ROLE_READERS]
        for x in self.p:
            x.start()
        self.prev_req = getattr(frappe.local, "request", None)
        if self.path:
            frappe.local.request = SimpleNamespace(path=self.path)
        frappe.set_user(self.user)
        return self

    def __exit__(self, *exc):
        frappe.set_user("Administrator")
        frappe.local.request = self.prev_req
        for x in self.p:
            x.stop()
        return False


_FIX = {}


def setUpModule():
    """One fixture BoQ (no sheet): the services' reads and writes need a real BoQ to resolve; purged at the end."""
    project = _make_project()
    boq = frappe.new_doc("BOQs")
    boq.project = project.name
    boq.boq_name = "BCS-3 role check"
    boq.tax_treatment = "Pre-tax"
    boq.insert(set_name=fixture_boq_name("BCS3_ROLE_CHECK"), ignore_permissions=True)
    frappe.db.commit()
    _FIX.update(project=project.name, boq=boq.name)


def tearDownModule():
    frappe.set_user("Administrator")
    purge_boq(_FIX.get("boq"))
    frappe.db.commit()
    if _FIX.get("project"):
        _cleanup_project(_FIX["project"])


def _http(endpoint):
    return "/api/method/nirmaan_stack.api.boq.rate_master." + endpoint


class TestBcsServicesRoleCheck(FrappeTestCase):
    def test_procurement_and_pmo_are_refused_on_every_bcs_service_before_anything_is_read(self):
        for user in (PROCUREMENT, PMO):
            for name in SERVICES:
                with self.subTest(user=user, service=name), _AsUser(user):
                    with self.assertRaises(frappe.PermissionError) as ctx:
                        getattr(bcs, name)()          # no arguments at all: the gate runs FIRST
                    self.assertIn("Admin and Estimates", str(ctx.exception))

    def test_an_estimates_user_passes_the_gate_on_every_service(self):
        with _AsUser(ESTIMATES):
            # read: a pure read of an unknown sheet returns no rows (the gate let it through)
            self.assertEqual(bcs.get_sheet_bcs_rates(boq_name=_FIX["boq"], sheet_name="S", committed_version=1)["rows"], [])
            # switch on / confirm / save: past the gate they fail on the missing sheet, never on permission
            for name, kw in (("set_bcs_enabled", {"enabled": 1}), ("confirm_bcs_columns", {}),
                             ("save_row_bcs_rates", {"excel_row": 5, "supply_rate": 1, "install_rate": 0})):
                with self.subTest(service=name):
                    try:
                        getattr(bcs, name)(boq_name=_FIX["boq"], sheet_name="S", committed_version=1, **kw)
                    except frappe.PermissionError:
                        self.fail(f"{name}: an Estimates user was refused")
                    except Exception:
                        pass  # the missing sheet -- after the gate
                    finally:
                        frappe.db.rollback()

    def test_administrator_passes(self):
        self.assertEqual(bcs.get_sheet_bcs_rates(boq_name=_FIX["boq"], sheet_name="S", committed_version=1)["rows"], [])
        self.assertTrue(bcs.may_see_bcs_cost("Administrator"))


class TestResourceRouteRoleCheck(FrappeTestCase):
    """/api/resource on `BoQ Row BCS Rate` (owner answer 1 "2a"): the two hooks.py entries."""

    def tearDown(self):
        frappe.set_user("Administrator")
        for n in frappe.get_all(DT, filters={"boq": _FIX["boq"]}, pluck="name"):
            frappe.delete_doc(DT, n, force=True, ignore_permissions=True)
        frappe.db.commit()

    def _new(self):
        return frappe.get_doc({"doctype": DT, "boq": _FIX["boq"], "sheet_name": "S", "excel_row": 1, "committed_version": 1,
                               "bcs_version": 1, "is_current": 1, "supply_rate": 1.0, "install_rate": 0.0, "combined_rate": 0.0})

    def test_the_two_hooks_entries_name_the_bcs_functions(self):
        self.assertIn("nirmaan_stack.api.boq.wizard.bcs.has_bcs_rate_permission", frappe.get_hooks("has_permission").get(DT, []))
        self.assertIn("nirmaan_stack.api.boq.wizard.bcs.bcs_rate_query_conditions",
                      frappe.get_hooks("permission_query_conditions").get(DT, []))

    def test_a_no_cost_user_is_refused_read_list_and_insert(self):
        doc = self._new().insert(ignore_permissions=True)
        frappe.db.commit()
        for user in (PROCUREMENT, PMO):
            with self.subTest(user=user), _AsUser(user):
                self.assertFalse(frappe.has_permission(DT, "read", doc=doc.name, user=user))
                self.assertEqual(frappe.get_list(DT, filters={"boq": _FIX["boq"]}, pluck="name"), [])
                with self.assertRaises(frappe.PermissionError):
                    self._new().insert()
        self.assertEqual(len(frappe.get_all(DT, filters={"boq": _FIX["boq"]})), 1, "a refused insert wrote nothing")

    def test_an_allowed_user_reads_lists_and_inserts(self):
        doc = self._new().insert(ignore_permissions=True)
        frappe.db.commit()
        with _AsUser(ESTIMATES):
            self.assertTrue(frappe.has_permission(DT, "read", doc=doc.name, user=ESTIMATES))
            self.assertEqual(frappe.get_list(DT, filters={"boq": _FIX["boq"]}, pluck="name"), [doc.name])
            d2 = self._new()
            d2.excel_row = 2
            d2.insert()
        self.assertEqual(len(frappe.get_all(DT, filters={"boq": _FIX["boq"]})), 2)

    def test_the_hook_functions_answer_by_the_pricing_access_set(self):
        with _AsUser(PROCUREMENT):
            self.assertIs(bcs.has_bcs_rate_permission(user=PROCUREMENT), False)
            self.assertEqual(bcs.bcs_rate_query_conditions(user=PROCUREMENT), "1=0")
        with _AsUser(ESTIMATES):
            self.assertIsNone(bcs.has_bcs_rate_permission(user=ESTIMATES))
            self.assertEqual(bcs.bcs_rate_query_conditions(user=ESTIMATES), "")


class TestDataServicesCostContent(FrappeTestCase):
    """The two services the calculator and the helper read (P5b)."""

    def _cfg(self, user, category, http=True):
        with _AsUser(user, _http("get_rate_category_config") if http else None):
            return rate_master.get_rate_category_config(discipline="Electrical", category_id=category)["config"]

    def _items(self, user, http=True):
        with _AsUser(user, _http("get_rate_master_items") if http else None):
            return rate_master.get_rate_master_items(discipline="Electrical")["items"]

    @staticmethod
    def _pi(items, name):
        return next((i for i in items if i["kind"] == "electrical_pricing_input" and (i.get("attributes") or {}).get("item") == name), None)

    def test_a_no_cost_user_gets_no_cost_pipeline_and_no_cost_key(self):
        full = self._cfg(ESTIMATES, "wiring_cabling")
        self.assertIn("cable_bcs", full["pipelines"])
        self.assertIn("bcs_default_margin", full)
        for user in (PROCUREMENT, PMO):
            with self.subTest(user=user):
                cut = self._cfg(user, "wiring_cabling")
                self.assertFalse([p for p in cut["pipelines"] if "bcs" in p.lower()])
                self.assertNotIn("bcs_default_margin", cut)
                self.assertFalse([pid for g in cut.get("goldens") or [] for pid in (g.get("expect") or {}) if "bcs" in pid.lower()])
                # the non-cost content is unchanged: every price pipeline and every other key, byte for byte
                self.assertEqual({k: v for k, v in cut.items() if k not in ("pipelines", "goldens")},
                                 {k: v for k, v in full.items() if k not in ("pipelines", "goldens", "bcs_default_margin")})
                self.assertEqual(cut["pipelines"], {p: v for p, v in full["pipelines"].items() if "bcs" not in p.lower()})

    def test_a_no_cost_user_gets_no_cost_only_pricing_input_and_keeps_the_rest(self):
        full, cut = self._items(ESTIMATES), self._items(PROCUREMENT)
        self.assertIn("ratio", self._pi(full, "popup_supply")["rates"])
        self.assertNotIn("ratio", self._pi(cut, "popup_supply")["rates"])          # only popup_bcs reads it
        self.assertNotIn("bcs_markup", self._pi(cut, "lms_bcs")["rates"])
        self.assertIsNone(self._pi(cut, "elec_bcs_install_per_sqft"))            # summary_inputs only
        self.assertEqual(self._pi(cut, "misc_supply")["rates"], self._pi(full, "misc_supply")["rates"])  # misc PRICE reads it
        self.assertEqual(self._pi(cut, "swsock")["rates"], self._pi(full, "swsock")["rates"])
        non_pi = lambda xs: [i for i in xs if i["kind"] != "electrical_pricing_input"]
        self.assertEqual(non_pi(cut), non_pi(full), "every catalogue row is unchanged")

    def test_a_python_caller_inside_the_server_keeps_the_full_content(self):
        # the match path calls these functions directly (pricing_step.load_asset); no HTTP endpoint = no filter, whoever runs it
        self.assertIn("cable_bcs", self._cfg(PROCUREMENT, "wiring_cabling", http=False)["pipelines"])
        self.assertIn("ratio", self._pi(self._items(PROCUREMENT, http=False), "popup_supply")["rates"])

    def test_hvac_is_unchanged_for_a_no_cost_user(self):
        for cid in [r for r in frappe.get_all("BoQ Rate Category Config", filters={"discipline": "HVAC", "active": 1}, pluck="category_id")][:5]:
            with _AsUser(ESTIMATES, _http("get_rate_category_config")):
                a = rate_master.get_rate_category_config(discipline="HVAC", category_id=cid)["config"]
            with _AsUser(PROCUREMENT, _http("get_rate_category_config")):
                b = rate_master.get_rate_category_config(discipline="HVAC", category_id=cid)["config"]
            self.assertEqual(a, b, cid)
