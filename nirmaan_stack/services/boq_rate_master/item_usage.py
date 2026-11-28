"""CAT-3 (owner 2026-11-26 00:10, R6; CAT-D1 E6 + review caveat 1): WHAT STOPS WORKING if a catalogue row goes or changes.

The safety net NEVER blocks an edit: Rate Master's Deactivate and Edit dialogs, and the CSV preview, show this list and the Admin
goes ahead ("Deactivate anyway" / "Save anyway"). Only a rate-file LOAD refuses (CAT-1's gate).

HOW: the answer is a DIFFERENCE of CAT-1's own reference gate (`catalogue_gate.reference_problems`, the declared reference-key
registry: value references, code targets, item references, Pricing Input ids, `{{cat:}}` / `{{item:}}` / `{{note:}}` placeholders,
pinned cases). Every config of the discipline is checked against the catalogue as it stands NOW and as it WOULD stand after the
change (the row removed, or its values replaced); a REFUSE line that appears only afterwards is something that "will stop
working until the rate file is updated"; an INFO line that appears only afterwards is "also" (a pinned case or example naming
it). "Still works" counts the references naming one of the row's values that keep a carrier. Nothing here writes.
"""
from __future__ import annotations

import copy
import re
import time

from nirmaan_stack.services.boq_rate_master import catalogue_gate, catalogue_labels, catalogue_lists


def _key(p):
    return (p.get("config"), p.get("path"), p.get("message"))


def _get(node, path):
    """The value at a dotted / indexed config path ("list_spec.pricing.text_notes[3].line"), or None."""
    cur = node
    for part in re.findall(r"[^.\[\]]+|\[\d+\]", path.split(" ")[0]):
        if part.startswith("["):
            i = int(part[1:-1])
            cur = cur[i] if isinstance(cur, list) and i < len(cur) else None
        else:
            cur = cur.get(part) if isinstance(cur, dict) else None
        if cur is None:
            return None
    return cur


def _humanize(code):
    """'valve_type' -> 'Valve type' (the last resort when no screen label exists)."""
    s = str(code or "").replace("_", " ").strip()
    return s[:1].upper() + s[1:] if s else s


def attr_label(configs, attr, fill=None):
    """PURE (CAT-3 K5c, owner review point 3): the column heading people see for an attribute key - its `label` in any config's
    attribute definitions (list_spec first), else the key made readable. Never the code name itself; a placeholder in the label
    (e.g. "{{cat:valve_type=Strainer}} type") reads as the screen shows it when `fill` is given."""
    for cfg in configs if isinstance(configs, list) else [configs]:
        cfg = cfg or {}
        for defs in (((cfg.get("list_spec") or {}).get("attribute_definitions")) or [], cfg.get("attribute_definitions") or []):
            for d in defs:
                if isinstance(d, dict) and d.get("id") == attr and d.get("label"):
                    return fill(d["label"]) if fill is not None else d["label"]
    return _humanize(attr)


