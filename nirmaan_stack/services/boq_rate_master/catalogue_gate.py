"""CAT-1 -- THE REFERENCE GATE and G-PROSE, split out of catalogue_lists.py (residence S1, the 500-line limit). PURE: no frappe here.
The import gate calls them through `config_validation.validate_catalogue_references` (beside `validate_delegated_sections`); the mint
build and the suite call them directly. The rebuild, the stamp, the merge and the fill they read are `catalogue_lists`.
"""
from __future__ import annotations

from nirmaan_stack.services.boq_rate_master.catalogue_lists import (  # noqa: F401  (the shared rule, read here)
    EXCLUDES_KEY, LINKED_DISCIPLINES, PLACEHOLDER_RE, UNSTOCKED_KEY, _attrs, _declared, build, config_kinds, declared_placeholders,
    index_items, resolve_placeholder,
)


# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# THE REFERENCE GATE (CAT-D0 D5 G1; CAT-D1 E6 G-REF). PURE. Called by `config_validation.validate_catalogue_references` from the
# import gate (both loader paths) -- so every mint, whose own load runs it, is gated too. Owner 2026-11-26 00:06 / 00:10: "a
# rate-file load is REFUSED if any reference names a missing item, with the place named".
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
REFUSE, INFO = "REFUSE", "INFO"

# THE DECLARED REFERENCE-KEY REGISTRY -- every config key that names a catalogue value or item, each checked by `_value_refs`,
# `_share_parts`, `_walk_inputs` or the placeholder walk below. A key outside this list is not a reference (wording, a number, a
# class-(b) answer). A NEW reference key joins here in the same change that adds it (test_catalogue_gate pins the list).
REFERENCE_KEYS = (
    "list_spec.pricing.defaults.<attr>.value",
    "list_spec.pricing.defaults.<attr>.by_family.<family>",
    "list_spec.pricing.value_map[].to / .families",
    "list_spec.pricing.derive_when_none[].then / .families / .when",
    "list_spec.pricing.override_when[].then / .families / .when",
    "list_spec.pricing.family_when_none.by_unit_class / .when_words[].family",
    "list_spec.pricing.families.<family>",
    "list_spec.pricing.families.<family>...steps[].conditions[].when",
    "list_spec.pricing.companion_items[].families / .item",
    "list_spec.pricing.text_notes[].families / .when",
    "list_spec.pricing.read_notes[].families",
    "list_spec.pricing.user_addable[].family",
    "list_spec.sections[].families (the delegated category's families)",
    "list_spec.pricing.sheet_shares.shares[].parts[].sku (an item: item_uid, or kind / attr / value)",
    "pipelines.<id>.steps[].conditions[].when",
    "extraction_defaults.<attr>",
    "synonyms.<attr>.<variant> (the canonical side)",
    "unstocked_answers.<attr> (must NOT be stocked)",
    "catalogue_excludes.<attr> (must be carried)",
    "<any>.input / <any>.*_input (a Pricing Input id)",
    "<any string> {{cat:...}} / {{item:...}} placeholders",
    "goldens / impact_examples (LISTED as INFO, never refused - owner 2026-11-26 00:53, QR-SCOPE-2)",
)


def _scalar(v):
    return isinstance(v, (str, int, float)) and not isinstance(v, bool)


def _carried(by_kind, kinds):
    """{attr: set(values)} over the active SKUs of `kinds`."""
    out = {}
    for k in kinds:
        for a in by_kind.get(k, []):
            for attr, v in a.items():
                if _scalar(v) and v != "":
                    out.setdefault(attr, set()).add(v)
    return out


def _families_of(cfg):
    ls = cfg.get("list_spec") if isinstance(cfg.get("list_spec"), dict) else {}
    return ls.get("family_attribute_id")


def _walk_strings(node, path):
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _walk_strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_strings(v, f"{path}[{i}]")


