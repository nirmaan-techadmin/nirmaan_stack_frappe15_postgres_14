"""SRS-2 T1 / T2 - the suggested rates for every stored row (services/boq_suggest_store/rates.py) and their trigger in the
Suggest worker (api/boq/rate_master._suggest_worker).

  T1 rates     + a pass's records priced = the server pricing step's OWN figures for the same row records (a fake bundle,
                 and once the REAL bundle on this bench); + "not priced: <reason>" when the helper prices nothing;
                 + "rates not computed: <reason>" when the step cannot run (no bundle / an error / no current sheet), with
                 ONE Error Log and nothing raised; - `bcs_supply_rate` never written; + a re-read row is reset (by the store)
                 and re-priced by its own pass, never overwritten by an older pass's job; + a partly priced row shows only
                 the kinds the pricer priced; - a 0 is never a price.
  T2 trigger   + a pass with rows written queues ONE rates job, after the run's commit and the store's finish; - a pass with
                 0 rows written, or the store off, queues none; + the Suggest run's writes and result are BYTE-IDENTICAL with
                 the rates job on, off and failing.

Fixture rows use a BoQ name outside the BOQs series (store_test_support), purged with the store family's Error Logs.
"""

import copy
import hashlib
import json
import os
import shutil
import tempfile
from types import SimpleNamespace
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.api.boq import rate_master
from nirmaan_stack.services.boq_rate_master import extraction
from nirmaan_stack.services.boq_rate_match import pricing_step
from nirmaan_stack.services.boq_suggest_store import rates, store
from nirmaan_stack.services.boq_suggest_store.store_test_support import fixture_boq, purge_store_fixtures, raw_row, raw_run
from nirmaan_stack.services.boq_suggest_store.test_store import SHEET, CAT, _Client, _Mocks, _answer, _env_mocks

ASSET = ({"configs": {}, "itemsByDiscipline": {}}, "BRMS-TEST:00000000000000aa")
# A FAKE bundle: per row, the outcome the row's attributes ask for (so the plumbing is tested apart from the pricer).
FAKE = """
const c = []; process.stdin.on("data", (d) => c.push(d)); process.stdin.on("end", () => {
  const input = JSON.parse(Buffer.concat(c).toString("utf8"));
  const rows = input.rows.map((r) => {
    const key = `${r.boq}|${r.sheet_name}|${r.excel_row}`;
    const want = (r.attributes || {}).want || "priced";
    let rec;
    if (want === "priced") rec = { kind: "suggestion", mode: "attr", priced: true, scope: ["supply_rate", "install_rate", "combined_rate"],
      values: { supply_rate: r.excel_row * 10, install_rate: r.excel_row, combined_rate: r.excel_row * 11 }, lines: [["p", "uid-" + r.excel_row, "sku", 1]], blanks: [] };
    else if (want === "partial") rec = { kind: "suggestion", mode: "attr", priced: true, scope: ["supply_rate", "combined_rate"],
      values: { supply_rate: 5, install_rate: 0, combined_rate: 9 }, lines: [], blanks: [] };
    else if (want === "error") rec = { kind: "error", mode: "attr", priced: false, scope: [], values: null, lines: [], blanks: ["error"] };
    else rec = { kind: "no_match", mode: "attr", priced: false, scope: [], values: null, reason: null, lines: [], blanks: ["size_mm"] };
    rec.seen = { unit: r.unit, headings: r.headings, cat: r.resolved_category, disc: r.discipline };
    return { key, rec, ac7: { key } };
  });
  process.stdout.write(JSON.stringify({ ok: true, rows }));
});
"""


def _fa(excel_row, want="priced", category=CAT):
    return json.dumps({"excel_row": excel_row, "description": "row %d" % excel_row, "category_id": category,
                       "attributes": {"want": want}})


