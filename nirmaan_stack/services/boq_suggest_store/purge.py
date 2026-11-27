"""SRS-1 (SRS-D0 D6; owner R-BCS-138 "the DB should keep data for 1 year and then purge ... daily or weekly, you
decide"; walk-through 27 Nov: DAILY): delete Suggest run store records older than one year.

`hooks.py` runs `run_daily` at 01:30 (cron "30 1 * * *", clear of the 02:00 - 06:00 jobs). It:
  1. deletes Row Records whose `run_date` is more than `KEEP_DAYS` days old, by name, `BATCH` at a time, committing after
     each batch, at most `MAX_BATCHES` batches a night (the rest wait for the next night);
  2. then Run Records older than a year that no Row Record points to any more;
  3. then Questions that no Row Record references.
It touches no other table.

RAW SQL deletes, on purpose (CODING_STANDARDS § Writing raw SQL): the three doctypes have no doc_events, no controller
hooks, `track_changes` 0 and nothing derived from them, so a raw delete skips nothing. A batch of 1,000 by primary key
never holds a long lock.
"""

import frappe

KEEP_DAYS = 365
BATCH = 1000
MAX_BATCHES = 200


def cutoff(now=None):
    """The purge line: records whose run_date is BEFORE this are deleted."""
    return frappe.utils.add_to_date(now or frappe.utils.now_datetime(), days=-KEEP_DAYS)


def run_daily(now=None, batch=BATCH, max_batches=MAX_BATCHES):
    """Delete store records older than a year. Returns the counts {rows, runs, questions, batches, more_left}."""
    line = cutoff(now)
    rows = batches = 0
    more_left = False
    while True:
        if batches >= max_batches:
            more_left = bool(frappe.db.sql(
                'select 1 from "tabBoQ AI Suggest Row Record" where run_date < %s limit 1', (line,)))
            break
        names = [r[0] for r in frappe.db.sql(
            'select name from "tabBoQ AI Suggest Row Record" where run_date < %s order by run_date limit %s',
            (line, batch))]
        if not names:
            break
        frappe.db.sql('delete from "tabBoQ AI Suggest Row Record" where name in %s', (tuple(names),))
        frappe.db.commit()
        rows += len(names)
        batches += 1
    runs = frappe.db.sql(
        """delete from "tabBoQ AI Suggest Run Record" r
           where coalesce(r.finished_at, r.started_at, r.creation) < %s
             and not exists (select 1 from "tabBoQ AI Suggest Row Record" w where w.run_record = r.name)
           returning r.name""", (line,))
    frappe.db.commit()
    questions = frappe.db.sql(
        """delete from "tabBoQ AI Suggest Question" q
           where not exists (select 1 from "tabBoQ AI Suggest Row Record" w where w.question = q.name)
           returning q.name""")
    frappe.db.commit()
    return {"rows": rows, "runs": len(runs), "questions": len(questions), "batches": batches, "more_left": more_left}