# A Pricing Input reference under one of these paths names a FAMILY of inputs by its shared prefix (VRF extras: the band's
# `input` "vrf_extra_pipe_indoor_upto_4tr" is read as "..._supply_mm" / "..._return_mm" / "..._insulation_mm"), so it must be the
# prefix of at least one active id; everywhere else the value must BE an active id. Keys under `labels` are wording.
PREFIX_INPUT_PATHS = (".pipe_bands.", ".power_bands.", ".comm_input")


def _walk_inputs(node, path):
    """(path, id) for every `input` / `*_input` key holding a string -- a Pricing Input reference (wording under `labels` is
    not one)."""
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else str(k)
            if k == "labels":
                continue
            if isinstance(v, str) and (k == "input" or k.endswith("_input")):
                yield p, v
            else:
                yield from _walk_inputs(v, p)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_inputs(v, f"{path}[{i}]")


def _walk_conditions(node, path):
    """(path, {attr: value}) for every `conditions[].when` dict of a pipeline step."""
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}" if path else str(k)
            if k == "conditions" and isinstance(v, list):
                for i, c in enumerate(v):
                    if isinstance(c, dict) and isinstance(c.get("when"), dict):
                        yield f"{p}[{i}].when", c["when"]
            yield from _walk_conditions(v, p)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_conditions(v, f"{path}[{i}]")


def _value_refs(cfg, configs_by_id):
    """(path, attr, value, scope_cfg) for every registry value reference of one config; `scope_cfg` = the config whose kinds
    must carry the value (the config itself, or a delegated section's category)."""
    ls = cfg.get("list_spec") if isinstance(cfg.get("list_spec"), dict) else {}
    p = ls.get("pricing") if isinstance(ls.get("pricing"), dict) else {}
    fam = ls.get("family_attribute_id")
    base = "list_spec.pricing"
    out = []
    for attr, spec in (p.get("defaults") or {}).items():
        if not isinstance(spec, dict):
            continue
        if _scalar(spec.get("value")):
            out.append((f"{base}.defaults.{attr}.value", attr, spec["value"], cfg))
        for f, v in (spec.get("by_family") or {}).items():
            if fam:
                out.append((f"{base}.defaults.{attr}.by_family (key)", fam, f, cfg))
            if _scalar(v):
                out.append((f"{base}.defaults.{attr}.by_family.{f}", attr, v, cfg))
    for key in ("value_map", "derive_when_none", "override_when"):
        for i, m in enumerate(p.get(key) or []):
            if not isinstance(m, dict):
                continue
            tgt = "to" if key == "value_map" else "then"
            if m.get("attr") and _scalar(m.get(tgt)):
                out.append((f"{base}.{key}[{i}].{tgt}", m["attr"], m[tgt], cfg))
            for f in m.get("families") or []:
                if fam:
                    out.append((f"{base}.{key}[{i}].families", fam, f, cfg))
            w = m.get("when")
            if isinstance(w, dict) and w.get("attr") and isinstance(w.get("equals"), str):
                out.append((f"{base}.{key}[{i}].when", w["attr"], w["equals"], cfg))
    fwn = p.get("family_when_none") if isinstance(p.get("family_when_none"), dict) else {}
    if fam:
        for uc, f in (fwn.get("by_unit_class") or {}).items():
            out.append((f"{base}.family_when_none.by_unit_class.{uc}", fam, f, cfg))
        for i, w in enumerate(fwn.get("when_words") or []):
            if isinstance(w, dict) and w.get("family"):
                out.append((f"{base}.family_when_none.when_words[{i}].family", fam, w["family"], cfg))
        for f in (p.get("families") or {}):
            out.append((f"{base}.families.{f}", fam, f, cfg))
        for key in ("text_notes", "read_notes", "companion_items"):
            for i, n in enumerate(p.get(key) or []):
                if not isinstance(n, dict):
                    continue
                for f in n.get("families") or []:
                    out.append((f"{base}.{key}[{i}].families", fam, f, cfg))
                w = n.get("when")
                if isinstance(w, dict) and w.get("attr") and isinstance(w.get("equals"), str):
                    out.append((f"{base}.{key}[{i}].when", w["attr"], w["equals"], cfg))
                if key == "companion_items" and isinstance(n.get("item"), dict):
                    for a, v in n["item"].items():
                        if _scalar(v):
                            out.append((f"{base}.companion_items[{i}].item.{a}", fam if a == "family" else a, v, cfg))
        # a user-addable family is a delegated section's family (VAV Box: the DP sensor is a Sensors SKU)
        targets = [configs_by_id.get(s.get("category_id")) for s in (ls.get("sections") or []) if isinstance(s, dict)]
        for i, u in enumerate(p.get("user_addable") or []):
            if isinstance(u, dict) and u.get("family"):
                owner = next((t for t in targets if t and u["family"] in (((t.get("list_spec") or {}).get("pricing") or {})
                                                                          .get("families") or {})), cfg)
                out.append((f"{base}.user_addable[{i}].family", _families_of(owner) or fam, u["family"], owner))
    for i, s in enumerate(ls.get("sections") or []):
        if not isinstance(s, dict) or not s.get("category_id"):
            continue
        tgt = configs_by_id.get(s["category_id"])
        tfam = _families_of(tgt) if tgt else None
        for f in s.get("families") or []:
            if tgt is not None and tfam:
                out.append((f"list_spec.sections[{i}].families", tfam, f, tgt))
    for path, when in list(_walk_conditions(p.get("families") or {}, f"{base}.families")) + \
            list(_walk_conditions(cfg.get("pipelines") or {}, "pipelines")):
        for a, v in when.items():
            if _scalar(v):
                out.append((f"{path}.{a}", a, v, cfg))
    for a, v in (cfg.get("extraction_defaults") or {}).items():
        d = v.get("default") if isinstance(v, dict) else v
        if isinstance(d, str):
            out.append((f"extraction_defaults.{a}", a, d, cfg))
    for a, m in (cfg.get("synonyms") or {}).items():
        for variant, canonical in (m or {}).items():
            if isinstance(canonical, str):
                out.append((f"synonyms.{a}.{variant}", a, canonical, cfg))
    return out


