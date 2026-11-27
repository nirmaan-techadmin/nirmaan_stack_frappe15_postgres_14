"""CAT-1 -- THE CATALOGUE LISTS: every catalogue choice list REBUILT from the live catalogue, stored with a STAMP, and
merged into the config at the two config read points.

THE OWNER'S WORDS (2026-11-24 18:42 - 19:38, the capture): attribute choices come from the catalogue; adding or removing an
item reflects in the AI's allowed values, the matcher and the drop-downs; the lists are REBUILT whenever the catalogue changes
by any route and stored with a stamp; before each request the stamp is checked and the lists rebuilt first if stale. And
(2026-11-26 00:06 / 00:10): item names inside wording are FILLED from the catalogue at each request and each screen.

WHAT THIS MODULE IS (design: CAT-D0 D1 / D3, CAT-D1 E5 / E10 -- `BoQ main lane\\CAT-D0\\`, `\\CAT-D1\\`):

  * THE RULE (`classify_and_rebuild`). For every choice question of a config, in order, the first that fits:
      A-FAMILY    an item-list config's family question -> the config's rule families that >= 1 active SKU of its kinds carries;
      A-DERIVED   a question with `values_from` -> untouched (it already reads the live catalogue at request time);
      A-IDENTITY  the item-identity attribute -> untouched (same);
      A-ATTRIBUTE a SKU attribute of the config's kinds -> the distinct values those SKUs carry (per family where the
                  question has `values_by_family`), minus the config's declared `catalogue_excludes`;
      B           anything else -> the config list, untouched.
    MEMBERSHIP comes from the catalogue; ORDER and PLACEHOLDERS from the config (`_order`): the config list's own order for every
    value that survives, new catalogue values inserted sorted case-folded before the list's trailing placeholders, and a value no
    SKU stocks kept ONLY where the config declares it (`no_sku_families`, `family_alias` keys, `family_alias_offered`,
    `value_map` `from`, and the new `unstocked_answers` {question: [values]}). A value is NEVER stripped (Insulation's leading
    space survives).

  * THE STAMP (`compute_stamp`): sha256 over every active item's (kind, brand, unit, attributes), canonical and sorted, plus
    every active config of the discipline. NOT rates, item_uid, name, modified, import_batch, source -- so a rate edit or the
    derived-rate recompute's same-content re-insert does not move it, and a raw-SQL attribute edit or a config reorder does.

  * THE STORE: the Frappe cache, key `catalogue_lists:<discipline>` = the built dict {stamp, lists, names, values}. A missing or
    stale stamp rebuilds in memory, serves, and re-caches. Lost on a cache flush -> the next read rebuilds (~50 ms).

  * REBUILT at the two choke points every app write route passes (`rebuild_after_write`): the loader's end and
    `loader.recompute_derived_after_write`. The cache is written AFTER the transaction commits (a rolled-back write never
    leaves a stamp of content that does not exist). Desk, console, raw SQL and restores are caught by the stamp check.

  * MERGED at the two read points through ONE helper (`serve_config` / `serve_configs`): `extraction._load_active_configs`
    (every Suggest request, `_group_context`, the mints' request proofs; the stamp is checked on every call) and
    `rate_master.get_rate_category_config` (panel, Calculator, Rate Master, rules page, the server pricing step; checked at
    most once a minute per worker). The exporter keeps reading the RAW config, so nothing derived is ever exported.

  * THE PLACEHOLDER FILL (`fill_text`): `{{cat:<attr>=<value>}}` (the exact value; `|lower`, `|trim`) and
    `{{item:<item_uid>}}` / `{{item:<item_uid>:<attr>}}` (the SKU's name, read live). Filled in the same merge at both read
    points. A placeholder that cannot resolve is REFUSED at load (`catalogue_gate.reference_problems`); if the catalogue
    changes after the load by a route that has no gate (Desk / console), the fill prints the value as written (never braces)
    and an item reference prints `UNRESOLVED_ITEM_TEXT`.

SCOPE IN THIS SLICE (owner 2026-11-26 01:16 "yes proceed", the order R8): the LISTS are merged for `LINKED_DISCIPLINES` only
(HVAC). Electrical joins after the BCS merge (CAT-3): its colour list needs a `catalogue_excludes` declaration that only an
Electrical rate file can carry, and no Electrical file is minted here. The FILL applies to every discipline (a no-op on a
config without placeholders).

PURE functions take plain dicts; only `_read`, `current`, `rebuild_after_write`, `serve_config(s)` touch frappe.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time

import frappe

ITEM_DOCTYPE = "BoQ Rate Master Item"
CONFIG_DOCTYPE = "BoQ Rate Category Config"
CACHE_PREFIX = "catalogue_lists:"
LIST_MODE = "item_list"
LINKED_DISCIPLINES = ("HVAC",)
# the served path checks the stamp at most once per this many seconds per worker (CAT-D0 D3: 40 ms per check, called once per
# category on a page load); the request path (`fresh=True`) checks on every call
SERVED_CHECK_SECONDS = 60
UNRESOLVED_ITEM_TEXT = "an item no longer in the catalogue"
# config keys that DECLARE a value no SKU stocks (kept) or a SKU value never offered (dropped) -- per question id
UNSTOCKED_KEY = "unstocked_answers"
EXCLUDES_KEY = "catalogue_excludes"
# the item attribute a SKU's display name is read from, first present wins
NAME_ATTRS = ("item", "item_name", "description")

PLACEHOLDER_RE = re.compile(r"\{\{(cat|item):([^{}]*)\}\}")

_MEMO: dict = {}   # {discipline: (monotonic_time, built)} -- the per-worker served-path memo


# ── canonical form + stamp (PURE) ───────────────────────────────────────────────────────────────────────────────────
def canon(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)


def compute_stamp(items, configs):
    """sha256 (first 16 hex) over the active items' (kind, brand, unit, attributes) and the configs, each canonical, sorted."""
    ip = hashlib.sha256("\n".join(sorted(
        canon([i.get("kind"), i.get("brand"), i.get("unit"), i.get("attributes") or {}])
        for i in items if i.get("active", 1))).encode("utf-8")).hexdigest()
    cp = hashlib.sha256("\n".join(sorted(canon(c) for c in configs)).encode("utf-8")).hexdigest()
    return hashlib.sha256((ip + cp).encode("utf-8")).hexdigest()[:16]


