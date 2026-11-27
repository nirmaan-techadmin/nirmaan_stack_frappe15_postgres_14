"""SRS-1 T3 / T4 / T5 - the Suggest run store's write (owner R-BCS-138 / 139, R4 QR-C1 / QR-C2, R6; SRS-D0 D1 / D2 / D9).

They drive the REAL `extraction.run_extraction` (and, for T4, the REAL `rate_master._suggest_worker`) with a fake model
client and a mocked population (the pattern of test_rate_master's `_extraction_env_mocks`), so the real `_extract_batch`,
its capture and its observation run. No model call is made.

T3 + one record per attempted row, its input / reply BYTE-EQUAL to the capture line's per-row parts, its final values the
     run's own result row (the checkpoint's), the question its request minus the ROWS block;
   + a second run of the same row OVERWRITES its record (same name, the new read);
   - a selected-rows pass writes only the rows it read: an older record of another row keeps its date and content;
   - a row the reply omitted keeps its input with "no reply element";
   + one Question for two batches with the same text;
   + the upsert names the doctype's UNIQUE constraint.
T4 the store failing changes NOTHING about the run: the run doc's writes (checkpoints and the final write) and the
   operation's result are BYTE-IDENTICAL to a run with no store, and ONE Error Log is written; carried rows get no record.
T5 without `store_cb` (every other caller) the capture lines, the checkpoints and the envelope are identical, and no
   observation is collected.
ON + outside `bench run-tests` the store is ON and writes (ANSWER 2: the switch can never silently disable production).

Run: bench --site localhost run-tests --module nirmaan_stack.services.boq_suggest_store.test_store
"""

import copy
import json
from types import SimpleNamespace
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from nirmaan_stack.api.boq import rate_master
from nirmaan_stack.nirmaan_stack.doctype.boq_ai_suggest_row_record import boq_ai_suggest_row_record as row_doctype
from nirmaan_stack.services.boq_rate_master import extraction
from nirmaan_stack.services.boq_suggest_store import split, store
from nirmaan_stack.services.boq_suggest_store.store_test_support import fixture_boq, purge_store_fixtures, raw_row

SHEET = "Sheet A "
DISC, CAT = "TEST_DISC", "test_cat"


class _Resp:
    def __init__(self, text):
        self.content = [SimpleNamespace(text=text)]
        self.stop_reason = "end_turn"
        self.usage = SimpleNamespace(input_tokens=100, output_tokens=20)


class _Client:
    """A fake Anthropic client: `responder(items)` -> reply text for the request's ROWS items."""

    def __init__(self, responder):
        self.responder = responder
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, model, max_tokens, messages, timeout):
        content = messages[0]["content"]
        self.calls.append(content)
        items = json.loads(content.split(split.ROWS_MARKER, 1)[1])
        return _Resp(self.responder(items))


def _answer(tag=0, omit=()):
    def responder(items):
        els = [{"id": it["id"], "attributes": {"a": {"value": it["id"] * 10 + tag, "confidence": 0.9}}}
               for it in items if it["id"] not in omit]
        return "Rows:\n" + json.dumps(els, indent=2)
    return responder


def _population(rows):
    return [{"excel_row": er, "description": "row %d description" % er, "discipline": DISC, "category_id": CAT,
             "anc_headers": [SHEET], "notes": ""} for er in rows]


def _env_mocks(rows):
    cfg = {"attribute_definitions": [{"id": "a", "type": "number"}], "pipelines": {"p": {}}}
    return [
        mock.patch.object(extraction, "assemble_population", return_value=(4, _population(rows))),
        mock.patch.object(extraction, "_load_active_configs", return_value={(DISC, CAT): cfg}),
        mock.patch.object(extraction, "build_attribute_defs", return_value=[{"id": "a", "type": "number"}]),
        mock.patch.object(extraction, "select_prompt_text", return_value="SRS-1 test prompt."),
        mock.patch("nirmaan_stack.api.boq.wizard.ai_settings.get_boq_ai_settings",
                   return_value={"enabled": True, "model": "m"}),
        mock.patch.object(store.SuggestPass, "_stamp", return_value="stamp-test"),
    ]