def describe(cfg, path, fill=None):
    """PURE. A plain sentence for one place that stops working (the dialog's line; the raw place is kept for the Admin fold).
    CAT-3 K5c: no code name - attribute keys read as their column heading, the category as its display name."""
    name = (cfg or {}).get("category_display") or _humanize((cfg or {}).get("category_id")) or "a category"
    if fill is not None and "{{" in name:
        name = fill(name)   # a placeholder in the category's display name reads as the screen shows it
    m = re.search(r"pricing\.families\.([^.]+)", path)
    if m and path.rstrip(".").endswith(m.group(0)):
        return "%s: the price rule for \"%s\" - its rows will show no SKU and must be priced by hand" % (name, m.group(1))
    m = re.search(r"attribute_definitions\[([^\]]+)\]\.values", path)
    if m:
        return "%s: the %s list offers it" % (name, attr_label(cfg, m.group(1), fill))
    m = re.search(r"attribute_definitions\[(\d+)\]\.note", path)
    if m:
        defs = ((cfg or {}).get("list_spec") or {}).get("attribute_definitions") or (cfg or {}).get("attribute_definitions") or []
        idx = int(m.group(1))
        d = defs[idx] if idx < len(defs) and isinstance(defs[idx], dict) else {}
        label = d.get("label")
        if isinstance(label, str) and label and fill is not None:
            label = fill(label)
        return "%s: the note the AI is given for %s" % (name, label or _humanize(d.get("id")) or "a question")
    for key, what in (("text_notes", "working note"), ("read_notes", "working note"), ("companion_items", "item it adds")):
        m = re.search(r"(.*\b%s\[\d+\])" % key, path)
        if m:
            entry = _get(cfg, m.group(1)) or {}
            if path.endswith(".rule_line"):
                what, field = "rules-page line", "rule_line"
            else:
                field = "line" if isinstance(entry, dict) and entry.get("line") else "rule_line"
            words = entry.get(field) if isinstance(entry, dict) else None
            if isinstance(words, str) and words and fill is not None:
                words = fill(words)   # a placeholder in the wording reads as the screen shows it
            return "%s: the %s \"%s\"" % (name, what, words) if isinstance(words, str) and words else "%s: a %s" % (name, what)
    if ".defaults." in path:
        return "%s: the default for %s" % (name, attr_label(cfg, path.split(".defaults.", 1)[1].split(".")[0], fill))
    if "sheet_shares" in path:
        return "%s: a sheet share part that points at this row" % name
    if "code_targets" in path:
        return "%s: a rule that picks this value by name" % name
    if path.startswith("extraction_defaults") or path.startswith("synonyms"):
        return "%s: what the AI is told to answer" % name
    return "%s: a setting that names it" % name


def problems_added(configs, before_items, after_items, discipline):
    """PURE. ([REFUSE lines new after], [INFO lines new after]) -- each {"config", "path", "message", "line"}."""
    by_id = {c.get("category_id"): c for c in configs if isinstance(c, dict)}
    built = catalogue_gate.build(before_items, configs)
    fill = lambda t: catalogue_lists.fill_text(t, built)   # noqa: E731
    before = {_key(p) for p in catalogue_gate.reference_problems(configs, before_items, discipline)}
    stop, also, seen = [], [], set()
    for p in catalogue_gate.reference_problems(configs, after_items, discipline):
        if _key(p) in before or _key(p) in seen:   # one line per place (a text naming it twice is one place)
            continue
        seen.add(_key(p))
        line = {"config": p["config"], "path": p["path"], "message": p["message"],
                "line": describe(by_id.get(p["config"]), p["path"] or "", fill)}
        (stop if p["severity"] == catalogue_gate.REFUSE else also).append(line)
    return stop, also


def _carried_values(items):
    out = set()
    for i in items:
        if i.get("active", 1):
            for k, v in catalogue_gate._attrs(i).items():
                if isinstance(v, (str, int, float)) and not isinstance(v, bool):
                    out.add((k, v))
    return out


def references_naming(configs, values, uid):
    """PURE. Every registry reference (path, attr, value) of the configs that names one of `values` ({(attr, value)}) or the item
    `uid` (a share part or a placeholder)."""
    by_id = {c.get("category_id"): c for c in configs if isinstance(c, dict)}
    out = []
    for cfg in configs:
        cid = cfg.get("category_id")
        for path, attr, value, _scope in catalogue_gate._value_refs(cfg, by_id):
            if (attr, value) in values:
                out.append((cid, path, attr, value))
        for path, attr, value, _scope, prob in catalogue_gate.code_target_refs(cfg, by_id):
            if not prob and (attr, value) in values:
                out.append((cid, path, attr, value))
        for path, sku in catalogue_gate.share_parts(cfg):
            if (uid and sku.get("item_uid") == uid) or (sku.get("attr"), sku.get("value")) in values:
                out.append((cid, path, sku.get("attr") or "item_uid", sku.get("value") or uid))
        for path, s in catalogue_gate._walk_strings(cfg, ""):
            for m in catalogue_gate.PLACEHOLDER_RE.finditer(s) if "{{" in s else ():
                body = m.group(2)
                if m.group(1) == "cat" and "=" in body:
                    a, v = body.split("|")[0].split("=", 1)
                    if (a.strip(), v) in values:
                        out.append((cid, path, a.strip(), v))
                elif m.group(1) in ("item", "note") and uid and body.split("|")[0].split(":")[0].strip() == uid:
                    out.append((cid, path, m.group(1), uid))
    return out


