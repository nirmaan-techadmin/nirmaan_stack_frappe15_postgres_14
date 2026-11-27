"""CAT-3 (owner 2026-11-26 00:11, R1): CATALOGUE LABELS, made from each row's OWN values by ONE rule.

A label is a code-owned concept (``conductor = al``, ``poles = 3``; a label value is never a catalogue word, so C1 never counts it) attached to a catalogue row by the table below,
which reads ONLY that row's attributes. Code that recognises a GROUP of rows that grows with the catalogue (the cable
conductor / armour, the breaker poles, the insulation cloth cladding) names the LABEL VALUE, never the catalogue spelling,
so a new SKU added by any route (rate-file load, Rate Master add / edit, CSV upload, Desk) is recognised with nobody filling
anything in (owner: "the user can t be expected to fill them also").

WHERE LABELS LIVE (CAT-D1 E3, option L3): NOTHING IS STORED. Labels are computed on every read -- the served items
(`attach`, called by `api/boq/rate_master._serve_items`, the last step of `get_rate_master_items`), the Python readers
(`label_of_value`) -- emitted by the exporter per item as derived data, and VERIFIED by the loader (G-LABEL,
`label_problems`): a rate file whose labels differ from the rule is refused; a file with no labels (older files) loads.

THE RULE: each entry has ``scope_kinds`` (the item kinds it applies to), ``from_attr`` (the attribute it reads), ``cases``
[(regex over the value, label value)] and ``total``. EXACTLY ONE case must match. Zero or two matches on a TOTAL label =
the row is FLAGGED for Admin (``label_flags``, the amber "could not label" chip) -- it is still saved and priced as before,
never refused. On a PARTIAL label, no match = no label (and two = the flag). A ``{1}`` label value takes the case's first
capture group (the cladding gauge). A row in scope whose attribute is ABSENT gets nothing (no flag).

The cases recognise the catalogue values today's code lists typed (proved set-equal by file and line in
`test_catalogue_labels`, and side by side in the CAT-3 PF3 workbook). BoQ-writing variants (``spn_family_tokens``, the words
a BoQ uses for armour) stay in code (owner 2026-11-26 00:53, QR-C-1): only catalogue VALUES moved here.

DORMANT VALUES: ``poles`` 1+N / 3+N (an SPN / TPN pole spelling) are made by the rule but carried by no SKU today; they keep
the poles-plus-neutral ladder's rung 1 working the day such a SKU is added (owner: "if we later add SPN in catalog it gets
matched first"; CAT-D1 E1, QR-C-POLES).
"""
from __future__ import annotations

import re

# fmt: off
LABEL_RULES = (
    {"id": "conductor", "scope_kinds": ("cable", "termination"), "from_attr": "material", "total": True,
     "cases": ((r"^alumin(i)?um$", "al"), (r"^copper$", "cu"))},
    {"id": "armour", "scope_kinds": ("cable", "termination"), "from_attr": "insulation", "total": True,
     "cases": ((r"^un-?armou?red$", "unarmoured"), (r"^armou?red$", "armoured"))},
    {"id": "poles", "scope_kinds": ("db_switchgear_item",), "from_attr": "pole", "total": True,
     "cases": ((r"^SP$", "1"), (r"^DP$", "2"), (r"^TP$", "3"), (r"^FP$", "4"), (r"^SPN$", "1+N"), (r"^TPN$", "3+N"))},
    {"id": "cloth_cladding", "scope_kinds": ("hvac_insulation_item",), "from_attr": "cladding", "total": False,
     "cases": ((r"^(?!.*\d{2}G).*glass cloth", "cloth"), (r"^\d{2}G aluminium with glass cloth$", "cloth_on_aluminium"))},
    {"id": "cladding_gauge", "scope_kinds": ("hvac_insulation_item",), "from_attr": "cladding", "total": False,
     "cases": ((r"^(\d{2})G\b", "{1}"),)},
)
# fmt: on

# Label values the rule makes but no SKU carries today (see the module docstring). Listed so a reader can see they are
# deliberate; G-LABEL's code scan accepts any value a rule makes.
DORMANT_LABEL_VALUES = (("poles", "1+N"), ("poles", "3+N"))

_COMPILED = {r["id"]: [(re.compile(rx, re.I), lv) for rx, lv in r["cases"]] for r in LABEL_RULES}
_BY_ID = {r["id"]: r for r in LABEL_RULES}


