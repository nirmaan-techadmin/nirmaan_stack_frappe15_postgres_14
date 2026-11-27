"""SRS-1 T2 - the Suggest run store is Admin only (owner R-BCS-139 "2 only admins"; walk-through 27 Nov: Admin =
Administrator or the Admin profile; Estimates users' runs ARE stored but they cannot read them; SRS-D0 D7).

System Manager - the role the three doctypes' DocPerm rows name - is also bundled in the Estimates, PMO and HR profiles, so
the hooks (`permissions.py`, wired in hooks.py) are what keeps those users out. Every test person below HOLDS System Manager.

  + Administrator and an Admin-profile user read all three doctypes through frappe.client get_list / get / get_count and
    the report view's query (`frappe.desk.reportview.execute`);
  - an Estimates, a PMO and an HR user get an empty list, a count of 0 and a PermissionError on get, through each route;
  - Guest is never a reader.

Nothing here commits: the fixture rows and people roll back with the class; the purge helpers run after as the safety net.

Run: bench --site localhost run-tests --module nirmaan_stack.services.boq_suggest_store.test_permissions
"""

import frappe
import frappe.client
from frappe.desk import reportview
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.nirmaan_stack.doctype.asset_management.test_asset_management import _make_person
from nirmaan_stack.services.boq_suggest_store import permissions
from nirmaan_stack.services.boq_suggest_store.store_test_support import (
    fixture_boq,
    purge_store_fixtures,
    raw_question,
    raw_row,
    raw_run,
)

QUESTION_TEXT = "SRS-1 T2 permission fixture question (made up)"


class TestStoreAdminOnly(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        frappe.set_user("Administrator")
        cls.people = {}
        for tag, profile in (("admin", "Nirmaan Admin Profile"), ("est", "Nirmaan Estimates Executive Profile"),
                             ("pmo", "Nirmaan PMO Executive Profile"), ("hr", "Nirmaan HR Executive Profile")):
            email = _make_person("srs1-" + tag, profile)
            frappe.get_doc({"doctype": "Has Role", "name": frappe.generate_hash(length=10), "parent": email,
                            "parenttype": "User", "parentfield": "roles", "role": "System Manager"}).db_insert()
            frappe.clear_cache(user=email)
            cls.people[tag] = email
        cls.boq = fixture_boq("perm")
        cls.question = raw_question(QUESTION_TEXT)
        cls.run_record = raw_run(cls.boq)   # NOT `cls.run`: that would shadow TestCase.run
        cls.row = raw_row(cls.boq, 12, run_record=cls.run_record, question=cls.question)
        cls.names = {"BoQ AI Suggest Row Record": cls.row, "BoQ AI Suggest Run Record": cls.run_record,
                     "BoQ AI Suggest Question": cls.question}

    @classmethod
    def tearDownClass(cls):
        frappe.set_user("Administrator")
        frappe.db.rollback()
        people = list(cls.people.values())
        for dt, filters in (("Has Role", {"parent": ["in", people], "parenttype": "User"}),
                            ("Nirmaan Users", {"name": ["in", people]}), ("User", {"name": ["in", people]})):
            try:
                frappe.db.delete(dt, filters)
                frappe.db.commit()
            except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
                frappe.db.rollback()
                print("WARNING -- test_permissions people purge INCOMPLETE: %s: %s" % (dt, exc))
        purge_store_fixtures([cls.question])
        super().tearDownClass()

    def tearDown(self):
        frappe.set_user("Administrator")

    def _reads(self, user, dt):
        frappe.set_user(user)
        listed = [r["name"] for r in frappe.client.get_list(dt, fields=["name"], limit_page_length=0)]
        count = frappe.client.get_count(dt)
        report = [r[0] if isinstance(r, (list, tuple)) else r["name"]
                  for r in reportview.execute(dt, fields=["name"], limit_page_length=0)]
        return listed, count, report

    def test_t2_administrator_and_the_admin_profile_read_every_route(self):
        for user in ("Administrator", self.people["admin"]):
            for dt, name in self.names.items():
                listed, count, report = self._reads(user, dt)
                self.assertIn(name, listed, (user, dt))
                self.assertIn(name, report, (user, dt))
                self.assertGreaterEqual(count, 1, (user, dt))
                got = frappe.client.get(dt, name)
                self.assertEqual(got["name"], name, (user, dt))

    def test_t2_estimates_pmo_and_hr_holding_system_manager_get_nothing(self):
        for tag in ("est", "pmo", "hr"):
            user = self.people[tag]
            self.assertIn("System Manager", frappe.get_roles(user), user)
            for dt, name in self.names.items():
                listed, count, report = self._reads(user, dt)
                self.assertEqual((listed, count, report), ([], 0, []), (tag, dt))
                with self.assertRaises(frappe.PermissionError, msg=(tag, dt)):
                    frappe.client.get(dt, name)
                self.assertFalse(frappe.has_permission(dt, "read", doc=name, user=user), (tag, dt))

    def test_t2_the_hooks_are_wired_for_all_three_doctypes(self):
        hp = frappe.get_hooks("has_permission")
        pq = frappe.get_hooks("permission_query_conditions")
        for dt in permissions.STORE_DOCTYPES:
            self.assertEqual(hp.get(dt), ["nirmaan_stack.services.boq_suggest_store.permissions.has_permission"], dt)
            self.assertEqual(pq.get(dt), ["nirmaan_stack.services.boq_suggest_store.permissions.get_permission_query_conditions"], dt)

    def test_t2_the_rule_itself(self):
        self.assertTrue(permissions.is_store_reader("Administrator"))
        self.assertTrue(permissions.is_store_reader(self.people["admin"]))
        for tag in ("est", "pmo", "hr"):
            self.assertFalse(permissions.is_store_reader(self.people[tag]), tag)
        self.assertFalse(permissions.is_store_reader("Guest"))
        self.assertEqual(permissions.get_permission_query_conditions(self.people["est"]), "1=0")
        self.assertEqual(permissions.get_permission_query_conditions(self.people["admin"]), "")