def usage(configs, items, row, proposed_values=None, discipline=None):
    """PURE. What happens to the discipline's references if `row` (an item dict from `items`) is DEACTIVATED (proposed_values
    None) or EDITED to `proposed_values` ({attr: new value}; brand / kind / unit may be given too).
    -> {"action", "will_stop": [...], "still_works": n, "also": [...], "labels": {...}, "last_carrier_of": [[attr, value], ...]}."""
    uid = (row.get("item_uid") or "").strip()
    name = row.get("name")
    others = [i for i in items if i is not row and not (name and i.get("name") == name)]
    if proposed_values is None:
        after = others
        action = "deactivate"
    else:
        changed = copy.deepcopy(row)
        attrs = dict(changed.get("attributes") or {})
        for k, v in proposed_values.items():
            if k in ("brand", "kind", "unit"):
                changed[k] = v
            else:
                attrs[k] = v
        changed["attributes"] = attrs
        after = others + [changed]
        action = "edit"
    stop, also = problems_added(configs, items, after, discipline)
    mine = {(k, v) for k, v in catalogue_gate._attrs(row).items() if isinstance(v, (str, int, float)) and not isinstance(v, bool)}
    left = _carried_values(after)
    last = sorted([list(x) for x in mine if x not in left], key=lambda x: (str(x[0]), str(x[1])))
    refs = references_naming(configs, mine, uid)
    stopped_paths = {(s["config"], s["path"]) for s in stop}
    still = sum(1 for (cid, path, _a, _v) in refs if (cid, path) not in stopped_paths)
    labels, _flags = catalogue_labels.labels_for(row.get("kind"), row.get("attributes") or {})
    return {"action": action, "will_stop": stop, "still_works": still, "also": also, "labels": labels, "last_carrier_of": last}


def values_no_row_will_carry(configs, items_before, items_after, discipline=None):
    """PURE. The CSV preview's list (R6): every (attr, value) some active row carries now and no row will carry after the
    upload, and what stops working because of it."""
    lost = sorted(_carried_values(items_before) - _carried_values(items_after), key=lambda x: (str(x[0]), str(x[1])))
    stop, _also = problems_added(configs, items_before, items_after, discipline) if lost else ([], [])
    # CAT-3 K5c: each value also carries its column heading (the preview shows "Item name: ...", never the key)
    built = catalogue_gate.build(items_before, configs) if lost else None
    fill = (lambda t: catalogue_lists.fill_text(t, built)) if built is not None else None   # noqa: E731
    return {"values": [[a, v, attr_label(configs, a, fill)] for (a, v) in lost], "will_stop": stop}


def read_discipline(discipline):
    """frappe read (no write): the discipline's active items (name, item_uid, kind, brand, unit, attributes) and active configs."""
    import frappe

    items = frappe.get_all("BoQ Rate Master Item", filters={"discipline": discipline, "active": 1},
                           fields=["name", "item_uid", "kind", "brand", "unit", "attributes", "item_notes"], order_by="name asc")
    for i in items:
        i["attributes"] = catalogue_lists._parse(i.get("attributes"), {})
        i["active"] = 1
    configs = []
    for r in frappe.get_all("BoQ Rate Category Config", filters={"discipline": discipline, "active": 1},
                            fields=["config"], order_by="category_id asc"):
        c = catalogue_lists._parse(r.get("config"), {})
        c.setdefault("discipline", discipline)
        configs.append(c)
    return items, configs


def timed(fn, *a, **kw):
    """(result, milliseconds)."""
    t = time.perf_counter()
    r = fn(*a, **kw)
    return r, round((time.perf_counter() - t) * 1000, 1)
