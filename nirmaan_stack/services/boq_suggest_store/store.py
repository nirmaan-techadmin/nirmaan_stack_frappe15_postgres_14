"""SRS-1 - the Suggest run store: what each AI Suggest pass sent and got back, kept per row (SRS-D0 D1 / D4 / D9).

Owner R-BCS-138 / 139 (25 Nov 23:30 - 23:35): for every row an AI Suggest run reads, keep the AI input, the raw model
output and the final values, with the usual identifiers, readable by Admins only, for one year, overwritten when the row
is read again. AI Suggest only (owner 27 Nov 13:30): matching is never written here.

ONE writer, called by the Suggest worker (`api/boq/rate_master._suggest_worker`):
  * `SuggestPass.open(...)` once per pass - the Run Record;
  * `SuggestPass.on_batch(...)` - handed to `extraction.run_extraction` as its `store_cb`, called right after each
    batch's checkpoint with what the batch call(s) sent and got back (observed in `_extract_batch`, never changed),
    the batch's result rows (the run's own rows, never re-derived) and the batch's attempted rows;
  * `SuggestPass.finish(...)` after the run's own commit - the pass's end state.

What is written:
  * `BoQ AI Suggest Row Record`, ONE per (boq, sheet_name, committed_version, excel_row) - the overwrite key, a
    UNIQUE constraint (`ROW_KEY_CONSTRAINT`). Only rows the AI READ in this pass are written (owner QR-C2 "keep all"):
    a row a selected-rows pass only CARRIES is never in `attempted` and keeps its older record and date.
  * `BoQ AI Suggest Question`, each distinct FILLED question text once, named by its sha256 (QR-C1).
  * `BoQ AI Suggest Run Record`, one per pass, with the catalogue stamp per discipline (R3) and a `batches` list.

NEVER FAILS OR SLOWS THE RUN (D9). Every step runs inside its own savepoint and its own try / except: on any error it
rolls back ONLY its own write (the checkpoint before it has already committed), writes ONE Error Log per pass
(`ERROR_TITLE`), and returns. It sends nothing, uploads nothing, pushes nothing.

RAW SQL, on purpose (CODING_STANDARDS § Writing raw SQL): the three doctypes have NO doc_events, no controller hooks,
`track_changes` 0 and nothing derived from them, so a raw `INSERT ... ON CONFLICT DO UPDATE` skips nothing; and the
worker runs as whichever user started Suggest (Estimates users included), who must produce records they cannot read.

UNDER `bench run-tests` the store is OFF (`store_enabled`), as the capture log is (`extraction._capture_path`): older
tests drive the real worker against the live database and clean up only what they know. SRS-1's own tests switch it on.
"""

import json
import time

import frappe

from nirmaan_stack.services.boq_suggest_store import split

DT_ROW = "BoQ AI Suggest Row Record"
DT_RUN = "BoQ AI Suggest Run Record"
DT_QUESTION = "BoQ AI Suggest Question"
ROW_KEY = ("boq", "sheet_name", "committed_version", "excel_row")
ROW_KEY_CONSTRAINT = "boq_ai_suggest_row_record_key_unique"
ERROR_TITLE = "BoQ suggest store write failed"
RATES_PENDING = "pending"   # SRS-2 fills the rates; a re-read row's old rates belonged to its old read
PASS_WHOLE, PASS_SELECTED, PASS_RESUME = "whole_sheet", "selected_rows", "resume"
_SAVEPOINT = "boq_suggest_store"


def store_enabled():
    """False under `bench run-tests` (see the module docstring); SRS-1's tests patch this to True."""
    return not frappe.flags.in_test


def pass_kind(resume_run_id, scope):
    """whole_sheet / selected_rows / resume - a resume of any run is its own pass of the same run_id."""
    if resume_run_id:
        return PASS_RESUME
    return PASS_SELECTED if scope is not None else PASS_WHOLE


def _dumps(value):
    """JSON text with default separators - the run's own serialisation (`serialize_run_results`), so a stored result
    row is the same text as the run doc's."""
    return None if value is None else json.dumps(value)