def share_parts(cfg):
    """(path, sku) for every VAV-style sheet-share part of one config."""
    ls = cfg.get("list_spec") if isinstance(cfg.get("list_spec"), dict) else {}
    ss = (ls.get("pricing") or {}).get("sheet_shares")
    if not isinstance(ss, dict):
        return
    for si, s in enumerate(ss.get("shares") or []):
        for pi, part in enumerate((s or {}).get("parts") or []):
            if isinstance(part, dict) and isinstance(part.get("sku"), dict):
                yield f"list_spec.pricing.sheet_shares.shares[{si}].parts[{pi}].sku", part["sku"]


def resolve_share_sku(items, sku):
    """The active SKUs a share part's `sku` points at: {item_uid} -> by id (the name read live); {kind, attr, value} -> typed."""
    if sku.get("item_uid"):
        return [i for i in items if i.get("active", 1) and (i.get("item_uid") or "").strip() == sku["item_uid"]]
    return [i for i in items if i.get("active", 1) and i.get("kind") == sku.get("kind")
            and (i.get("attributes") or {}).get(sku.get("attr")) == sku.get("value")]


def reference_problems(configs, items, discipline=None, linked=None):
    """THE GATE -> [{"severity", "config", "path", "message"}] over `configs` (dicts) against the active `items` (dicts: the
    catalogue as it will stand). REFUSE lines refuse the import; INFO lines are listed. G1 (R1 - R4) runs for the linked
    disciplines (the lists merge only there); G-REF runs for every discipline."""
    linked = LINKED_DISCIPLINES if linked is None else linked
    by_kind = index_items(items)
    by_id = {c.get("category_id"): c for c in configs if isinstance(c, dict)}
    built = build(items, configs)
    pi_ids = {(i.get("attributes") or {}).get("item") for i in items
              if i.get("active", 1) and str(i.get("kind") or "").endswith("_pricing_input")}
    out = []

    def add(sev, cfg, path, msg):
        out.append({"severity": sev, "config": cfg.get("category_id"), "path": path, "message": msg})

    for cfg in configs:
        if not isinstance(cfg, dict):
            continue
        disc = discipline or cfg.get("discipline")
        kinds = config_kinds(cfg, by_kind)
        own = _carried(by_kind, kinds)
        # -- G1 (linked disciplines): every class-(a) list against the catalogue --
        if disc in linked:
            rb = built["lists"].get(cfg.get("category_id")) or {}
            ls = cfg.get("list_spec") if isinstance(cfg.get("list_spec"), dict) else None
            defs = (ls or {}).get("attribute_definitions") if ls else cfg.get("attribute_definitions")
            dpath = "list_spec.attribute_definitions" if ls else "attribute_definitions"
            for d in defs or []:
                r = rb.get(d.get("id")) if isinstance(d, dict) else None
                if not r or r["klass"] not in ("A-FAMILY", "A-ATTRIBUTE"):
                    continue
                q = d["id"]
                keep = declared_placeholders(cfg, q)
                stocked = own.get(q, set())
                lists = [(f"{dpath}[{q}].values", list(d.get("values") or []))]
                if isinstance(d.get("values_by_family"), dict):
                    lists += [(f"{dpath}[{q}].values_by_family.{f}", list(fv)) for f, fv in d["values_by_family"].items()]
                for path, vals in lists:
                    for v in vals:
                        if v not in stocked and v not in keep:          # R1
                            add(REFUSE, cfg, path, f"offers {q} = '{v}' - no active SKU stocks it and no declaration names it "
                                                   f"(declare it in {UNSTOCKED_KEY} if it is a deliberate refusal)")
                if not any(v in stocked for _p, vals in lists[:1] for v in vals):   # R3: the config's own list
                    add(REFUSE, cfg, f"{dpath}[{q}].values", f"question {q}: no value its list offers is stocked")
                for v in r["values"]:                                   # R4
                    if v not in (d.get("values") or []) and v not in keep:
                        add(INFO, cfg, f"{dpath}[{q}].values",
                            f"a SKU stocks {q} = '{v}', which the config list does not name (offered from the catalogue)")
        # -- the declarations (R2) --
        for q, vals in _declared(cfg, UNSTOCKED_KEY).items():
            for v in vals:
                if v in own.get(q, set()):
                    add(REFUSE, cfg, f"{UNSTOCKED_KEY}.{q}", f"declares {q} = '{v}' as not stocked, but an active SKU stocks it")
        for q, vals in _declared(cfg, EXCLUDES_KEY).items():
            for v in vals:
                if v not in own.get(q, set()):
                    add(REFUSE, cfg, f"{EXCLUDES_KEY}.{q}", f"excludes {q} = '{v}', which no active SKU carries")
        # -- G-REF: value references --
        for path, attr, value, scope in _value_refs(cfg, by_id):
            carried = own if scope is cfg else _carried(by_kind, config_kinds(scope, by_kind))
            if attr not in carried:
                continue    # not a SKU attribute of these kinds: a class-(b) answer, not a catalogue reference
            if value in carried[attr] or value in declared_placeholders(scope, attr):
                continue
            add(REFUSE, cfg, path, f"names {attr} = '{value}' - no active SKU carries it")
        # -- G-REF: item references (share parts) --
        for path, sku in share_parts(cfg):
            if resolve_share_sku(items, sku):
                continue
            if sku.get("item_uid"):
                add(REFUSE, cfg, path, f"points at item {sku['item_uid']} (last known name '{sku.get('name', '?')}') - "
                                       f"no active SKU has that id")
            else:
                add(REFUSE, cfg, path, f"names {sku.get('attr')} = '{sku.get('value')}' ({sku.get('kind')}) - "
                                       f"no active SKU carries it")
        # -- G-REF: Pricing Input ids --
        for path, pid in _walk_inputs(cfg, ""):
            if any(x in path for x in PREFIX_INPUT_PATHS):
                if not any(isinstance(i, str) and i.startswith(pid + "_") for i in pi_ids):
                    add(REFUSE, cfg, path, f"names Pricing Inputs '{pid}_...' - no active Pricing Input id starts with it")
                continue
            if pid not in pi_ids:
                add(REFUSE, cfg, path, f"names Pricing Input '{pid}' - no active Pricing Input has that id")
        # -- G-REF: placeholders --
        for path, s in _walk_strings(cfg, ""):
            if "{{" in s:
                for m in PLACEHOLDER_RE.finditer(s):
                    _t, prob = resolve_placeholder(m.group(1), m.group(2), built)
                    if prob:
                        add(REFUSE, cfg, path, prob)
        # -- goldens / impact_examples: LISTED only (QR-SCOPE-2) --
        for key in ("goldens", "impact_examples"):
            for path, s in _walk_strings(cfg.get(key) or [], key):
                attr = path.rsplit(".", 1)[-1]
                if attr in own and s not in own[attr] and s not in declared_placeholders(cfg, attr):
                    add(INFO, cfg, path, f"a pinned case names {attr} = '{s}', which no active SKU carries (listed, not refused)")
    return out