from nirmaan_stack.services.boq_rate_master.catalogue_values import (  # noqa: E402,F401  (CAT-3; split for S1)
    category_item_values, rate_master_kinds,
)

# ── the rule (PURE) ─────────────────────────────────────────────────────────────────────────────────────────────────
def _attrs(i):
    a = dict(i.get("attributes") or {})
    b = i.get("brand")
    if isinstance(b, str):
        b = b.strip()
    if b not in (None, "") and "brand" not in a:
        a["brand"] = b
    return a


def _kinds_named(node, out):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "kind" and isinstance(v, str):
                out.add(v)
            elif k in ("extra_kinds", "item_kinds") and isinstance(v, list):
                out |= {x for x in v if isinstance(x, str)}
            else:
                _kinds_named(v, out)
    elif isinstance(node, list):
        for x in node:
            _kinds_named(x, out)
    return out


def config_kinds(cfg, by_kind):
    ls = cfg.get("list_spec") if isinstance(cfg.get("list_spec"), dict) else None
    if ls:
        p = ls.get("pricing") or {}
        return [k for k in [p.get("kind")] + list(p.get("extra_kinds") or []) if k]
    return [k for k in (cfg.get("item_kinds") or []) if k in by_kind]


def _declared(cfg, key):
    d = cfg.get(key)
    return d if isinstance(d, dict) else {}


def declared_placeholders(cfg, qid):
    """The values the config DECLARES as offered although no SKU stocks them, for one question."""
    ls = cfg.get("list_spec") if isinstance(cfg.get("list_spec"), dict) else {}
    p = ls.get("pricing") or {}
    s = set()
    if qid == ls.get("family_attribute_id"):
        s |= set(p.get("no_sku_families") or []) | set((p.get("family_alias") or {}).keys()) | set(p.get("family_alias_offered") or [])
    for m in p.get("value_map") or []:
        if isinstance(m, dict) and m.get("attr") == qid and m.get("from"):
            s.add(m["from"])
    s |= set(_declared(cfg, UNSTOCKED_KEY).get(qid) or [])
    return s


def _order(config_vals, members, keep):
    """The config list's order for surviving values; the catalogue's new values sorted case-folded, inserted before the list's
    trailing declared placeholders."""
    kept = [v for v in config_vals if v in members or v in keep]
    new = sorted((v for v in members if v not in config_vals), key=lambda x: str(x).casefold())
    k = len(kept)
    while k > 0 and kept[k - 1] in keep and kept[k - 1] not in members:
        k -= 1
    return kept[:k] + new + kept[k:]