class SuggestPass:
    """The store's view of ONE Suggest pass. Every public method is safe to call and never raises."""

    def __init__(self, *, suggestion_run, run_id, boq, sheet_name, committed_version, user, kind):
        self.suggestion_run = suggestion_run
        self.run_id = run_id
        self.boq = boq
        self.sheet_name = sheet_name
        self.committed_version = committed_version
        self.user = user
        self.kind = kind
        self.name = None
        self.project = None
        self.sheet_doc = None
        self.started_at = None
        self.batches = []
        self.stamps = {}
        self.rows_read = 0
        self.rows_written = 0
        self.model = None
        self.failed_steps = []
        self._logged = False
        self._last_mark = time.monotonic()
        self.enabled = store_enabled()

    # ── public, never raise ─────────────────────────────────────────────────────────────────────────────────────
    @classmethod
    def open(cls, *, suggestion_run, run_id, boq, sheet_name, committed_version, user, kind):
        """Start a pass: write its Run Record. Returns the pass (enabled or not); never raises."""
        p = cls(suggestion_run=suggestion_run, run_id=run_id, boq=boq, sheet_name=sheet_name,
                committed_version=committed_version, user=user, kind=kind)
        p._guarded("open", p._open)
        p._last_mark = time.monotonic()
        return p

    def on_batch(self, observations, row_results, attempted):
        """The runner's `store_cb`: one completed sub-batch (see the module docstring). Never raises."""
        gap_ms = round((time.monotonic() - self._last_mark) * 1000)
        self._guarded("batch", lambda: self._write_batch(list(observations or []), list(row_results or []),
                                                         [int(x) for x in (attempted or [])], gap_ms))
        self._last_mark = time.monotonic()

    def finish(self, *, model=None, ai_status=None, run_status=None, halt_reason=None):
        """The pass's end state on its Run Record, after the run's own commit. Never raises."""
        self._guarded("finish", lambda: self._finish(model, ai_status, run_status, halt_reason))

    # ── the guard ───────────────────────────────────────────────────────────────────────────────────────────────
    def _guarded(self, step, fn):
        if not self.enabled:
            return
        try:
            frappe.db.savepoint(_SAVEPOINT)
            fn()
            frappe.db.release_savepoint(_SAVEPOINT)
            frappe.db.commit()
        except Exception:  # noqa: BLE001 -- the store must never fail the run (D9)
            self.failed_steps.append(step)
            try:
                frappe.db.rollback(save_point=_SAVEPOINT)
            except Exception:  # noqa: BLE001 -- savepoint gone: the run's own work is committed, so a full rollback loses none of it
                try:
                    frappe.db.rollback()
                except Exception:  # noqa: BLE001
                    pass
            self._log_once(step)

    def _log_once(self, step):
        if self._logged:
            return
        self._logged = True
        try:
            frappe.log_error(
                title=ERROR_TITLE,
                message="boq=%s sheet=%r cv=%s run_id=%s step=%s\n%s" % (
                    self.boq, self.sheet_name, self.committed_version, self.run_id, step, frappe.get_traceback()),
            )
            frappe.db.commit()
        except Exception:  # noqa: BLE001
            try:
                frappe.db.rollback()
            except Exception:  # noqa: BLE001
                pass

    # ── the writes ──────────────────────────────────────────────────────────────────────────────────────────────
    def _open(self):
        self.project = frappe.db.get_value("BOQs", self.boq, "project")
        sheets = frappe.get_all("BoQ Sheet", filters={"boq": self.boq, "sheet_name": self.sheet_name,
                                                      "commit_version": self.committed_version},
                                pluck="name", limit=1)
        self.sheet_doc = sheets[0] if sheets else None
        now = frappe.utils.now_datetime()
        self.started_at = now
        self.name = frappe.generate_hash(length=10)
        frappe.db.sql(
            """insert into "tabBoQ AI Suggest Run Record"
               (name, creation, modified, owner, modified_by, docstatus, idx,
                run_id, suggestion_run, boq, project, sheet_name, committed_version, pass_kind, run_by, started_at,
                catalogue_stamps, batches, rows_read, rows_written, store_failures)
               values (%s, %s, %s, %s, %s, 0, 0, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, 0)""",
            (self.name, now, now, self.user, self.user, self.run_id, self.suggestion_run, self.boq, self.project,
             self.sheet_name, self.committed_version, self.kind, self.user, now,
             _dumps({}), _dumps({"batches": []})),
        )

    def _node_names(self, excel_rows):
        if not self.sheet_doc or not excel_rows:
            return {}
        out = {}
        for n in frappe.get_all("BOQ Nodes", filters={"boq": self.boq, "sheet": self.sheet_doc, "is_current": 1,
                                                      "source_row_number": ["in", excel_rows]},
                                fields=["name", "source_row_number"], order_by="sort_order asc"):
            out.setdefault(int(n["source_row_number"]), n["name"])
        return out

    def _stamp(self, discipline):
        if not discipline:
            return None
        if discipline not in self.stamps:
            try:
                from nirmaan_stack.services.boq_rate_master import catalogue_lists
                self.stamps[discipline] = (catalogue_lists.current(discipline, fresh=False) or {}).get("stamp")
            except Exception:  # noqa: BLE001 -- a stamp we cannot read is recorded as unknown, never guessed
                self.stamps[discipline] = None
        return self.stamps[discipline]

    def _write_batch(self, observations, row_results, attempted, gap_ms):
        t0 = time.monotonic()
        now = frappe.utils.now_datetime()
        splits = [split.split_call(o) for o in observations]
        final = split.merge_calls(splits)
        results = {int(r["excel_row"]): r for r in row_results}
        first = observations[0] if observations else {}
        discipline = next((o.get("discipline") for o in observations if o.get("discipline")), None)
        category_id = next((o.get("category_id") for o in observations if o.get("category_id")), None)
        self.model = next((o.get("model") for o in observations if o.get("model")), self.model)
        stamp = self._stamp(discipline)
        if discipline:
            self.stamps[discipline] = stamp   # the Run Record's {discipline: stamp} (R3)
        batch_no = len(self.batches) + 1

        # the questions, once each (QR-C1)
        for sp in splits:
            self._upsert_question(sp["question"], category_id, discipline, now)

        nodes = self._node_names(attempted)
        written = []
        for rid in attempted:
            piece = final.get(rid)
            res = results.get(rid)
            if piece is None and res is None:
                continue
            q = split.fingerprint(piece["question"]) if piece else None
            earlier = (piece or {}).get("earlier_replies") or []
            if piece and piece.get("second_opinion"):
                earlier = earlier + [{"second_opinion_verdict": piece["second_opinion"]}]
            values = {
                "boq": self.boq, "sheet_name": self.sheet_name, "committed_version": self.committed_version,
                "excel_row": rid, "boq_node": nodes.get(rid), "project": self.project,
                "description": (res or {}).get("description"),
                "discipline": discipline, "category_id": (res or {}).get("category_id") or category_id,
                "run_record": self.name, "run_id": self.run_id, "run_date": now,
                "question": q, "batch_no": batch_no, "batch_rows": len(attempted),
                "ai_input": (piece or {}).get("ai_input"), "raw_reply": (piece or {}).get("raw_reply"),
                "reply_status": (piece or {}).get("reply_status") or split.REPLY_NONE,
                "final_attributes": _dumps(res),
                "coercion_trail": _dumps((piece or {}).get("coercion_trail")),
                "earlier_replies": _dumps({"replies": earlier}),
                # Frappe makes Currency columns NOT NULL DEFAULT 0 on Postgres: "not priced yet" is rates_status
                # "pending", never a NULL rate (QR-C3 (a)). A re-read row's old rates belonged to its old read.
                "supply_rate": 0, "install_rate": 0, "combined_rate": 0, "bcs_supply_rate": 0,
                "rates_status": RATES_PENDING, "rates_detail": None, "pricing_stamp": None,
                "catalogue_stamp": stamp,
            }
            self._upsert_row(values, now)
            written.append(rid)

        write_ms = round((time.monotonic() - t0) * 1000, 1)
        self.rows_read += len(attempted)
        self.rows_written += len(written)
        entry = {
            "batch_no": batch_no, "category_id": category_id, "discipline": discipline, "rows": attempted,
            "calls": [dict(sp["batch"], question=split.fingerprint(sp["question"])) for sp in splits],
            "rows_written": written, "write_ms": write_ms, "gap_ms": gap_ms,
        }
        if not first:
            entry["note"] = "no call observed for this batch"
        self.batches.append(entry)
        self._update_run(now)

    def _upsert_question(self, text, category_id, discipline, now):
        name = split.fingerprint(text)
        # ON CONFLICT: the same text seen again only moves last_used (QR-C1: stored once, shared by every row using it)
        frappe.db.sql(
            """insert into "tabBoQ AI Suggest Question"
               (name, creation, modified, owner, modified_by, docstatus, idx,
                question_text, category_id, discipline, bytes, first_seen, last_used)
               values (%s, %s, %s, %s, %s, 0, 0, %s, %s, %s, %s, %s, %s)
               on conflict (name) do update set last_used = excluded.last_used, modified = excluded.modified""",
            (name, now, now, self.user, self.user, text, category_id, discipline, len(text.encode("utf-8")), now, now),
        )

    def _upsert_row(self, values, now):
        cols = list(values)
        insert_cols = ["name", "creation", "modified", "owner", "modified_by", "docstatus", "idx"] + cols
        params = [frappe.generate_hash(length=10), now, now, self.user, self.user, 0, 0] + [values[c] for c in cols]
        update = ", ".join('"%s" = excluded."%s"' % (c, c) for c in cols if c not in ROW_KEY)
        # ON CONFLICT on the overwrite key (the UNIQUE constraint): the row's next read REPLACES its record; the record
        # keeps its name and creation, everything else is the new read's (owner R1 "older data can be overwritten").
        frappe.db.sql(
            'insert into "tabBoQ AI Suggest Row Record" (%s) values (%s) '
            'on conflict (boq, sheet_name, committed_version, excel_row) do update set %s, '
            'modified = excluded.modified, modified_by = excluded.modified_by'
            % (", ".join('"%s"' % c for c in insert_cols), ", ".join(["%s"] * len(insert_cols)), update),
            params,
        )

    def _update_run(self, now):
        frappe.db.sql(
            """update "tabBoQ AI Suggest Run Record"
               set modified = %s, catalogue_stamps = %s, batches = %s, rows_read = %s, rows_written = %s, model = %s
               where name = %s""",
            (now, _dumps(self.stamps), _dumps({"batches": self.batches}), self.rows_read,
             self.rows_written, self.model, self.name),
        )

    def _finish(self, model, ai_status, run_status, halt_reason):
        if not self.name:
            return
        now = frappe.utils.now_datetime()
        frappe.db.sql(
            """update "tabBoQ AI Suggest Run Record"
               set modified = %s, finished_at = %s, model = %s, ai_status = %s, run_status = %s, halt_reason = %s,
                   store_failures = %s
               where name = %s""",
            (now, now, model or self.model, ai_status, run_status, halt_reason, len(self.failed_steps), self.name),
        )
