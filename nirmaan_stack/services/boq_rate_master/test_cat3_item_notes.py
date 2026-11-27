"""CAT-3 (2026-11-27) -- ITEM NOTES (owner 2026-11-26 00:18, R5) and THE "WHAT STOPS WORKING" LIST (00:10, R6). Every check has a
NEGATIVE. Writes happen ONLY on a scratch row inside this test's own transaction (commit is stubbed, every test rolls back): no live
row is edited, deactivated or noted.

  T4+ Admin saves a note on a row (audited Version row; no supersede: same name, still active); the note is served by
      get_rate_master_items; the loader (both insert sites), the exporter and the CSV round trip carry it.
  T4- Estimates / PMO / HR (HR holding System Manager) get PermissionError on the note edit and on the usage list; the gate
      runs before any read.
  T4+ A note edit moves NEITHER stamp (CAT-1's catalogue stamp; the pricing step's served-catalogue version) nor any price.
  T5+ The CAT-D1 E6 examples on the live catalogue: the Automatic Air Vent and the DDC panel list what stops; a Dual Plate NRV
      lists nothing (others carry its values); an EDIT that renames the last carrier lists what stops; the CSV preview list.
  T5- An edit that keeps every value lists nothing; a value another row carries is "still works", never "will stop".
Run: bench --site localhost run-tests --module nirmaan_stack.services.boq_rate_master.test_cat3_item_notes
"""
import contextlib
import json
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_rate_master import catalogue_lists, exporter, item_usage

ITEM = "BoQ Rate Master Item"


@contextlib.contextmanager
def _as_profile(email, profile, extra_roles=()):
    """Run as `email` whose `Nirmaan Users.role_profile` reads as `profile` (no fixture row; the REAL admin gate runs). The
    `extra_roles` are answered for frappe.get_roles (HR holding System Manager)."""
    real = frappe.local.db.get_value

    def _get_value(doctype, filters=None, fieldname="name", *args, **kwargs):
        if doctype == "Nirmaan Users" and filters == email and fieldname == "role_profile":
            return profile
        return real(doctype, filters, fieldname, *args, **kwargs)

    original = frappe.session.user
    with mock.patch.object(frappe.local.db, "get_value", new=_get_value), \
            mock.patch("frappe.get_roles", return_value=list(extra_roles) + ["All", "Guest"]):
        frappe.set_user(email)
        try:
            yield
        finally:
            frappe.set_user(original)