def index_items(items):
    by_kind = {}
    for i in items:
        if i.get("active", 1):
            by_kind.setdefault(i.get("kind"), []).append(_attrs(i))
    return by_kind


def classify_and_rebuild(cfg, by_kind):
    """{qid: {"klass", "values"?, "by_family"?}} for one config, from the active SKUs grouped by kind."""
    ls = cfg.get("list_spec") if isinstance(cfg.get("list_spec"), dict) else None
    defs = (ls or {}).get("attribute_definitions") if ls else cfg.get("attribute_definitions")
    kinds = config_kinds(cfg, by_kind)
    fam_attr = (ls or {}).get("family_attribute_id")
    rule_fams = list((((ls or {}).get("pricing") or {}).get("families") or {}).keys())
    ident = cfg.get("identity_attribute_id") if cfg.get("matching_mode") == "item_identity" else None
    excludes = _declared(cfg, EXCLUDES_KEY)
    out = {}
    for d in defs or []:
        if not isinstance(d, dict) or d.get("type") not in ("choice", "number_choice"):
            continue
        q = d.get("id")
        cvals = list(d.get("values") or [])
        keep = declared_placeholders(cfg, q)
        if d.get("values_from"):
            out[q] = {"klass": "A-DERIVED"}
            continue
        if ident and q == ident:
            out[q] = {"klass": "A-IDENTITY"}
            continue
        if ls and q == fam_attr:
            stocked = {a.get(q) for k in kinds for a in by_kind.get(k, []) if a.get(q) not in (None, "")}
            members = [f for f in rule_fams if f in stocked]
            out[q] = {"klass": "A-FAMILY", "values": _order(cvals, members, keep)}
            continue
        carriers = [a for k in kinds for a in by_kind.get(k, []) if a.get(q) not in (None, "")]
        if not carriers and not ls:
            named = _kinds_named(cfg, set()) & set(by_kind)
            carriers = [a for k in sorted(named) if not str(k).endswith("_pricing_input")
                        for a in by_kind[k] if a.get(q) not in (None, "")]
        if not carriers:
            out[q] = {"klass": "B"}
            continue
        ex = set(excludes.get(q) or [])
        members = list(dict.fromkeys(a[q] for a in carriers if a[q] not in ex))
        r = {"klass": "A-ATTRIBUTE"}
        vbf = d.get("values_by_family") if isinstance(d.get("values_by_family"), dict) else None
        if vbf and fam_attr:
            r["by_family"] = {}
            for fam, fv in vbf.items():
                fm = list(dict.fromkeys(a[q] for a in carriers if a.get(fam_attr) == fam and a[q] not in ex))
                r["by_family"][fam] = _order(list(fv), fm, keep)
        r["values"] = _order(cvals, members, keep)
        out[q] = r
    return out


def build(items, configs, stamp=None):
    """The built store for one discipline: {stamp, lists {category_id: {qid: rebuilt}}, names {item_uid: name}, values
    {attr: [values carried]}, item_values {category_id: {attr: [values its grid's items carry]}}}. `configs` = the
    discipline's active config dicts."""
    by_kind = index_items(items)
    lists, item_values = {}, {}
    for cfg in configs:
        cid = cfg.get("category_id")
        if cid:
            lists[cid] = classify_and_rebuild(cfg, by_kind)
            item_values[cid] = category_item_values(cfg, by_kind)
    names, values = {}, {}
    for i in items:
        if not i.get("active", 1):
            continue
        a = _attrs(i)
        uid = (i.get("item_uid") or "").strip()
        if uid:
            names[uid] = {k: v for k, v in a.items() if isinstance(v, (str, int, float)) and not isinstance(v, bool)}
        for k, v in a.items():
            if isinstance(v, (str, int, float)) and not isinstance(v, bool) and v not in ("", None):
                values.setdefault(k, set()).add(v)
    return {"stamp": stamp or compute_stamp(items, configs), "lists": lists, "names": names,
            "values": {k: sorted(v, key=lambda x: (str(type(x)), str(x))) for k, v in values.items()},
            "item_values": item_values}


