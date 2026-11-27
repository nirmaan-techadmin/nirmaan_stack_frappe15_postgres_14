"""SRS-1 T6 - the daily one-year purge of the Suggest run store (owner R-BCS-138; walk-through 27 Nov: DAILY; SRS-D0 D6).

  + a record whose run date is 366 days old is deleted, one 364 days old is kept;
  + deletes go in batches with a nightly ceiling, and say when more are left for the next night;
  + Run Records older than a year that no record points to are deleted (a recent one, or one still pointed to, is kept);
  + Questions no record references are deleted; a referenced one is kept;
  - no other table is touched (the purge's SQL names only the three store tables, and other tables' counts do not move);
  + hooks.py runs it daily at 01:30.

The purge commits after each batch, so the fixtures here are committed; the store purge helper removes them after each
test. The fixture records all carry a `BOQ-TEST-SRS1-` BoQ name.

Run: bench --site localhost run-tests --module nirmaan_stack.services.boq_suggest_store.test_purge
"""

import inspect
import re

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.services.boq_suggest_store import purge
from nirmaan_stack.services.boq_suggest_store.store_test_support import (
    fixture_boq,
    purge_store_fixtures,
    raw_question,
    raw_row,
    raw_run,
)

# The REAL clock, never a far-future date: the purge runs on the live store, so a later "now" would put genuine recent
# records (a real Suggest run's) inside the cut. With today's clock only fixtures dated 366+ days back are in reach.
NOW = frappe.utils.now_datetime()


def _days_ago(n):
    return frappe.utils.add_to_date(NOW, days=-n)


def _exists(dt, name):
    return bool(frappe.db.sql('select 1 from "tab%s" where name = %%s' % dt, (name,)))


class TestPurge(FrappeTestCase):
    def setUp(self):
        self.questions = []

    def tearDown(self):
        purge_store_fixtures(self.questions)

    def test_t6_366_days_deleted_364_kept(self):
        boq = fixture_boq("age")
        old = raw_row(boq, 2, run_date=_days_ago(366))
        young = raw_row(boq, 3, run_date=_days_ago(364))
        out = purge.run_daily(now=NOW)
        self.assertFalse(_exists("BoQ AI Suggest Row Record", old))
        self.assertTrue(_exists("BoQ AI Suggest Row Record", young))
        self.assertGreaterEqual(out["rows"], 1)

    def test_t6_the_cutoff_is_exactly_365_days(self):
        self.assertEqual(purge.KEEP_DAYS, 365)
        fixed = frappe.utils.get_datetime("2027-12-01 01:30:00")
        self.assertEqual(purge.cutoff(fixed), frappe.utils.get_datetime("2026-12-01 01:30:00"))

    def test_t6_batches_with_a_nightly_ceiling(self):
        boq = fixture_boq("batch")
        names = [raw_row(boq, er, run_date=_days_ago(400)) for er in range(2, 7)]   # 5 old rows
        out = purge.run_daily(now=NOW, batch=2, max_batches=2)
        left = [n for n in names if _exists("BoQ AI Suggest Row Record", n)]
        self.assertEqual((out["batches"], out["rows"], out["more_left"], len(left)), (2, 4, True, 1))
        out2 = purge.run_daily(now=NOW, batch=2, max_batches=2)
        self.assertEqual((out2["rows"], out2["more_left"]), (1, False))
        self.assertEqual((purge.BATCH, purge.MAX_BATCHES), (1000, 200))

    def test_t6_orphan_run_records_and_questions_go_the_rest_stay(self):
        boq = fixture_boq("orph")
        old_run = raw_run(boq, started_at=_days_ago(400), finished_at=_days_ago(400))
        recent_run = raw_run(boq, started_at=_days_ago(10))
        pointed_run = raw_run(boq, started_at=_days_ago(400))
        q_free = raw_question("SRS-1 T6 unreferenced question (made up) " + frappe.generate_hash(length=6))
        q_used = raw_question("SRS-1 T6 referenced question (made up) " + frappe.generate_hash(length=6))
        self.questions += [q_free, q_used]
        raw_row(boq, 2, run_date=_days_ago(5), run_record=pointed_run, question=q_used)
        out = purge.run_daily(now=NOW)
        self.assertFalse(_exists("BoQ AI Suggest Run Record", old_run))
        self.assertTrue(_exists("BoQ AI Suggest Run Record", recent_run), "younger than a year")
        self.assertTrue(_exists("BoQ AI Suggest Run Record", pointed_run), "a record still points to it")
        self.assertFalse(_exists("BoQ AI Suggest Question", q_free))
        self.assertTrue(_exists("BoQ AI Suggest Question", q_used))
        self.assertGreaterEqual((out["runs"], out["questions"]), (1, 1))

    def test_t6_no_other_table_is_touched(self):
        src = inspect.getsource(purge)
        tables = set(re.findall(r'"tab([^"]+)"', src))
        self.assertEqual(tables, {"BoQ AI Suggest Row Record", "BoQ AI Suggest Run Record", "BoQ AI Suggest Question"})
        before = {t: frappe.db.count(t) for t in ("BOQs", "BoQ Rate Suggestion Run", "Error Log", "Version")}
        purge.run_daily(now=NOW)
        self.assertEqual({t: frappe.db.count(t) for t in before}, before)

    def test_t6_hooks_run_it_daily_at_0130(self):
        cron = frappe.get_hooks("scheduler_events").get("cron", {})
        self.assertIn("nirmaan_stack.services.boq_suggest_store.purge.run_daily", cron.get("30 1 * * *", []))