class _Scratch(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        self._commit = mock.patch.object(frappe.db, "commit", new=lambda *a, **k: None)
        self._commit.start()

    def tearDown(self):
        self._commit.stop()
        frappe.db.rollback()
        super().tearDown()

    def scratch_row(self, **attrs):
        live = frappe.get_all(ITEM, filters={"discipline": "HVAC", "active": 1, "kind": "hvac_valve_item"},
                              fields=["kind", "brand", "unit", "attributes", "rates"], limit=1)[0]
        doc = frappe.get_doc({"doctype": ITEM, "discipline": "HVAC", "kind": live["kind"], "brand": live["brand"],
                              "unit": live["unit"], "item_uid": "rmi-cat3scratch1",
                              "attributes": json.dumps(dict(json.loads(live["attributes"]) if isinstance(live["attributes"], str)
                                                            else live["attributes"], **attrs)),
                              "rates": live["rates"] if isinstance(live["rates"], str) else json.dumps(live["rates"]),
                              "source_sheet": "cat3-scratch", "source_row": 1, "import_batch": "cat3-scratch", "active": 1})
        doc.insert(ignore_permissions=True)
        return doc


class TestNoteEdit(_Scratch):
    def test_admin_saves_a_note_in_place_audited(self):
        from nirmaan_stack.api.boq import rate_master
        doc = self.scratch_row()
        before_versions = frappe.db.count("Version", {"ref_doctype": ITEM, "docname": doc.name})
        out = rate_master.save_rate_master_item_note(name=doc.name, item_notes="sold per piece")
        self.assertEqual(out, {"ok": True, "name": doc.name, "item_notes": "sold per piece"})
        row = frappe.db.get_value(ITEM, doc.name, ["item_notes", "active"], as_dict=True)
        self.assertEqual((row.item_notes, row.active), ("sold per piece", 1))     # in place: same row, still active
        self.assertEqual(frappe.db.count("Version", {"ref_doctype": ITEM, "docname": doc.name}), before_versions + 1)
        served = [i for i in rate_master.get_rate_master_items(discipline="HVAC")["items"] if i["name"] == doc.name]
        self.assertEqual(served[0]["item_notes"], "sold per piece")

    def test_non_admins_are_refused_before_any_read(self):
        from nirmaan_stack.api.boq import rate_master
        doc = self.scratch_row()
        for email, profile, roles in (("cat3-est@example.com", "Nirmaan Estimates Executive Profile", ()),
                                      ("cat3-pmo@example.com", "Nirmaan PMO Executive Profile", ()),
                                      ("cat3-hr@example.com", "Nirmaan HR Executive Profile", ("System Manager",))):
            with self.subTest(profile=profile), _as_profile(email, profile, roles):
                with self.assertRaises(frappe.PermissionError):
                    rate_master.save_rate_master_item_note(name=doc.name, item_notes="x")
                with self.assertRaises(frappe.PermissionError):
                    rate_master.rate_master_item_usage(name=doc.name)
                with self.assertRaises(frappe.PermissionError):   # the gate runs BEFORE resolution: a missing row still refuses
                    rate_master.save_rate_master_item_note(name="no-such-row", item_notes="x")
        self.assertIsNone(frappe.db.get_value(ITEM, doc.name, "item_notes"))

    def test_a_note_edit_moves_no_stamp_and_no_price(self):
        from nirmaan_stack.api.boq import rate_master
        from nirmaan_stack.services.boq_rate_match import pricing_step
        doc = self.scratch_row()
        items, configs = catalogue_lists._read("HVAC")
        stamp_before = catalogue_lists.compute_stamp(items, configs)
        _payload, ver_before = pricing_step.load_asset()
        rates_before = frappe.db.get_value(ITEM, doc.name, "rates")
        rate_master.save_rate_master_item_note(name=doc.name, item_notes="a fact about this row")
        items, configs = catalogue_lists._read("HVAC")
        self.assertEqual(catalogue_lists.compute_stamp(items, configs), stamp_before)
        _payload, ver_after = pricing_step.load_asset()
        self.assertEqual(ver_after, ver_before)
        self.assertEqual(frappe.db.get_value(ITEM, doc.name, "rates"), rates_before)
        # NEGATIVE (the check can see a move): an attribute edit DOES move the catalogue stamp
        frappe.db.set_value(ITEM, doc.name, "attributes", json.dumps({"item_name": "cat3 scratch moved"}),
                            update_modified=False)   # raw write on a scratch row inside this rolled-back test; no recompute needed
        items, configs = catalogue_lists._read("HVAC")
        self.assertNotEqual(catalogue_lists.compute_stamp(items, configs), stamp_before)

    def test_the_exporter_and_loader_carry_the_note(self):
        row = {"kind": "k", "brand": None, "unit": "Nos", "attributes": "{}", "rates": "{}", "source_sheet": "s", "source_row": 1,
               "item_uid": "rmi-x", "item_notes": "a fact"}
        self.assertEqual(exporter._item_payload(row)["item_notes"], "a fact")
        self.assertNotIn("item_notes", exporter._item_payload(dict(row, item_notes=None)))   # an empty note is not emitted


class TestUsage(FrappeTestCase):
    """T5: the usage list on the live catalogue (read-only)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.items, cls.configs = item_usage.read_discipline("HVAC")

    def _row(self, attr, value, kind=None):
        rows = [i for i in self.items if i["attributes"].get(attr) == value and (kind is None or i["kind"] == kind)]
        self.assertTrue(rows, (attr, value))
        return rows[0]

    def _carriers(self, attr, value):
        return [i for i in self.items if i["attributes"].get(attr) == value]

    def test_the_only_automatic_air_vent_lists_what_stops(self):
        vent = next(i for i in self.items if "air vent" in str(i["attributes"].get("item_name", "")).lower())
        self.assertEqual(len(self._carriers("item_name", vent["attributes"]["item_name"])), 1)
        u = item_usage.usage(self.configs, self.items, vent, None, "HVAC")
        self.assertEqual(u["action"], "deactivate")
        self.assertTrue(u["will_stop"])
        self.assertIn(["item_name", vent["attributes"]["item_name"]], u["last_carrier_of"])
        self.assertTrue(all(s["config"] and s["path"] and s["message"] for s in u["will_stop"]))

    def test_a_row_whose_values_others_carry_lists_nothing(self):
        # a Valve Package row whose every value another active row also carries
        for r in self.items:
            if r["kind"] != "hvac_valve_item":
                continue
            u = item_usage.usage(self.configs, self.items, r, None, "HVAC")
            if not u["last_carrier_of"]:
                self.assertEqual(u["will_stop"], [])
                self.assertGreaterEqual(u["still_works"], 0)
                return
        self.fail("no Valve Package row shares all its values")

    def test_an_edit_renaming_the_last_carrier_lists_what_stops_and_keeping_values_lists_nothing(self):
        vent = next(i for i in self.items if "air vent" in str(i["attributes"].get("item_name", "")).lower())
        renamed = item_usage.usage(self.configs, self.items, vent, {"item_name": vent["attributes"]["item_name"] + " (renamed)"}, "HVAC")
        self.assertEqual(renamed["action"], "edit")
        self.assertTrue(renamed["will_stop"])
        same = item_usage.usage(self.configs, self.items, vent, {"item_name": vent["attributes"]["item_name"]}, "HVAC")
        self.assertEqual(same["will_stop"], [])

    def test_the_csv_preview_list_names_the_lost_value(self):
        vent = next(i for i in self.items if "air vent" in str(i["attributes"].get("item_name", "")).lower())
        after = [i for i in self.items if i is not vent] + [dict(vent, attributes=dict(vent["attributes"], item_name="cat3 renamed"))]
        out = item_usage.values_no_row_will_carry(self.configs, self.items, after, "HVAC")
        self.assertIn(["item_name", vent["attributes"]["item_name"]], out["values"])
        self.assertTrue(out["will_stop"])
        self.assertEqual(item_usage.values_no_row_will_carry(self.configs, self.items, list(self.items), "HVAC"),
                         {"values": [], "will_stop": []})

    def test_the_endpoint_answers_admin_with_timing(self):
        from nirmaan_stack.api.boq import rate_master
        vent = next(i for i in self.items if "air vent" in str(i["attributes"].get("item_name", "")).lower())
        frappe.set_user("Administrator")
        out = rate_master.rate_master_item_usage(name=vent["name"])
        self.assertTrue(out["will_stop"])
        self.assertIsInstance(out["ms"], float)
        out2 = rate_master.rate_master_item_usage(name=vent["name"], proposed_values=json.dumps({"item_name": "cat3 renamed"}))
        self.assertEqual(out2["action"], "edit")


class TestNotePlaceholder(FrappeTestCase):
    """QR-NOTE (a): `{{note:<item_uid>}}` is filled from the item's own note by the ONE served fill; the gate refuses a reference to
    no active item or to an empty note."""

    def _built(self, note):
        items = [{"item_uid": "rmi-n1", "kind": "k", "attributes": {"item_name": "Thing"}, "item_notes": note, "active": 1}]
        return catalogue_lists.build(items, [])

    def test_the_fill_gives_the_note_words(self):
        built = self._built("one price for any size")
        problems = []
        self.assertEqual(catalogue_lists.fill_text("BoQ says x - {{note:rmi-n1}}", built, problems), "BoQ says x - one price for any size")
        self.assertEqual(problems, [])
        self.assertEqual(catalogue_lists.fill_text("{{note:rmi-n1|lower}}", self._built("ONE Price"), []), "one price")

    def test_an_empty_note_or_a_missing_item_is_a_problem(self):
        problems = []
        catalogue_lists.fill_text("{{note:rmi-n1}}", self._built(""), problems)
        self.assertIn("note", problems[0][1])
        problems = []
        catalogue_lists.fill_text("{{note:rmi-nope}}", self._built("x"), problems)
        self.assertIn("no active SKU", problems[0][1])
        self.assertIsNone(catalogue_lists.parse_placeholder("note", "rmi-n1:item_name"))   # a note takes no attribute

    def test_the_note_hash_moves_with_a_note_but_the_stamp_does_not(self):
        a = [{"item_uid": "rmi-n1", "kind": "k", "attributes": {"x": 1}, "item_notes": "a", "active": 1}]
        b = [dict(a[0], item_notes="b")]
        self.assertEqual(catalogue_lists.compute_stamp(a, []), catalogue_lists.compute_stamp(b, []))
        self.assertNotEqual(catalogue_lists.notes_sha(a), catalogue_lists.notes_sha(b))

    def test_the_pricing_step_version_leaves_the_note_out(self):
        from nirmaan_stack.services.boq_rate_match import pricing_step
        p1 = {"configs": {"c": {"list_spec": {"pricing": {"text_notes": [{"line": "one price"}]}}}},
              "itemsByDiscipline": {"HVAC": [{"item_uid": "rmi-n1", "item_notes": "one price", "rates": {"s": 1}}]}}
        p2 = json.loads(json.dumps(p1).replace("one price", "two prices"))
        self.assertEqual(pricing_step._version_canon(p1), pricing_step._version_canon(p2))
        p3 = json.loads(json.dumps(p1).replace('"s": 1', '"s": 2'))   # NEGATIVE: a rate move still moves the version
        self.assertNotEqual(pricing_step._version_canon(p1), pricing_step._version_canon(p3))


class TestCsvRoundTrip(_Scratch):
    """T4: the CSV round trip carries the note -- the column appears only in a file where a row carries one (a file with no notes is
    byte-identical), the importer reads it as a change of that row, and an absent column keeps every stored note."""

    def test_the_note_column_round_trips(self):
        from nirmaan_stack.services.boq_rate_master import csv_exporter, csv_importer
        before, _h, _n = csv_exporter.build_category_csv("HVAC", "hvac_valve_package")
        self.assertNotIn("item_notes", before.splitlines()[0])            # no row carries a note today: no column
        doc = self.scratch_row()
        frappe.db.set_value(ITEM, doc.name, "item_notes", "sold in pairs", update_modified=False)   # scratch row, rolled back
        text, headers, _n = csv_exporter.build_category_csv("HVAC", "hvac_valve_package")
        self.assertEqual(headers[-1], "item_notes")
        self.assertIn("sold in pairs", text)
        plan = csv_importer.build_plan("HVAC", text, category_id="hvac_valve_package")
        self.assertEqual([c for c in plan["changes"]], [])                 # unchanged file: zero changes
        edited = text.replace("sold in pairs", "sold singly")
        plan = csv_importer.build_plan("HVAC", edited, category_id="hvac_valve_package")
        ch = [c for c in plan["changes"] if c.get("item_uid") == "rmi-cat3scratch1"]
        self.assertEqual(len(ch), 1)
        self.assertEqual(ch[0]["_payload"]["item_notes"], "sold singly")
        self.assertIn("item_notes", [f["column"] for f in ch[0]["fields"]])
        # a file WITHOUT the column keeps the stored note (absent = unchanged)
        self.assertEqual(csv_importer.build_plan("HVAC", before, category_id="hvac_valve_package")["changes"], [])

    def test_the_preview_lists_values_no_row_will_carry(self):
        from nirmaan_stack.api.boq import rate_master
        from nirmaan_stack.services.boq_rate_master import csv_exporter
        text, headers, _n = csv_exporter.build_category_csv("HVAC", "hvac_valve_package")
        vent = next(i for i in item_usage.read_discipline("HVAC")[0] if "air vent" in str(i["attributes"].get("item_name", "")).lower())
        name = vent["attributes"]["item_name"]
        out = rate_master.preview_rate_master_csv(discipline="HVAC", csv_text=text.replace(name, name + " X"), category_id="hvac_valve_package")
        self.assertIn(["item_name", name], out["values_no_row_will_carry"]["values"])
        self.assertTrue(out["values_no_row_will_carry"]["will_stop"])
        same = rate_master.preview_rate_master_csv(discipline="HVAC", csv_text=text, category_id="hvac_valve_package")
        self.assertEqual(same["values_no_row_will_carry"], {"values": [], "will_stop": []})


class TestLoaderGateCarriesNotes(FrappeTestCase):
    """K3b (QR-LOAD-V92 (a), ANSWER 5): the gate the LOADER runs (`config_validation.validate_catalogue_references`, both loader paths)
    resolves a `{{note:<item_uid>}}` against the row's note in the payload -- the route the product uses, not only the gate directly.
    Read-only: it validates an in-memory payload built from today's export."""

    def _payload(self, note):
        a = exporter.build_asset("HVAC")
        vent = next(i for i in a["items"] if "air vent" in str(i["attributes"].get("item_name", "")).lower())
        if note is not None:
            vent["item_notes"] = note
        else:
            vent.pop("item_notes", None)
        cfg = next(c for c in a["category_configs"] if c["category_id"] == "hvac_valve_package")
        cfg["list_spec"]["pricing"]["text_notes"][0]["line"] = "{{note:%s}}" % vent["item_uid"]
        configs = [dict(c, discipline="HVAC") for c in a["category_configs"]]
        return configs, a["items"]

    def test_a_carried_note_passes_the_loader_gate(self):
        from nirmaan_stack.services.boq_rate_master import config_validation
        configs, items = self._payload("one price for any size")
        config_validation.validate_catalogue_references(configs, items, "HVAC")   # no refusal

    def test_an_empty_or_missing_note_is_refused_by_the_loader_gate(self):
        from nirmaan_stack.services.boq_rate_master import config_validation
        for note in ("", None):
            with self.subTest(note=note):
                configs, items = self._payload(note)
                with self.assertRaises(frappe.ValidationError) as cm:
                    config_validation.validate_catalogue_references(configs, items, "HVAC")
                self.assertIn("note", str(cm.exception))
