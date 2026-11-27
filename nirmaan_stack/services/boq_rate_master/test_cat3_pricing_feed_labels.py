"""CAT-3 (ANSWER 8, QR-REPLAY-LABELS (a) condition 2, 2026-11-28) -- THE PRICING-FEED LABEL GUARD.

PF2's tracked replay fed the pricing code RAW item rows and 49 stored rows lost their figures (a cloth cladding no longer resolved):
every label group (cloth claddings, cable kinds, poles) needs the `labels` the served read attaches. Every product path that prices
reads its items through ONE feed, `api/boq/rate_master.get_rate_master_items` (its last step `_serve_items` attaches them):
  - the BoQ pricing panel and the Calculator (`rateHelperPlumbing.useRateMasterItems`), the rules page (`RateMasterDerivation`),
    Rate Master (`RateMasterPage`) -- the browser;
  - the server pricing step (`boq_rate_match/pricing_step.load_asset`), which runs the same bundle on the worker.
The Python readers that use a label group label from the row's own attributes (`catalogue_labels.label_of_value`), and the extraction
list readers read attributes only, so neither is handed a label.

ONE guard: (1) every item the feed serves, for both disciplines, carries exactly the rule's labels; (2) so does every item the server
pricing step loads; (3) the browser has no other item feed -- the files that call the feed are exactly the three above, and no page
reads the doctype directly. Vacuity: `_serve_items` returning the rows unlabelled turns (1) and (2) RED; a new raw feed turns (3) RED.
Read-only.
Run: bench --site localhost run-tests --module nirmaan_stack.services.boq_rate_master.test_cat3_pricing_feed_labels
"""
import os
import re

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.api.boq import rate_master
from nirmaan_stack.services.boq_rate_master import catalogue_labels as CL
from nirmaan_stack.services.boq_rate_match import pricing_step

APP = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(CL.__file__)), "..", "..", ".."))
SRC = os.path.join(APP, "frontend", "src")
FEED_CALL = '"nirmaan_stack.api.boq.rate_master.get_rate_master_items"'
FEED_FILES = {
    "pages/boq-wizard/rate-helper/rateHelperPlumbing.tsx",
    "pages/pricing/rate-master/RateMasterDerivation.tsx",
    "pages/pricing/rate-master/RateMasterPage.tsx",
}
NOT_PRODUCT = re.compile(r"(\.test\.|\.harness\.|__fixtures__|/types/doctypes/)")


def _unlabelled(items):
    """Each item whose `labels` are missing or differ from the rule's labels for its own kind and attributes."""
    out = []
    for it in items:
        want = CL.labels_for(it.get("kind"), it.get("attributes") or {})[0]
        if "labels" not in it or it["labels"] != want:
            out.append(it.get("item_uid") or it.get("name"))
    return out


class TestPricingFeedsCarryLabels(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")

    def test_every_pricing_reader_is_handed_labelled_items(self):
        # (1) the one feed, both disciplines
        served = {}
        for d in ("HVAC", "Electrical"):
            items = rate_master.get_rate_master_items(discipline=d)["items"]
            self.assertTrue(items, d)
            self.assertEqual(_unlabelled(items), [], f"{d}: items served without the rule's labels")
            served[d] = items
        # not vacuous: the label groups the pricing code reads are present on the live catalogue
        carried = {k for d in served for it in served[d] for k in (it.get("labels") or {})}
        self.assertTrue({"cloth_cladding", "conductor", "armour", "poles"} <= carried, carried)
        # (2) the server pricing step loads exactly that feed
        payload, _version = pricing_step.load_asset()
        for d, items in payload["itemsByDiscipline"].items():
            self.assertEqual(_unlabelled(items), [], f"pricing step {d}: items without the rule's labels")
        self.assertEqual(sorted(payload["itemsByDiscipline"]), sorted(served))
        # (3) the browser has no other item feed
        callers, raw = set(), set()
        for root, _dirs, files in os.walk(SRC):
            for f in files:
                if not f.endswith((".ts", ".tsx")):
                    continue
                p = os.path.join(root, f)
                rel = os.path.relpath(p, SRC).replace(os.sep, "/")
                if NOT_PRODUCT.search("/" + rel):
                    continue
                text = open(p, encoding="utf-8").read()
                if FEED_CALL in text:
                    callers.add(rel)
                if re.search(r'useFrappeGetDocList\s*(<[^>]*>)?\s*\(\s*"BoQ Rate Master Item"', text) or \
                        re.search(r'getDocList\s*\(\s*"BoQ Rate Master Item"', text):
                    raw.add(rel)
        self.assertEqual(callers, FEED_FILES, "a new browser item feed must read get_rate_master_items' served items")
        self.assertEqual(raw, set(), "a page reads Rate Master items raw (no labels)")