# ── the merge + the fill (PURE) ─────────────────────────────────────────────────────────────────────────────────────
def merge_lists(cfg, rebuilt):
    """A config with every class-(a) FIXED list replaced by its rebuilt list. Returns `cfg` ITSELF when nothing differs (so a
    served object is byte-identical to the stored one), else a deep copy with only the changed lists replaced in place (key
    order kept)."""
    if not rebuilt:
        return cfg
    ls = cfg.get("list_spec") if isinstance(cfg.get("list_spec"), dict) else None
    defs = (ls or {}).get("attribute_definitions") if ls else cfg.get("attribute_definitions")
    changes = []
    for idx, d in enumerate(defs or []):
        if not isinstance(d, dict):
            continue
        r = rebuilt.get(d.get("id"))
        if not r or r.get("klass") not in ("A-FAMILY", "A-ATTRIBUTE"):
            continue
        if list(d.get("values") or []) != r["values"] and ("values" in d or r["values"]):
            changes.append((idx, "values", r["values"]))
        if r.get("by_family") is not None and isinstance(d.get("values_by_family"), dict):
            vbf = {k: list(v) for k, v in d["values_by_family"].items()}
            if vbf != r["by_family"]:
                changes.append((idx, "values_by_family", r["by_family"]))
    if not changes:
        return cfg
    c = copy.deepcopy(cfg)
    cdefs = c["list_spec"]["attribute_definitions"] if ls else c["attribute_definitions"]
    for idx, key, val in changes:
        cdefs[idx][key] = copy.deepcopy(val)
    return c


def item_name(names, uid, attr=None):
    a = names.get(uid)
    if a is None:
        return None
    if attr:
        v = a.get(attr)
        return None if v in (None, "") else str(v)
    for k in NAME_ATTRS:
        v = a.get(k)
        if v not in (None, ""):
            return str(v)
    return None


def parse_placeholder(kind, body):
    """-> ("cat", attr, value, mods) | ("item", uid, attr|None, mods) | None (malformed)."""
    parts = body.split("|")
    head, mods = parts[0], [m.strip() for m in parts[1:]]
    if any(m not in ("lower", "trim") for m in mods):
        return None
    if kind == "cat":
        if "=" not in head:
            return None
        attr, value = head.split("=", 1)
        if not attr.strip():
            return None
        return ("cat", attr.strip(), value, mods)
    bits = head.split(":")
    uid = bits[0].strip()
    if not uid or len(bits) > 2:
        return None
    return ("item", uid, bits[1].strip() if len(bits) == 2 and bits[1].strip() else None, mods)


def _apply_mods(s, mods):
    for m in mods:
        s = s.lower() if m == "lower" else s.strip()
    return s


def resolve_placeholder(kind, body, built):
    """-> (text, problem|None). `problem` names why it does not resolve (the load refuses on it)."""
    p = parse_placeholder(kind, body)
    if p is None:
        return body, f"malformed placeholder '{{{{{kind}:{body}}}}}'"
    if p[0] == "cat":
        _, attr, value, mods = p
        if value not in set((built.get("values") or {}).get(attr) or ()):
            return _apply_mods(value, mods), f"names {attr} = '{value}' - no active SKU carries it"
        return _apply_mods(value, mods), None
    _, uid, attr, mods = p
    name = item_name(built.get("names") or {}, uid, attr)
    if name is None:
        return UNRESOLVED_ITEM_TEXT, f"points at item {uid}" + (f" ({attr})" if attr else "") + " - no active SKU has that id"
    return _apply_mods(name, mods), None


def fill_text(s, built, problems=None, where=""):
    if "{{" not in s:
        return s

    def sub(m):
        text, prob = resolve_placeholder(m.group(1), m.group(2), built)
        if prob and problems is not None:
            problems.append((where, prob))
        return text
    return PLACEHOLDER_RE.sub(sub, s)


def has_placeholder(node):
    if isinstance(node, str):
        return "{{" in node and PLACEHOLDER_RE.search(node) is not None
    if isinstance(node, dict):
        return any(has_placeholder(v) for v in node.values())
    if isinstance(node, list):
        return any(has_placeholder(v) for v in node)
    return False


def fill_node(node, built, problems=None, where=""):
    """A COPY of `node` with every placeholder in every string VALUE filled (keys are never placeholders)."""
    if isinstance(node, str):
        return fill_text(node, built, problems, where)
    if isinstance(node, dict):
        return {k: fill_node(v, built, problems, f"{where}.{k}" if where else str(k)) for k, v in node.items()}
    if isinstance(node, list):
        return [fill_node(v, built, problems, f"{where}[{i}]") for i, v in enumerate(node)]
    return node