def format_problem(p):
    return f"{p['severity']}: {p['config']} > {p['path']} {p['message']}"


# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
# G-PROSE (CAT-D1 E9; owner 2026-11-26 01:47 QR-C-1 (a)): config WORDING that names a multi-word catalogue value outside a
# placeholder. Today's mentions stay typed (CAT-1b converts them) and are frozen by path in PROSE_ALLOWLIST at today's count, which
# only goes down; a NEW mention is listed by the import gate (INFO) and fails the suite (test_catalogue_guards). A string that IS a
# value (a list entry, a default) is a reference, checked by the gate, not prose.
# ══════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
PROSE_ALLOWLIST = "catalogue_prose_allowlist.json"   # beside this module


def prose_mentions(configs, items):
    """{"<category_id> > <path>": {value: count}} -- multi-word catalogue values named INSIDE a longer config string (after the
    placeholders are taken out), the longer value winning its span; goldens / impact_examples (pinned cases) left out."""
    vals = set()
    for i in items:
        if not i.get("active", 1) or str(i.get("kind") or "").endswith("_pricing_input"):
            continue
        for k, v in _attrs(i).items():
            if isinstance(v, str) and " " in v.strip() and len(v.strip()) >= 6 and k not in ("name", "remarks", "shared_by"):
                vals.add(v.strip())
    ordered = sorted(vals, key=lambda x: (-len(x), x))
    out = {}
    for cfg in configs:
        if not isinstance(cfg, dict):
            continue
        for path, s in _walk_strings({k: v for k, v in cfg.items() if k not in ("goldens", "impact_examples")}, ""):
            t = PLACEHOLDER_RE.sub(" ", s)
            if t.strip() in vals or " " not in t:
                continue
            low, used, hits = t.lower(), [], {}
            for v in ordered:
                start = low.find(v.lower())
                while start >= 0:
                    end = start + len(v)
                    before_ok = start == 0 or not low[start - 1].isalnum()
                    after_ok = end == len(low) or not low[end].isalnum()
                    if before_ok and after_ok and not any(start >= a and end <= b for a, b in used):
                        used.append((start, end))
                        hits[v] = hits.get(v, 0) + 1
                    start = low.find(v.lower(), start + 1)
            if hits:
                out[f"{cfg.get('category_id')} > {path}"] = hits
    return out


def prose_drift(found, frozen):
    """G-PROSE drift: each (path, value) above / below its frozen count."""
    lines = []
    for path in sorted(set(found) | set(frozen)):
        a, b = found.get(path, {}), frozen.get(path, {})
        for v in sorted(set(a) | set(b)):
            now, was = a.get(v, 0), (b.get(v) or {}).get("count", 0) if isinstance(b.get(v), dict) else b.get(v, 0)
            if now != was:
                lines.append(f"{path}: '{v}' named {now} time(s), {was} frozen"
                             + (" (a new mention: write it as {{cat:<attr>=<value>}})" if now > was else " (fewer: lower its count)"))
    return lines