class _Mocks:
    def __init__(self, patches):
        self.patches = patches

    def __enter__(self):
        for p in self.patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.stop()


def _store_on():
    return mock.patch.object(store, "store_enabled", return_value=True)


def _records(boq):
    """The fixture's Row Records; `final_text` is the json column's stored TEXT (a json column is returned parsed)."""
    return frappe.db.sql('select *, final_attributes::text as final_text from "tabBoQ AI Suggest Row Record" '
                         'where boq = %s order by excel_row', (boq,), as_dict=True)


def _j(v):
    return json.loads(v) if isinstance(v, str) else v


def _capture_batches(boq):
    path = extraction._capture_path()
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r.get("kind") == "batch" and r.get("boq") == boq:
                out.append(r)
    return out


class TestStoreWrite(FrappeTestCase):
    def setUp(self):
        self.started = frappe.utils.now_datetime()

    def tearDown(self):
        purge_store_fixtures(error_logs_since=self.started)

    def _run(self, boq, rows, responder, only_rows=None, store_cb_from=None):
        checkpoints = []
        p = store_cb_from or store.SuggestPass.open(suggestion_run=None, run_id="rid-" + frappe.generate_hash(length=6),
                                                    boq=boq, sheet_name=SHEET, committed_version=4,
                                                    user="Administrator", kind=store.pass_kind(None, only_rows))
        with _Mocks(_env_mocks(rows)):
            env = extraction.run_extraction(boq, SHEET, client=_Client(responder),
                                            checkpoint_cb=lambda res, att: checkpoints.append(copy.deepcopy((res, att))),
                                            only_rows=only_rows, store_cb=p.on_batch)
        return env, checkpoints, p

    def test_t3_one_record_per_attempted_row_byte_equal_to_the_capture(self):
        boq = fixture_boq("t3")
        with _store_on():
            env, checkpoints, p = self._run(boq, [2, 3, 4], _answer())
        recs = _records(boq)
        self.assertEqual([r.excel_row for r in recs], [2, 3, 4])
        cap = _capture_batches(boq)
        self.assertEqual(len(cap), 1)
        cap = cap[0]
        by_id = {it["id"]: it for it in cap["payload_items"]}
        result_rows = {r["excel_row"]: r for r in checkpoints[0][0]}
        for r in recs:
            self.assertEqual(r.ai_input, json.dumps(by_id[r.excel_row], ensure_ascii=False))
            self.assertIn(r.raw_reply, cap["response_text"])
            self.assertEqual(json.loads(r.raw_reply)["id"], r.excel_row)
            self.assertEqual(r.reply_status, split.REPLY_OK)
            self.assertEqual(r.final_text, json.dumps(result_rows[r.excel_row]))   # the run's own row, same text
            self.assertEqual((r.run_record, r.sheet_name, r.committed_version, r.discipline, r.category_id),
                             (p.name, SHEET, 4, DISC, CAT))
            self.assertEqual((r.rates_status, r.supply_rate, r.catalogue_stamp), (store.RATES_PENDING, 0, "stamp-test"))
        q = frappe.db.get_value(store.DT_QUESTION, recs[0].question, ["question_text", "bytes"], as_dict=True)
        self.assertEqual(q.question_text + split.rows_block(cap["payload_items"]), cap["prompt"])
        self.assertNotIn("{{", q.question_text)
        run = frappe.db.get_value(store.DT_RUN, p.name, ["rows_read", "rows_written", "batches", "catalogue_stamps", "pass_kind"],
                                  as_dict=True)
        self.assertEqual((run.rows_read, run.rows_written, run.pass_kind), (3, 3, store.PASS_WHOLE))
        batches = _j(run.batches)["batches"]
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["calls"][0]["usage"], {"input_tokens": 100, "output_tokens": 20})
        self.assertIn("write_ms", batches[0])
        self.assertEqual(_j(run.catalogue_stamps), {DISC: "stamp-test"})

    def test_t3_a_new_record_has_rates_0_and_status_pending(self):
        """QR-C3 (a) (ANSWER 6): rates_status is the only truth for 'priced'; a new record (and a re-read one) reads
        0 for all four rates with status 'pending'."""
        boq = fixture_boq("rates")
        with _store_on():
            self._run(boq, [2], _answer())
            frappe.db.sql('update "tabBoQ AI Suggest Row Record" set supply_rate = 9, rates_status = %s where boq = %s',
                          ("priced", boq))   # as SRS-2 would; the next read must reset it
            first = _records(boq)[0]
            self.assertEqual((first.supply_rate, first.rates_status), (9, "priced"))
            self._run(boq, [2], _answer(tag=3))
        r = _records(boq)[0]
        self.assertEqual((r.supply_rate, r.install_rate, r.combined_rate, r.bcs_supply_rate, r.rates_status),
                         (0, 0, 0, 0, store.RATES_PENDING))

    def test_t3_a_second_run_overwrites_the_same_key(self):
        boq = fixture_boq("over")
        with _store_on():
            self._run(boq, [2, 3], _answer(tag=1))
            first = {r.excel_row: r for r in _records(boq)}
            _env, _cp, p2 = self._run(boq, [2, 3], _answer(tag=7))
        second = {r.excel_row: r for r in _records(boq)}
        self.assertEqual(len(second), 2)
        for er in (2, 3):
            self.assertEqual(second[er].name, first[er].name, "the record keeps its name")
            self.assertNotEqual(second[er].raw_reply, first[er].raw_reply)
            self.assertIn('"value": %d' % (er * 10 + 7), second[er].raw_reply)
            self.assertEqual(second[er].run_record, p2.name)
            self.assertGreaterEqual(second[er].run_date, first[er].run_date)

    def test_t3_a_selected_pass_writes_only_the_rows_it_read(self):
        boq = fixture_boq("sel")
        old_date = frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-10)
        raw_row(boq, 2, committed_version=4, sheet_name=SHEET, run_date=old_date, raw_reply="OLD", run_id="old-run")
        with _store_on():
            self._run(boq, [2, 3, 4], _answer(), only_rows=[3])
        recs = {r.excel_row: r for r in _records(boq)}
        self.assertEqual(sorted(recs), [2, 3])
        self.assertEqual((recs[2].raw_reply, recs[2].run_id, recs[2].run_date), ("OLD", "old-run", old_date))
        self.assertNotIn(4, recs)

    def test_t3_an_omitted_row_keeps_its_input_with_no_reply_element(self):
        boq = fixture_boq("omit")
        with _store_on():
            self._run(boq, [2, 3], _answer(omit={3}))
        recs = {r.excel_row: r for r in _records(boq)}
        self.assertEqual(recs[3].reply_status, split.REPLY_NONE)
        self.assertIsNone(recs[3].raw_reply)
        self.assertIn('"id": 3', recs[3].ai_input)

    def test_t3_one_question_for_two_batches_with_the_same_text(self):
        boq = fixture_boq("twob")
        rows = list(range(2, 27))   # 25 rows -> batches of 20 and 5
        with _store_on():
            _env, _cp, p = self._run(boq, rows, _answer())
        recs = _records(boq)
        self.assertEqual(len(recs), 25)
        self.assertEqual(len({r.question for r in recs}), 1)
        self.assertEqual({r.batch_no for r in recs}, {1, 2})
        self.assertEqual(frappe.db.count(store.DT_QUESTION, {"name": recs[0].question}), 1)
        self.assertEqual(len(_j(frappe.db.get_value(store.DT_RUN, p.name, "batches"))["batches"]), 2)

    def test_t3_the_upsert_names_the_doctypes_unique_constraint(self):
        self.assertEqual(store.ROW_KEY_CONSTRAINT, row_doctype.ROW_KEY_CONSTRAINT)
        self.assertEqual(store.ROW_KEY, tuple(row_doctype.ROW_KEY_FIELDS))

    def test_t4_a_failing_store_leaves_the_runner_untouched_and_logs_once(self):
        boq = fixture_boq("fail")
        with _store_on(), mock.patch.object(store.SuggestPass, "_upsert_row", side_effect=RuntimeError("store boom")):
            env, checkpoints, p = self._run(boq, list(range(2, 27)), _answer())
        with _Mocks(_env_mocks(list(range(2, 27)))):
            ref_cps = []
            ref = extraction.run_extraction(boq, SHEET, client=_Client(_answer()),
                                            checkpoint_cb=lambda res, att: ref_cps.append(copy.deepcopy((res, att))))
        self.assertEqual(json.dumps(env, sort_keys=True), json.dumps(ref, sort_keys=True))
        self.assertEqual(json.dumps(checkpoints), json.dumps(ref_cps))
        self.assertEqual(_records(boq), [])
        self.assertEqual(p.failed_steps, ["batch", "batch"])
        logs = frappe.get_all("Error Log", filters={"method": store.ERROR_TITLE, "creation": [">=", self.started]})
        self.assertEqual(len(logs), 1, "ONE Error Log per pass")

    def test_t5_without_store_cb_the_capture_checkpoints_and_envelope_are_identical(self):
        boq = fixture_boq("t5")
        outs = []
        for with_store in (False, True):
            cps, seen = [], []
            before = len(_capture_batches(boq))
            with _Mocks(_env_mocks([2, 3, 4])):
                env = extraction.run_extraction(
                    boq, SHEET, client=_Client(_answer()),
                    checkpoint_cb=lambda res, att: cps.append(copy.deepcopy((res, att))),
                    store_cb=(lambda obs, res, att: seen.append((obs, att))) if with_store else None)
            lines = [{k: v for k, v in r.items() if k != "ts"} for r in _capture_batches(boq)[before:]]
            outs.append((json.dumps(env, sort_keys=True), json.dumps(cps), json.dumps(lines, sort_keys=True), seen))
        self.assertEqual(outs[0][:3], outs[1][:3])
        self.assertEqual(outs[0][3], [])
        self.assertEqual([att for _o, att in outs[1][3]], [[2, 3, 4]])
        self.assertEqual([o["kind"] for o in outs[1][3][0][0]], ["batch"])

    def test_t5_extract_batch_without_store_obs_collects_nothing(self):
        ctx = {"boq": "B"}
        extraction._store_observe(ctx, [{"category_id": CAT}], "batch", text="x")
        self.assertEqual(ctx, {"boq": "B"})
        extraction._store_observe(None, [], "batch")   # never raises
        obs = []
        extraction._store_observe({"boq": "B", "store_obs": obs, "reask": True}, [{"category_id": CAT, "discipline": DISC}],
                                  "batch", text="x")
        self.assertEqual(obs, [{"text": "x", "kind": "batch", "reask": True, "category_id": CAT, "discipline": DISC}])

    def test_on_outside_tests_the_store_writes(self):
        boq = fixture_boq("prod")
        self.assertFalse(store.store_enabled(), "under bench run-tests the store is off")
        # NOT mock.patch.object(frappe.flags, ...): frappe.flags is a dict-backed object, and patch's restore can leave
        # `in_test` deleted (None) - every later capture write would then reach the REAL capture log. Set and restore.
        was = frappe.flags.in_test
        frappe.flags.in_test = False
        try:
            self.assertTrue(store.store_enabled())
            p = store.SuggestPass.open(suggestion_run=None, run_id="rid-prod", boq=boq, sheet_name=SHEET,
                                       committed_version=4, user="Administrator", kind=store.PASS_WHOLE)
            items = [{"id": 2, "description": "d"}]
            obs = {"kind": "batch", "payload_items": items, "content": "Q" + split.rows_block(items),
                   "text": '[{"id": 2, "attributes": {}}]', "category_id": CAT, "discipline": DISC, "model": "m"}
            with mock.patch.object(store.SuggestPass, "_stamp", return_value="s"):
                p.on_batch([obs], [{"excel_row": 2, "description": "d", "category_id": CAT, "attributes": {}}], [2])
        finally:
            frappe.flags.in_test = was
        self.assertTrue(frappe.flags.in_test)
        self.assertTrue(p.enabled)
        self.assertEqual(len(_records(boq)), 1)
        q = store.SuggestPass.open(suggestion_run=None, run_id="rid-test", boq=boq, sheet_name=SHEET,
                                   committed_version=4, user="Administrator", kind=store.PASS_WHOLE)
        self.assertFalse(q.enabled)
        self.assertIsNone(q.name, "under tests nothing is written")


