"""Test-only helpers for the Suggest run store suites (SRS-1): fixture identities that can never be real, and ONE purge
helper the store suites import (CODING_STANDARDS § Writing tests: one purge helper per suite family, imported, not copied).

Every fixture BoQ name starts `BOQ-TEST-SRS1-`, which is outside the BOQs series, so a purge by that prefix can never touch a
real record. Never call these on real data.
"""

import hashlib

import frappe

FIXTURE_BOQ_PREFIX = "BOQ-TEST-SRS1-"
STORE_TABLES = ("tabBoQ AI Suggest Row Record", "tabBoQ AI Suggest Run Record")
# the store family's own Error Log titles (SRS-1 store write; SRS-2 rates job and its trigger) - purged by time, never others
ERROR_LOG_TITLES = ("BoQ suggest store write failed", "BoQ suggest store rates failed", "BoQ suggest store rates trigger failed")


def fixture_boq(tag=""):
    """A fixture BoQ name outside the BOQs series (no BOQs row is made: the store writes by raw SQL)."""
    return f"{FIXTURE_BOQ_PREFIX}{(tag or 'X').upper()}-{frappe.generate_hash(length=6)}"


def raw_row(boq, excel_row, committed_version=1, sheet_name="Sheet A ", run_date=None, **extra):
    """Insert one Row Record by plain raw SQL (no ON CONFLICT), as a test fixture. Returns its name."""
    name = frappe.generate_hash(length=10)
    now = frappe.utils.now_datetime()
    values = {"name": name, "creation": now, "modified": now, "owner": "Administrator", "modified_by": "Administrator",
              "docstatus": 0, "idx": 0, "boq": boq, "sheet_name": sheet_name, "committed_version": committed_version,
              "excel_row": excel_row, "run_date": run_date or now}
    values.update(extra)
    cols = list(values)
    frappe.db.sql('insert into "tabBoQ AI Suggest Row Record" (%s) values (%s)'
                  % (", ".join('"%s"' % c for c in cols), ", ".join(["%s"] * len(cols))), [values[c] for c in cols])
    return name


def raw_run(boq, started_at=None, **extra):
    """Insert one Run Record by raw SQL, as a test fixture. Returns its name."""
    name = frappe.generate_hash(length=10)
    now = frappe.utils.now_datetime()
    values = {"name": name, "creation": now, "modified": now, "owner": "Administrator", "modified_by": "Administrator",
              "docstatus": 0, "idx": 0, "boq": boq, "started_at": started_at or now}
    values.update(extra)
    cols = list(values)
    frappe.db.sql('insert into "tabBoQ AI Suggest Run Record" (%s) values (%s)'
                  % (", ".join('"%s"' % c for c in cols), ", ".join(["%s"] * len(cols))), [values[c] for c in cols])
    return name


def raw_question(text, when=None):
    """Insert one Question by raw SQL, as a test fixture. Returns its name (the sha256 of `text`, as the store names it)."""
    name = hashlib.sha256(text.encode("utf-8")).hexdigest()
    now = when or frappe.utils.now_datetime()
    frappe.db.sql('insert into "tabBoQ AI Suggest Question" (name, creation, modified, owner, modified_by, docstatus, idx, '
                  'question_text, bytes, first_seen, last_used) values (%s, %s, %s, %s, %s, 0, 0, %s, %s, %s, %s)',
                  (name, now, now, "Administrator", "Administrator", text, len(text.encode("utf-8")), now, now))
    return name


def purge_store_fixtures(question_names=(), error_logs_since=None):
    """Remove every store row a store suite made: rows / runs whose boq starts with the fixture prefix, the questions only
    fixture rows referenced (plus any named), and - when `error_logs_since` is given - the store's own Error Log rows
    written since then. Rolls back FIRST (a poisoned transaction), deletes each scope in its own try, commits per scope,
    and reports a failure instead of swallowing it."""
    frappe.db.rollback()
    problems = []
    names = set(question_names)
    try:
        names |= {q for (q,) in frappe.db.sql(
            """select distinct w.question from "tabBoQ AI Suggest Row Record" w where w.boq like %s and w.question is not null
               and not exists (select 1 from "tabBoQ AI Suggest Row Record" o where o.question = w.question and o.boq not like %s)""",
            (FIXTURE_BOQ_PREFIX + "%", FIXTURE_BOQ_PREFIX + "%"))}
    except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
        frappe.db.rollback()
        problems.append(f"question lookup: {exc}")
    scopes = [
        ('delete from "tabBoQ AI Suggest Row Record" where boq like %s', (FIXTURE_BOQ_PREFIX + "%",)),
        ('delete from "tabBoQ AI Suggest Run Record" where boq like %s', (FIXTURE_BOQ_PREFIX + "%",)),
    ]
    if names:
        scopes.append(('delete from "tabBoQ AI Suggest Question" where name in %s', (tuple(names),)))
    if error_logs_since is not None:
        scopes.append(('delete from "tabError Log" where method in %s and creation >= %s',
                       (ERROR_LOG_TITLES, error_logs_since)))
    for sql, params in scopes:
        try:
            frappe.db.sql(sql, params)
            frappe.db.commit()
        except Exception as exc:  # noqa: BLE001 -- reported, never swallowed
            frappe.db.rollback()
            problems.append(f"{sql[:40]}: {exc}")
    if problems:
        print("WARNING -- suggest store purge INCOMPLETE, rows left in the live DB: %s" % "; ".join(problems))
    return problems