class _Base(FrappeTestCase):
    def setUp(self):
        self.started = frappe.utils.now_datetime()
        self.dir = tempfile.mkdtemp(prefix="srs2_rates_test_")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)
        purge_store_fixtures(error_logs_since=self.started)

    def _bundle(self, js=FAKE):
        path = os.path.join(self.dir, pricing_step.BUNDLE)
        with open(path, "w", encoding="utf-8") as f:
            f.write(js)
        with open(path, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        with open(os.path.join(self.dir, pricing_step.STAMP), "w", encoding="utf-8") as f:
            json.dump({"code_hash": "code-T", "bundle_sha256": digest}, f)

    def _pass(self, boq, rows, **row_extra):
        """A Run Record and its Row Records ({excel_row: want}). -> (run record name, {excel_row: row name})."""
        rr = raw_run(boq, run_id="rid-t")
        names = {}
        for er, want in rows.items():
            names[er] = raw_row(boq, er, committed_version=1, sheet_name=SHEET, run_record=rr, run_id="rid-t",
                                category_id=CAT, discipline="Electrical", final_attributes=_fa(er, want),
                                supply_rate=0, install_rate=0, combined_rate=0, bcs_supply_rate=0,
                                rates_status=store.RATES_PENDING, **row_extra)
        frappe.db.commit()
        return rr, names

    @staticmethod
    def _inputs(boq, sheet_name, cv, records):
        return ({f"{boq}|{sheet_name}": []},
                {int(r["excel_row"]): {"unit": "Rmt", "headings": ["H1", "H2"], "resolved_category": CAT,
                                       "discipline": "Electrical", "description": None} for r in records}, None)

    def _price(self, rr, **kw):
        with mock.patch.object(rates, "sheet_inputs_for", side_effect=self._inputs), \
                mock.patch.object(pricing_step, "load_asset", return_value=ASSET):
            return rates.price_run_record(rr, build_dir=self.dir, **kw)

    @staticmethod
    def _rows(boq):
        return {r.excel_row: r for r in frappe.db.sql(
            'select * from "tabBoQ AI Suggest Row Record" where boq = %s order by excel_row', (boq,), as_dict=True)}

    def _logs(self, title=rates.ERROR_TITLE):
        return frappe.get_all("Error Log", filters={"method": title, "creation": [">=", self.started]})


class TestRates(_Base):
    def test_t1_priced_rows_carry_the_steps_own_figures_status_detail_and_stamp(self):
        self._bundle()
        boq = fixture_boq("rp")
        rr, _ = self._pass(boq, {3: "priced", 7: "priced"})
        out = self._price(rr)
        self.assertEqual(out["counts"], {rates.PRICED: 2})
        recs = self._rows(boq)
        # the step's own output for the same row records
        _, inputs, _ = self._inputs(boq, SHEET, 1, list(recs.values()))
        step_rows = [rates.step_row(r, inputs) for r in recs.values()]
        own = pricing_step.price_rows({f"{boq}|{SHEET}": []}, step_rows, asset=ASSET, build_dir=self.dir)
        for er, r in recs.items():
            vals = own["rows"][f"{boq}|{SHEET}|{er}"]["rec"]["values"]
            self.assertEqual((r.supply_rate, r.install_rate, r.combined_rate),
                             (vals["supply_rate"], vals["install_rate"], vals["combined_rate"]))
            self.assertEqual(r.rates_status, rates.PRICED)
            self.assertEqual(r.pricing_stamp, "code-T|" + ASSET[1])
            d = json.loads(r.rates_detail) if isinstance(r.rates_detail, str) else r.rates_detail
            self.assertEqual(d["scope"], ["supply_rate", "install_rate", "combined_rate"])
            self.assertEqual(d["lines"], [["p", "uid-%d" % er, "sku", 1]])
            self.assertEqual(d["inputs"], {"committed_version": 1, "unit": "Rmt", "resolved_category": CAT,
                                           "discipline": "Electrical", "headings": 2})
            self.assertEqual(d["job"]["rows"], 2)
        self.assertEqual(self._logs(), [])

    def test_t1_the_step_rows_are_built_from_the_store_and_the_sheet_inputs(self):
        rec = {"boq": "B", "sheet_name": "S", "excel_row": 4, "category_id": "c0", "description": "store text",
               "final_attributes": json.dumps({"excel_row": 4, "description": "run text", "category_id": "c1",
                                               "attributes": {"x": {"value": 1}}, "items": [{"attributes": {}}]})}
        row = rates.step_row(rec, {4: {"unit": "Nos", "headings": ["A"], "resolved_category": "", "discipline": "D"}})
        self.assertEqual(row, {"boq": "B", "sheet_name": "S", "excel_row": 4, "run_id": None, "category_id": "c1",
                               "resolved_category": "", "discipline": "D", "description": "run text", "unit": "Nos",
                               "headings": ["A"], "attributes": {"x": {"value": 1}}, "items": [{"attributes": {}}]})
        # a row the resolver does not know prices with the run's category, as sheet_inputs does
        self.assertEqual(rates.step_row(rec, {})["resolved_category"], "c1")

    def test_t1_not_priced_when_the_helper_prices_nothing(self):
        self._bundle()
        boq = fixture_boq("np")
        rr, _ = self._pass(boq, {5: "none"})
        self._price(rr)
        r = self._rows(boq)[5]
        self.assertEqual(r.rates_status, "not priced: size_mm")
        self.assertEqual((r.supply_rate, r.install_rate, r.combined_rate), (0, 0, 0))
        self.assertEqual(self._logs(), [], "a row the helper cannot price is an outcome, not a failure")

    def test_t1_partly_priced_row_keeps_only_the_kinds_in_scope(self):
        self._bundle()
        boq = fixture_boq("pp")
        rr, _ = self._pass(boq, {6: "partial"})
        self._price(rr)
        r = self._rows(boq)[6]
        d = json.loads(r.rates_detail) if isinstance(r.rates_detail, str) else r.rates_detail
        self.assertEqual((r.rates_status, d["scope"]), (rates.PRICED, ["supply_rate", "combined_rate"]))
        self.assertEqual((r.supply_rate, r.install_rate, r.combined_rate), (5, 0, 9))

    def test_t1_not_computed_when_the_bundle_is_missing_one_error_log_nothing_raised(self):
        boq = fixture_boq("nb")   # no _bundle(): the temp folder is empty
        rr, _ = self._pass(boq, {2: "priced", 3: "priced"})
        out = self._price(rr)
        self.assertEqual(out["counts"], {"rates not computed": 2})
        for r in self._rows(boq).values():
            self.assertTrue(r.rates_status.startswith("rates not computed: pricing step bundle missing"), r.rates_status)
            self.assertEqual((r.supply_rate, r.install_rate, r.combined_rate), (0, 0, 0))
        self.assertEqual(len(self._logs()), 1)

    def test_t1_not_computed_on_an_error_one_error_log_nothing_raised(self):
        self._bundle()
        boq = fixture_boq("er")
        rr, _ = self._pass(boq, {2: "priced", 3: "priced"})
        with mock.patch.object(pricing_step, "price_rows", side_effect=RuntimeError("pricer exploded")):
            out = self._price(rr)
        self.assertIn("RuntimeError: pricer exploded", out["reason"])
        for r in self._rows(boq).values():
            self.assertEqual(r.rates_status, "rates not computed: pricing step error: RuntimeError: pricer exploded")
        self.assertEqual(len(self._logs()), 1)

    def test_t1_a_row_the_pricer_fails_on_is_not_computed(self):
        self._bundle()
        boq = fixture_boq("re")
        rr, _ = self._pass(boq, {4: "error", 5: "priced"})
        self._price(rr)
        recs = self._rows(boq)
        self.assertEqual(recs[4].rates_status, "rates not computed: the pricing step failed on this row")
        self.assertEqual(recs[5].rates_status, rates.PRICED)

    def test_t1_not_computed_when_the_sheet_has_no_current_version(self):
        # the REAL sheet_inputs_for: a fixture BoQ has no BoQ Sheet, so the step is never run
        self._bundle()
        boq = fixture_boq("ns")
        rr, _ = self._pass(boq, {2: "priced"})
        with mock.patch.object(pricing_step, "price_rows") as step:
            rates.price_run_record(rr, build_dir=self.dir)
        step.assert_not_called()
        self.assertEqual(self._rows(boq)[2].rates_status, "rates not computed: the sheet has no current committed version")

    def test_t1_bcs_supply_rate_is_never_written(self):
        self._bundle()
        boq = fixture_boq("bc")
        rr, _ = self._pass(boq, {3: "priced"})
        frappe.db.sql('update "tabBoQ AI Suggest Row Record" set bcs_supply_rate = 7 where boq = %s', (boq,))
        frappe.db.commit()
        self._price(rr)
        self.assertEqual(self._rows(boq)[3].bcs_supply_rate, 7)
        with mock.patch.object(pricing_step, "price_rows", side_effect=RuntimeError("x")):
            self._price(rr)
        self.assertEqual(self._rows(boq)[3].bcs_supply_rate, 7, "the failure path never writes it either")

    def test_t1_a_re_read_row_is_reset_by_the_store_and_re_priced_by_its_own_pass_only(self):
        self._bundle()
        boq = fixture_boq("rr")
        old_rr, names = self._pass(boq, {3: "priced"})
        self._price(old_rr)
        self.assertEqual(self._rows(boq)[3].rates_status, rates.PRICED)
        # the row is read again by a later pass: the store's own upsert resets it to 0 + pending
        p = store.SuggestPass(suggestion_run=None, run_id="rid-new", boq=boq, sheet_name=SHEET, committed_version=1,
                              user="Administrator", kind=store.PASS_SELECTED)
        p.name = raw_run(boq, run_id="rid-new")
        later = frappe.utils.add_to_date(frappe.utils.now_datetime(), seconds=5)
        snapshot = rates._rows_of(old_rr)   # what the OLD pass's job read before the re-read
        p._upsert_row({"boq": boq, "sheet_name": SHEET, "committed_version": 1, "excel_row": 3, "run_record": p.name,
                       "run_id": "rid-new", "run_date": later, "category_id": CAT, "final_attributes": _fa(3, "partial"),
                       "supply_rate": 0, "install_rate": 0, "combined_rate": 0, "bcs_supply_rate": 0,
                       "rates_status": store.RATES_PENDING, "rates_detail": None, "pricing_stamp": None}, later)
        frappe.db.commit()
        r = self._rows(boq)[3]
        self.assertEqual((r.rates_status, r.supply_rate, r.name), (store.RATES_PENDING, 0, names[3]))
        # the old pass's job, late, with what it read before the re-read: it must NOT overwrite the new read
        with mock.patch.object(rates, "_rows_of", return_value=snapshot):
            self._price(old_rr)
        self.assertEqual(self._rows(boq)[3].rates_status, store.RATES_PENDING, "an older read's figures never land")
        # the old pass now owns no row; the new pass's job prices the new read
        self.assertEqual(self._price(old_rr)["rows"], 0)
        self._price(p.name)
        r = self._rows(boq)[3]
        self.assertEqual((r.rates_status, r.supply_rate, r.combined_rate), (rates.PRICED, 5, 9))

    def test_t1_real_bundle_figures_equal_the_step_for_the_same_rows(self):
        """The REAL bundle on this bench (built by the frontend build script) and the live catalogue: the stored
        figures equal price_rows' own for the same row records. Skipped only where no bundle was built."""
        try:
            pricing_step.read_code_stamp()
        except pricing_step.Unavailable as e:
            self.skipTest(str(e))
        boq = fixture_boq("rb")
        rr = raw_run(boq, run_id="rid-real")
        fa = {"excel_row": 43, "description": "Supply and installation of 25 mm PVC conduit", "category_id": "conduit_piping",
              "attributes": {"conduit_type": {"value": "PVC", "confidence": 0.97}, "size_mm": {"value": 25, "confidence": 0.95}}}
        raw_row(boq, 43, committed_version=1, sheet_name=SHEET, run_record=rr, category_id="conduit_piping",
                discipline="Electrical", final_attributes=json.dumps(fa), supply_rate=0, install_rate=0, combined_rate=0,
                bcs_supply_rate=0, rates_status=store.RATES_PENDING)
        frappe.db.commit()

        def inputs(boq_, sheet_, cv, recs):
            return ({f"{boq_}|{sheet_}": []}, {43: {"unit": "Rmt", "headings": ["WIRING SYSTEM", "Conduit provision"],
                                                   "resolved_category": "conduit_piping", "discipline": "Electrical"}}, None)

        with mock.patch.object(rates, "sheet_inputs_for", side_effect=inputs):
            rates.price_run_record(rr)
        r = self._rows(boq)[43]
        own = pricing_step.price_rows({f"{boq}|{SHEET}": []}, [rates.step_row(r, inputs(boq, SHEET, 1, [r])[1])])
        rec = own["rows"][f"{boq}|{SHEET}|43"]["rec"]
        self.assertTrue(own["rows"][f"{boq}|{SHEET}|43"]["priced"], rec)
        self.assertEqual(r.rates_status, rates.PRICED)
        self.assertEqual((r.supply_rate, r.install_rate, r.combined_rate),
                         tuple(float(rec["values"][k]) for k in rates.KINDS))
        self.assertEqual(r.pricing_stamp, rates.stamp_text(own["stamp"]))


class TestRowOutcome(FrappeTestCase):
    """The status rule alone (pure)."""

    def test_nothing_returned_is_not_computed(self):
        self.assertEqual(rates.row_outcome(None)[0], "rates not computed: the pricing step returned nothing for this row")

    def test_priced_without_any_number_is_not_a_price(self):
        st, fig, _ = rates.row_outcome({"priced": True, "rec": {"scope": ["supply_rate"], "values": {}}})
        self.assertTrue(st.startswith("not priced: "))
        self.assertEqual(fig, {})

    def test_a_0_in_scope_is_a_real_figure_only_when_priced(self):
        st, fig, _ = rates.row_outcome({"priced": True, "rec": {"scope": ["supply_rate"], "values": {"supply_rate": 0}}})
        self.assertEqual((st, fig), (rates.PRICED, {"supply_rate": 0.0}))
        st, fig, _ = rates.row_outcome({"priced": False, "rec": {"scope": ["supply_rate"], "values": {"supply_rate": 0}, "reason": "r"}})
        self.assertEqual((st, fig), ("not priced: r", {}))

    def test_a_long_reason_fits_the_column(self):
        st, _, _ = rates.row_outcome({"priced": False, "rec": {"reason": "x " * 400}})
        self.assertLessEqual(len(st), rates.STATUS_MAX)
        self.assertTrue(st.endswith("..."))

    def test_stamp_text(self):
        self.assertEqual(rates.stamp_text({"code": "c", "asset": "a"}), "c|a")
        self.assertIsNone(rates.stamp_text(None))


class TestTrigger(FrappeTestCase):
    def setUp(self):
        self.started = frappe.utils.now_datetime()

    def tearDown(self):
        purge_store_fixtures(error_logs_since=self.started)

    @staticmethod
    def _p(enabled=True, name="RR1", rows_written=2):
        return SimpleNamespace(enabled=enabled, name=name, rows_written=rows_written)

    def test_t2_a_pass_with_rows_written_queues_one_rates_job(self):
        p = self._p()
        with mock.patch("nirmaan_stack.services.background_ops.start") as start:
            op = rates.queue_after_pass(p)
        start.assert_called_once()
        args, kw = start.call_args
        self.assertEqual(args, (rates.OPERATION_KIND, rates.WORKER))
        self.assertEqual((kw["op_id"], kw["run_record"], kw["timeout"]), (op, "RR1", rates.JOB_TIMEOUT_SEC))

    def test_t2_no_job_for_0_rows_written_the_store_off_or_no_run_record(self):
        for p in (self._p(rows_written=0), self._p(enabled=False), self._p(name=None)):
            with mock.patch("nirmaan_stack.services.background_ops.start") as start:
                self.assertIsNone(rates.queue_after_pass(p))
            start.assert_not_called()

    def test_t2_a_failing_queue_call_is_logged_once_and_never_raises(self):
        p = self._p()
        with mock.patch("nirmaan_stack.services.background_ops.start", side_effect=RuntimeError("redis down")):
            self.assertIsNone(rates.queue_after_pass(p))
        logs = frappe.get_all("Error Log", filters={"method": rates.TRIGGER_ERROR_TITLE, "creation": [">=", self.started]})
        self.assertEqual(len(logs), 1)


class TestWorkerByteIdentity(FrappeTestCase):
    """T2 at the worker: the SAME selected-rows pass with the rates job on (queued), off (never queued) and failing (the
    queue call raises) gives byte-identical run-doc writes and operation results; on, the job is queued ONCE, after the
    run's final write and the store's finish. A pass whose scope holds no row of the population writes no row and
    queues nothing."""

    def setUp(self):
        self.started = frappe.utils.now_datetime()

    def tearDown(self):
        purge_store_fixtures(error_logs_since=self.started)

    def _worker(self, boq, mode, scope=frozenset({3})):
        writes, events = [], []

        def _progress(run_name, acc_results, acc_attempted, scope_pending=None):
            writes.append(("progress", rate_master.serialize_run_results(acc_results.values()), sorted(acc_attempted),
                           sorted(scope_pending) if scope_pending is not None else None))

        def _final(run_name, cv, ai_status, merged, acc_attempted, complete, halt_reason, boq, sheet_name, scope_pending=None):
            writes.append(("final", cv, ai_status, rate_master.serialize_run_results(merged), sorted(acc_attempted),
                           complete, halt_reason, sorted(scope_pending) if scope_pending is not None else None))
            events.append("final")

        real_finish = store.SuggestPass.finish

        def _finish(self_, **kw):
            real_finish(self_, **kw)
            events.append("finish")

        def _start(*a, **kw):
            events.append("queued")
            if mode == "failing":
                raise RuntimeError("queue boom")

        carried = [{"excel_row": 2, "description": "row 2 description", "category_id": CAT,
                    "attributes": {"a": {"value": 1, "confidence": 0.5, "corroborated": False}}},
                   {"excel_row": 4, "description": "row 4 description", "category_id": CAT,
                    "attributes": {"a": {"value": 3, "confidence": 0.5, "corroborated": False}}}]
        real = extraction.run_extraction

        def _with_client(b, s, **kw):
            return real(b, s, client=_Client(_answer()), **kw)

        patches = _env_mocks([2, 3, 4]) + [
            mock.patch.object(extraction, "run_extraction", side_effect=_with_client),
            mock.patch.object(rate_master, "_resolve_committed_version", return_value=4),
            mock.patch.object(rate_master, "_open_run_doc", return_value=("N", "RID", copy.deepcopy(carried), [2, 3, 4], set(scope))),
            mock.patch.object(rate_master, "_write_run_progress", side_effect=_progress),
            mock.patch.object(rate_master, "_finalise_run", side_effect=_final),
            mock.patch.object(rate_master, "_start_match_after_suggest", return_value=None),
            mock.patch.object(rate_master.background_ops, "set_row_progress"),
            mock.patch.object(rate_master.operation_marker, "release_own"),
            mock.patch.object(store, "store_enabled", return_value=True),
            mock.patch.object(store.SuggestPass, "finish", _finish),
            mock.patch("nirmaan_stack.services.background_ops.start", side_effect=_start),
        ]
        if mode == "off":
            patches.append(mock.patch.object(rates, "queue_after_pass", return_value=None))
        with _Mocks(patches):
            payload = rate_master._suggest_worker(boq=boq, sheet_name=SHEET, only_rows=sorted(scope))
        return json.dumps(writes), json.dumps(payload, sort_keys=True, default=str), events

    def test_t2_rates_job_on_off_and_failing_give_byte_identical_run_writes(self):
        boq = fixture_boq("rw")
        on = self._worker(boq, "on")
        self.assertEqual(on[2], ["final", "finish", "queued"], "ONE job, after the run's final write and the store's finish")
        off = self._worker(boq, "off")
        self.assertEqual(off[2], ["final", "finish"])
        failing = self._worker(boq, "failing")
        self.assertEqual(failing[2], ["final", "finish", "queued"])
        self.assertEqual(on[:2], off[:2], "the rates job changes nothing the run writes or returns")
        self.assertEqual(on[:2], failing[:2], "a failing rates trigger changes nothing the run writes or returns")
        logs = frappe.get_all("Error Log", filters={"method": rates.TRIGGER_ERROR_TITLE, "creation": [">=", self.started]})
        self.assertEqual(len(logs), 1)

    def test_t2_a_pass_that_reads_no_row_queues_nothing(self):
        boq = fixture_boq("rz")
        _, _, events = self._worker(boq, "on", scope=frozenset({9}))   # row 9 is not in the population: nothing read
        self.assertEqual(events, ["final", "finish"])
        # the pass ends partial, so the worker writes its own halt log; the family purge removes it (fixture BoQ only)
        halt = {"method": "BoQ suggest run halted (partial saved)", "creation": [">=", self.started],
                "error": ["like", "boq=%s%%" % boq]}
        self.assertEqual(len(frappe.get_all("Error Log", filters=halt)), 1)
        purge_store_fixtures(error_logs_since=self.started)
        self.assertEqual(frappe.get_all("Error Log", filters=halt), [], "no live Error Log row is left behind")