def merge_config(cfg, built, discipline):
    """THE ONE MERGE: the rebuilt lists (linked disciplines) then the placeholder fill. Returns `cfg` itself when neither
    changes anything."""
    if not isinstance(cfg, dict):
        return cfg
    out = cfg
    if discipline in LINKED_DISCIPLINES:
        out = merge_lists(cfg, (built.get("lists") or {}).get(cfg.get("category_id")))
    if has_placeholder(out):
        out = fill_node(out, built)
    return out


# ── frappe: read, store, serve ──────────────────────────────────────────────────────────────────────────────────────
def _parse(v, default):
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v or "null") or default
    except (TypeError, ValueError):
        return default


def _read(discipline):
    items = frappe.get_all(ITEM_DOCTYPE, filters={"discipline": discipline, "active": 1},
                           fields=["kind", "brand", "unit", "attributes", "item_uid"], order_by="name asc")
    for i in items:
        i["attributes"] = _parse(i.get("attributes"), {})
        i["active"] = 1
    configs = [_parse(r.get("config"), {}) for r in frappe.get_all(
        CONFIG_DOCTYPE, filters={"discipline": discipline, "active": 1}, fields=["config"], order_by="category_id asc")]
    return items, configs


def cache_key(discipline):
    return CACHE_PREFIX + discipline


def current(discipline, fresh=True):
    """The built store for `discipline`, guaranteed current: `fresh` checks the stamp now; otherwise at most once per
    SERVED_CHECK_SECONDS per worker. A missing / stale cache entry is rebuilt and re-cached."""
    now = time.monotonic()
    memo = _MEMO.get(discipline)
    if not fresh and memo and now - memo[0] < SERVED_CHECK_SECONDS:
        return memo[1]
    items, configs = _read(discipline)
    stamp = compute_stamp(items, configs)
    cached = frappe.cache().get_value(cache_key(discipline))
    # CAT-3: a store cached before `item_values` existed is rebuilt once (same stamp, one more key)
    if isinstance(cached, dict) and cached.get("stamp") == stamp and "item_values" in cached:
        built = cached
    else:
        built = build(items, configs, stamp)
        frappe.cache().set_value(cache_key(discipline), built)
    _MEMO[discipline] = (now, built)
    return built


def rebuild_after_write(discipline):
    """Called at the two choke points (the loader's end, `recompute_derived_after_write`), inside the writer's transaction:
    rebuilds from the catalogue as the transaction now sees it, clears this worker's memo, and writes the cache when the
    transaction COMMITS (never for a rolled-back write). Returns the new stamp."""
    items, configs = _read(discipline)
    built = build(items, configs)
    _MEMO.pop(discipline, None)

    def _store():
        frappe.cache().set_value(cache_key(discipline), built)
        _MEMO.pop(discipline, None)
    after = getattr(getattr(frappe, "db", None), "after_commit", None)
    if after is not None and hasattr(after, "add"):
        after.add(_store)
    else:   # pragma: no cover - every supported frappe has after_commit
        _store()
    return built["stamp"]


def serve_config(discipline, cfg, fresh=False):
    """THE served-config helper (`get_rate_category_config`). Runs LAST on the served object -- a later role-based filter
    (the BCS lane's cost withholding) belongs before it."""
    if not isinstance(cfg, dict) or not discipline:
        return cfg
    if discipline not in LINKED_DISCIPLINES and not has_placeholder(cfg):
        return cfg
    return merge_config(cfg, current(discipline, fresh=fresh), discipline)


def served_item_values(discipline, category_id, fresh=False):
    """CAT-3 (R7, QR-C-P2 (a)): the `item_values` served beside one category's config -- from the same cached store the
    config merge reads (stamp checked at most once a minute per worker). {} when the category is unknown."""
    if not discipline or not category_id:
        return {}
    return ((current(discipline, fresh=fresh).get("item_values") or {}).get(category_id)) or {}


def serve_configs(configs, fresh=True):
    """The request-path helper (`extraction._load_active_configs`): {(discipline, category_id): cfg} -> merged, the stamp
    checked once per discipline present."""
    out = {}
    built_by = {}
    for (d, cid), cfg in configs.items():
        if not isinstance(cfg, dict) or (d not in LINKED_DISCIPLINES and not has_placeholder(cfg)):
            out[(d, cid)] = cfg
            continue
        if d not in built_by:
            built_by[d] = current(d, fresh=fresh)
        out[(d, cid)] = merge_config(cfg, built_by[d], d)
    return out