class TestWorkerByteIdentity(FrappeTestCase):
    """T4 at the worker: three passes of the SAME selected-rows run - store off, store on, store failing - give the same
    run-doc writes and the same operation result. Carried rows (2, 4) never get a record."""

    def setUp(self):
        self.started = frappe.utils.now_datetime()

    def tearDown(self):
        purge_store_fixtures(error_logs_since=self.started)

    def _worker(self, boq, mode):
        writes = []

        def _progress(run_name, acc_results, acc_attempted, scope_pending=None):
            writes.append(("progress", rate_master.serialize_run_results(acc_results.values()), sorted(acc_attempted),
                           sorted(scope_pending) if scope_pending is not None else None))

        def _final(run_name, cv, ai_status, merged, acc_attempted, complete, halt_reason, boq, sheet_name, scope_pending=None):
            writes.append(("final", cv, ai_status, rate_master.serialize_run_results(merged), sorted(acc_attempted),
                           complete, halt_reason, sorted(scope_pending) if scope_pending is not None else None))

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
            mock.patch.object(rate_master, "_open_run_doc", return_value=("N", "RID", copy.deepcopy(carried), [2, 3, 4], {3})),
            mock.patch.object(rate_master, "_write_run_progress", side_effect=_progress),
            mock.patch.object(rate_master, "_finalise_run", side_effect=_final),
            mock.patch.object(rate_master, "_start_match_after_suggest", return_value=None),
            mock.patch.object(rate_master.background_ops, "set_row_progress"),
            mock.patch.object(rate_master.operation_marker, "release_own"),
            mock.patch.object(store, "store_enabled", return_value=(mode != "off")),
        ]
        if mode == "failing":
            patches.append(mock.patch.object(store.SuggestPass, "_upsert_row", side_effect=RuntimeError("store boom")))
        with _Mocks(patches):
            payload = rate_master._suggest_worker(boq=boq, sheet_name=SHEET, only_rows=[3])
        return json.dumps(writes), json.dumps(payload, sort_keys=True, default=str)

    def test_t4_store_off_on_and_failing_give_byte_identical_run_writes(self):
        boq = fixture_boq("wk")
        old_date = frappe.utils.add_to_date(frappe.utils.now_datetime(), days=-3)
        raw_row(boq, 2, committed_version=4, sheet_name=SHEET, run_date=old_date, raw_reply="OLD-2", run_id="old")
        off = self._worker(boq, "off")
        on = self._worker(boq, "on")
        recs = {r.excel_row: r for r in _records(boq)}
        self.assertEqual(sorted(recs), [2, 3], "only the read row 3 is new; carried 4 has none")
        self.assertEqual((recs[2].raw_reply, recs[2].run_date), ("OLD-2", old_date), "carried row 2 keeps its older record")
        run = frappe.get_all(store.DT_RUN, filters={"boq": boq}, fields=["pass_kind", "run_status", "rows_read", "finished_at"])
        self.assertEqual(len(run), 1)
        self.assertEqual((run[0].pass_kind, run[0].run_status, run[0].rows_read), (store.PASS_SELECTED, "complete", 1))
        self.assertIsNotNone(run[0].finished_at)
        failing = self._worker(boq, "failing")
        self.assertEqual(off, on, "the store changes nothing the run writes or returns")
        self.assertEqual(off, failing, "a failing store changes nothing the run writes or returns")
        logs = frappe.get_all("Error Log", filters={"method": store.ERROR_TITLE, "creation": [">=", self.started]})
        self.assertEqual(len(logs), 1)