def rule(label_id):
    """The rule entry for one label id (KeyError for an unknown id)."""
    return _BY_ID[label_id]


def _hits(label_id, value):
    if not isinstance(value, str):
        return []
    out = []
    for rx, lv in _COMPILED[label_id]:
        m = rx.search(value)
        if m:
            out.append(m.group(1) if lv == "{1}" else lv)
    return out


def label_of_value(label_id, value):
    """PURE. The label value one catalogue value carries for `label_id` (scope not checked), or None when zero or two
    cases match. The Python readers (the cable corroborator, the poles ladder) use this on a value they already hold."""
    h = _hits(label_id, value)
    return h[0] if len(h) == 1 else None


def labels_for(kind, attributes):
    """PURE. ({label_id: value}, [flag]) for one row from its OWN kind and attributes. A flag is
    {"label", "value", "reason"} -- the row is still saved and priced as before (owner 2026-11-26 00:11)."""
    labels, flags = {}, []
    attributes = attributes or {}
    for r in LABEL_RULES:
        if kind not in r["scope_kinds"] or r["from_attr"] not in attributes:
            continue
        v = attributes.get(r["from_attr"])
        h = _hits(r["id"], v)
        if len(h) == 1:
            labels[r["id"]] = h[0]
        elif r["total"] or len(h) > 1:
            flags.append({"label": r["id"], "value": v,
                          "reason": "no case matches" if not h else "%d cases match" % len(h)})
    return labels, flags


def attach(items):
    """Put ``labels`` and ``label_flags`` on each served item dict (in place) and return the list. Computed from the
    item's own ``kind`` and ``attributes`` -- nothing is stored. Adds no other key."""
    for it in items:
        labels, flags = labels_for(it.get("kind"), it.get("attributes"))
        it["labels"] = labels
        it["label_flags"] = flags
    return items


def all_label_values():
    """Every (label_id, value) a rule can make, for the fixed-value cases (a capture case adds none)."""
    return {(r["id"], lv) for r in LABEL_RULES for _rx, lv in r["cases"] if lv != "{1}"}


def lv(label_id, value):
    """The checked spelling of a label value a reader names: refuses (ValueError) a value no rule makes, so a reader can
    never name a label that does not exist. G-LABEL's suite scan reads every ``lv("<id>", "<value>")`` call."""
    if (label_id, value) not in all_label_values():
        raise ValueError("no catalogue label rule makes %s=%r" % (label_id, value))
    return value


def label_problems(items):
    """G-LABEL at load: every item that CARRIES ``labels`` must carry exactly what the rule makes from its own kind and
    attributes. An item without a ``labels`` key (an older rate file) is not checked. Returns a list of problem dicts
    {"index", "item_uid", "carried", "rule"}; empty = pass."""
    out = []
    for idx, it in enumerate(items or []):
        if not isinstance(it, dict) or "labels" not in it:
            continue
        want, _flags = labels_for((it.get("kind") or "").strip(), it.get("attributes") or {})
        if it.get("labels") != want:
            out.append({"index": idx, "item_uid": it.get("item_uid"), "carried": it.get("labels"), "rule": want})
    return out


def format_label_problem(p):
    """One refusal sentence for a G-LABEL problem."""
    return ("REFUSED: items[%d] (%s) carries labels %r but the label rule makes %r from its own values - labels are made "
            "from the row, never written by hand" % (p["index"], p.get("item_uid") or "no item_uid", p["carried"], p["rule"]))


def value_label_map(items):
    """{label_id: {"from_attr", "scope_kinds", "values": {catalogue value: label value}}} over every distinct value the
    given items carry in scope. Written to the frontend test fixture so test readers of RAW rate files (which carry no
    served labels) label items exactly as the server does; `test_catalogue_labels` proves the fixture equals the rule."""
    out = {}
    for r in LABEL_RULES:
        vals = {}
        for it in items:
            if it.get("kind") in r["scope_kinds"]:
                v = (it.get("attributes") or {}).get(r["from_attr"])
                lab = label_of_value(r["id"], v)
                if isinstance(v, str) and lab is not None:
                    vals[v] = lab
        out[r["id"]] = {"from_attr": r["from_attr"], "scope_kinds": list(r["scope_kinds"]), "total": r["total"],
                        "values": dict(sorted(vals.items()))}
    return out
