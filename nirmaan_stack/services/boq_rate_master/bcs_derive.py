"""Electrical supply cost (BCS) calculations GENERATED from the price calculations (BCS-2b, 2026-11-24).

The owner's words: "ideally the BCS part should get worked out from the same code which works out the BoQ price, just leaving
the final supply markup increases, and adding exceptions like wastage where applicable" (R1, 2026-11-23); "for installation we
follow the rules we have specified" (R2: installation cost rules stay hand-written); "1b" - one calculation, generated when the
rate file is made (R3, 2026-11-24); "dont hardcode it" (R6: every figure is read from a Pricing Input, as the price reads it).

PURE: no frappe, no database, no network. The mint imports it to build a rate file; a test imports it to regenerate the cost
calculations of a committed file and compare (the drift test). It holds NO ARITHMETIC: it only rewrites pipeline steps; the
product's interpreter (ratePipelineInterpreter.ts) runs what it writes.

THE GENERAL RULE (one rule, no per-category code): every supply markup the category's `bcs_default_margin` names is left out of
the price calculation. The ctx key the price loads for that input (`rate_ref`, field `supply_markup`) is found, and every
`<x>_from_ctx` that reads it becomes `<x>: 0` - the factor (1 + markup) becomes (1 + 0). Every item read, discount read, catalogue
fit and refusal of the price stays as it is. The markup's own `rate_ref` is then read by nothing and goes.

THE EXCEPTIONS TABLE (`PAIRS` below, one entry per supply cost, each exception by kind and name):
  wastage          the named cable inputs: the markup is not left out but REPLACED by the same input's `wastage`
  drop_roundup     a round-up of the price is left out (target, which occurrence)
  roundup_digits   a round-up keeps its place but rounds to other digits (the cable: tens -> units)
  drop_stage_round a part's own per-part round-up is left out (industrial sockets: the socket, the paired breaker)
  ratio            our share of the quote: the named value x the input's `ratio` (miscellaneous; the pop-up box)
  cost_markup      a cost-only input the price does not read (lighting: `lms_bcs.bcs_markup`)

WHAT ELSE A GENERATED PIPELINE DOES (P2b): it keeps the cost's own OUTPUT names (the price's supply output is renamed); it drops
the price's installation steps (a cost has no use for them); where the previous cost carried an installation output
(`misc_bcs`, `popup_bcs`: R2) the steps that make it are carried over from the previous cost pipeline UNCHANGED; every explanation
line that changed reads as a cost (COST WORDING below; a price sentence left in a cost step is refused); it keeps every refusal of
the price (same step, same sentence); and its `note` says in one line that it is worked out from the price, markup left out.
`tray_bcs_install` (installation) is never generated.
"""
import copy
import json
import re

WASTAGE = "wastage"
DROP_ROUNDUP = "drop_roundup"
ROUNDUP_DIGITS = "roundup_digits"
DROP_STAGE_ROUND = "drop_stage_round"
RATIO = "ratio"
COST_MARKUP = "cost_markup"
EXCEPTION_KINDS = (WASTAGE, DROP_ROUNDUP, ROUNDUP_DIGITS, DROP_STAGE_ROUND, RATIO, COST_MARKUP)
PI_KIND = "electrical_pricing_input"
_PRUNABLE = ("scale", "roundup", "rate_ref", "install_as_ratio")


class GenerationError(ValueError):
    """The price calculation does not have the shape an exception names, or a price sentence would be left in a cost step."""


def _pair(category, price, price_out, cost, cost_out, exceptions=(), wording=(), plain=""):
    return {"category": category, "price": price, "price_out": price_out, "cost": cost, "cost_out": cost_out,
            "exceptions": list(exceptions), "wording": list(wording), "plain": plain}


def _x(kind, **kw):
    return dict(kw, kind=kind)


def _w(match, explain):
    """COST WORDING for one step of the generated pipeline: `match` names the step (all keys equal), `explain` is its line.
    `{input:<item>}` is replaced by that Pricing Input's own name, read from the rate file (never typed)."""
    return {"match": match, "explain": explain}


# ---------------------------------------------------------------------------------------------------- THE EXCEPTIONS TABLE
PAIRS = (
    _pair("cabletray_raceway", "tray_boq_supply", "supply_per_rmt", "tray_bcs", "bcs_supply",
          [_x(DROP_ROUNDUP, target="supply_per_rmt", occurrence=1)],
          [_w({"step": "scale", "result": "bcs_supply"}, "our cost: the parts above added, with the supply markup from {input:tray_supply} left out and not rounded up")],
          "its round-up is left out too"),
    _pair("conduit_piping", "conduit_boq", "supply_per_mtr", "conduit_bcs", "bcs_supply_per_mtr", [],
          [_w({"step": "scale", "result": "bcs_supply_per_mtr"}, "our cost per metre = the list price x (1 - the discount in {input:conduit}); the supply markup is left out")],
          ""),
    _pair("db_switchgear", "db_buildup_supply", "supply", "db_buildup_bcs", "bcs_supply", [],
          [_w({"step": "scale", "result": "bcs_supply"}, "our cost: the parts at list x (1 - the discount in {input:switchgear}); the supply markup is left out"),
           _w({"step": "roundup", "target": "bcs_supply"}, "our cost rounds up to the next 10, as the price does")],
          "the cost still rounds up to tens"),
    _pair("earthing", "earthing_boq", "supply", "earthing_bcs", "bcs_supply", [],
          [_w({"step": "scale", "result": "bcs_supply"}, "our cost: the earthing supply as listed; the supply markup from {input:earthing_supply} is left out")],
          ""),
    _pair("industrial_sockets", "indsock_boq", "supply", "indsock_bcs", "bcs_supply",
          [_x(DROP_STAGE_ROUND, parts=["socket", "paired_mcb"])],
          [_w({"step": "component_ref", "name": "socket"}, "the socket at our cost: list x (1 - the discount in {input:indsock}); its markup left out, not rounded up"),
           _w({"step": "component_ref", "name": "paired_mcb"}, "the paired MCB, added x1 UNLESS the socket is the interlocked type (then bundled, x0), at our cost: list x (1 - the discount in {input:switchgear}); its markup left out, not rounded up")],
          "each part's markup is left out, and each part's round-up too"),
    _pair("junction_box_raceway", "jb_boq", "supply", "jb_bcs", "bcs_supply",
          [_x(DROP_ROUNDUP, target="supply", occurrence=1)],
          [_w({"step": "scale", "result": "bcs_supply"}, "our cost = the list price less the discount in {input:jb_discount}; the supply markup from {input:jb_supply} is left out, and so is its round-up")],
          "its round-up is left out too"),
    _pair("lighting_mgmt_system", "lms_boq", "supply", "lms_bcs", "bcs_supply",
          [_x(DROP_ROUNDUP, target="supply", occurrence=1), _x(COST_MARKUP, target="supply", item="lms_bcs", field="bcs_markup")],
          [_w({"step": "scale", "target": "rate", "result": "bcs_supply"}, "our cost IS the catalogue rate as stored: the supply markup from {input:lms_supply} is left out, and so is its round-up to tens"),
           _w({"step": "scale", "target": "bcs_supply", "result": "bcs_supply", "formula": "base*(1+m)"}, "plus the cost-only markup in {input:lms_bcs}, which the price does not read")],
          "its round-up is left out too; plus the cost-only markup input, which the price does not read"),
    _pair("miscellaneous", "misc_boq", "supply", "misc_bcs", "bcs_supply",
          [_x(RATIO, target="supply", item="misc_supply")],
          [_w({"step": "scale", "target": "boq_supply", "result": "bcs_supply"}, "our cost = this rate x the ratio in {input:misc_supply}: our share of what we quote (the rate carries no markup of its own)"),
           _w({"step": "scale", "target": "bcs_supply", "result": "bcs_supply", "formula": "base*r"}, "our share of what we quote: the rate x the ratio in {input:misc_supply}")],
          "the price has no markup here: our cost is our share of the quote, the ratio input"),
    _pair("point_wiring", "pw_boq_supply", "supply", "pw_bcs", "bcs_supply",
          [_x(WASTAGE, items=["cable_unarm"])],
          [_w({"step": "component_ref", "name": "wire1"}, "the cable at our cost x length: list x (1 - discount) x (1 + wastage) from {input:cable_unarm}, the wastage in place of the markup"),
           _w({"step": "component_ref", "name": "conduit"}, "the conduit at our cost x ROUNDUP(length/circuits): list x (1 - the discount in {input:conduit}), its markup left out")],
          "the wires take the cable's wastage in place of their markup; each part keeps its round-up"),
    _pair("popup_boxes", "popup_boq", "supply", "popup_bcs", "bcs_supply",
          [_x(DROP_ROUNDUP, target="module_supply", occurrence=1), _x(RATIO, target="box_supply", item="popup_supply")],
          [_w({"step": "scale", "target": "supply_per_module", "result": "box_supply"}, "the box itself, priced per module (the guiding Floor BOX block); our cost takes our share of the quote, the ratio in {input:popup_supply}"),
           _w({"step": "scale", "target": "box_supply", "result": "box_supply", "formula": "base*r"}, "our share of the quote: the box x the ratio in {input:popup_supply}"),
           _w({"step": "scale", "target": "module_raw", "result": "module_supply"}, "the modules at our cost: list x (1 - the discount in {input:swsock}); their markup left out, not rounded up"),
           _w({"step": "scale", "target": "box_supply", "result": "bcs_supply"}, "our cost = the box at its share plus the modules it carries")],
          "the box is taken at our share of the quote (the ratio input); the modules lose their round-up too"),
    _pair("switches_sockets", "swsock_boq", "supply", "swsock_bcs", "bcs_supply", [],
          [_w({"step": "scale", "target": "bcs_supply", "result": "bcs_supply"}, "our cost: the parts at list x (1 - the discount in {input:swsock}); the supply markup is left out"),
           _w({"step": "roundup", "target": "bcs_supply"}, "our cost rounds up to the next 10, as the price does")],
          "the cost still rounds up to tens"),
    _pair("wiring_cabling", "cable_boq", "supply_per_mtr", "cable_bcs", "bcs_supply_per_mtr",
          [_x(WASTAGE, items=["cable_arm", "cable_unarm"]), _x(ROUNDUP_DIGITS, target="supply_per_mtr", occurrence=1, digits=0),
           _x(DROP_ROUNDUP, target="supply_per_mtr", occurrence=2)],
          [_w({"step": "apply_effective_multiplier", "result": "bcs_supply_per_mtr"}, "our cost: the supplier discount off list, plus the cable's wastage in place of the company markup ({input:cable_arm} when armoured, {input:cable_unarm} when unarmoured); rounded up to the rupee"),
           _w({"step": "roundup", "target": "bcs_supply_per_mtr"}, "our cost rounds up to the rupee (units), not to tens"),
           _w({"step": "component_ref", "name": "conduit"}, "the conduit the price adds, at our cost: list x (1 - the discount in {input:conduit}), its markup left out; one conduit regardless of parallel runs; not rounded"),
           _w({"step": "scale", "target": "bcs_supply_per_mtr", "result": "bcs_supply_per_mtr", "formula": "base+conduit"}, "our cost = the cable (rounded up to the rupee) plus its conduit at cost, not rounded again")],
          "the cable's wastage in place of its markup; the cable rounds up to the rupee instead of to tens; the total is not rounded again"),
    _pair("wiring_cabling", "termination_boq", "supply_per_set", "termination_bcs", "bcs_supply_per_set", [],
          [_w({"step": "component", "name": "lug"}, "the lug at our cost: list x (1 - the discount in {input:lug}); its markup left out"),
           _w({"step": "component_band", "name": "gland"}, "the gland at our cost: list x (1 - the discount in {input:gland}); its markup left out"),
           _w({"step": "roundup", "target": "bcs_supply_per_set"}, "our cost rounds up to the next 10, as the price does")],
          "the set still rounds up to tens"),
)

PLAIN_LINE = "Our cost (BCS), worked out from the price calculation with the supply markup left out"
# a price sentence is refused in a cost step unless the generator wrote it: these words mark a price line
_PRICE_WORDS = re.compile(r"markup|\bBoQ (?:rate|multiplier|price|supply)\b|\bBoQ =|round(?:s|ed)? up to (?:the next )?tens|company", re.I)


# ---------------------------------------------------------------------------------------------------- step helpers
def _from_ctx_values(obj):
    """every ctx key a step READS through a `*_from_ctx` value (params, conditions, rate stages; nested dicts / lists)."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.endswith("_from_ctx"):
                if isinstance(v, str):
                    out.append(v)
                elif isinstance(v, (list, dict)):
                    out.extend(_strings(v))
            else:
                out.extend(_from_ctx_values(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_from_ctx_values(v))
    return out


def _strings(obj):
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        return [s for v in obj.values() for s in _strings(v)]
    if isinstance(obj, list):
        return [s for v in obj for s in _strings(v)]
    return []


def _reads(step):
    keys = set(_from_ctx_values({k: v for k, v in step.items() if k not in ("explain", "note")}))
    if step.get("step") in ("scale", "roundup") and step.get("target"):
        keys.add(step["target"])
    return keys


def _produces(step):
    if step.get("step") == "roundup":
        return {step.get("target")}
    return {step["result"]} if step.get("result") else set()


def _param_dicts(step):
    """the param dicts a markup can sit in: the step's own, each condition's, each rate stage."""
    out = [step["params"]] if isinstance(step.get("params"), dict) else []
    out += [c["params"] for c in step.get("conditions") or [] if isinstance(c.get("params"), dict)]
    out += [st for st in step.get("rate_stages") or [] if isinstance(st, dict)]
    return out


def _rate_ref_index(steps, item, field):
    for i, s in enumerate(steps):
        if s.get("step") == "rate_ref" and (s.get("ref") or {}).get("item") == item and s.get("target") == field:
            return i
    return None


def _ensure_rate_ref(steps, item, field):
    i = _rate_ref_index(steps, item, field)
    if i is not None:
        return steps[i]["result"]
    key = "pi_%s_%s" % (item, field)
    # FIRST: the interpreter hoists rate_ref and pricing-input steps keeping their order (ratePipelineInterpreter.ts
    # hoistRateRefs), so the reference is loaded before any step reads it
    steps.insert(0, {"step": "rate_ref", "ref": {"kind": PI_KIND, "item": item}, "target": field, "result": key,
                     "explain": "pricing input: %s (%s)" % (item, field)})
    return key


def _nth_roundup(steps, target, occurrence, where):
    n = 0
    for i, s in enumerate(steps):
        if s.get("step") == "roundup" and s.get("target") == target:
            n += 1
            if n == occurrence:
                return i
    raise GenerationError("%s: no round-up #%s of %s" % (where, occurrence, target))


def _after_producer(steps, target, where):
    idx = None
    for i, s in enumerate(steps):
        if s.get("result") == target:
            idx = i
    if idx is None:
        raise GenerationError("%s: nothing produces %s" % (where, target))
    return idx


def _input_names(asset):
    return {(i.get("attributes") or {}).get("item"): (i.get("attributes") or {}).get("name")
            for i in asset.get("items") or [] if i.get("kind") == PI_KIND}


def _word(text, names, where):
    def sub(m):
        name = names.get(m.group(1))
        if not name:
            raise GenerationError("%s: wording names Pricing Input %r, which the file does not hold" % (where, m.group(1)))
        return "'%s'" % name
    return re.sub(r"\{input:([a-z0-9_]+)\}", sub, text)


def _match(step, match):
    return all(step.get(k) == v for k, v in match.items())


def _install_chain(stored_cost, keep_outputs):
    """The steps of the STORED cost pipeline that make its installation output(s) (R2), in their stored order, unchanged."""
    steps = stored_cost.get("steps") or []
    need, chain = set(keep_outputs), set()
    changed = True
    while changed:
        changed = False
        for i, s in enumerate(steps):
            if i in chain:
                continue
            if _produces(s) & need:
                if s.get("step") not in _PRUNABLE:
                    raise GenerationError("installation output made by a %s step" % s.get("step"))
                chain.add(i)
                need |= _reads(s)
                changed = True
    return [copy.deepcopy(steps[i]) for i in sorted(chain)]


# ---------------------------------------------------------------------------------------------------- the generator
def generate(asset, pair, stored_cost=None, without=(), general_rule=True, break_=None):
    """One generated cost pipeline for `pair`, from the PRICE pipeline of `asset`. `stored_cost` = the cost pipeline the
    file holds under the cost id (its installation steps are carried over, R2). `without` / `general_rule` / `break_` exist
    only for the switch-off proofs and the negative control."""
    cats = {c["category_id"]: c for c in asset["category_configs"]}
    cfg = cats[pair["category"]]
    where = "%s/%s" % (pair["category"], pair["cost"])
    price = cfg["pipelines"][pair["price"]]
    stored_cost = stored_cost if stored_cost is not None else cfg["pipelines"].get(pair["cost"])
    names = _input_names(asset)
    steps = copy.deepcopy(price["steps"])
    exc = [e for e in pair["exceptions"] if e["kind"] not in without]
    wast = {it for e in exc if e["kind"] == WASTAGE for it in e["items"]}
    if break_ == "cable_wastage":
        wast = set()
    # 1 THE GENERAL RULE
    for entry in (cfg.get("bcs_default_margin") or {}).get("entries", []):
        if entry.get("field") != "supply_markup" or not general_rule:
            continue
        item = entry["ref"]["item"]
        i = _rate_ref_index(steps, item, "supply_markup")
        if i is None:
            continue   # this price does not read that input (termination_boq reads neither cable input)
        if break_ == "conduit_margin_in" and item == "conduit":
            continue
        key = steps[i]["result"]
        repl = None
        if item in wast:
            repl = _ensure_rate_ref(steps, item, WASTAGE)
            i = _rate_ref_index(steps, item, "supply_markup")
        for s in steps:
            for p in _param_dicts(s):
                for pk in list(p.keys()):
                    if pk.endswith("_from_ctx") and p[pk] == key:
                        if repl:
                            p[pk] = repl
                        else:
                            del p[pk]
                            p[pk[: -len("_from_ctx")]] = 0
    # 2 the price's installation outputs and everything only they need go (a cost has no use for them)
    drop_outputs = [o for o in price.get("output") or [] if o != pair["price_out"]]
    steps = [s for s in steps if not (_produces(s) & set(drop_outputs))]
    # 3 THE EXCEPTIONS
    for e in exc:
        if e["kind"] == ROUNDUP_DIGITS:
            i = _nth_roundup(steps, e["target"], e["occurrence"], where)
            steps[i] = dict(steps[i], params=dict(steps[i].get("params") or {}, digits=e["digits"]))
    drops = [_nth_roundup(steps, e["target"], e["occurrence"], where) for e in exc if e["kind"] == DROP_ROUNDUP]
    for i in sorted(drops, reverse=True):
        del steps[i]
    for e in exc:
        if e["kind"] == DROP_STAGE_ROUND:
            for part in e["parts"]:
                hit = [s for s in steps if s.get("step") == "component_ref" and s.get("name") == part]
                if len(hit) != 1:
                    raise GenerationError("%s: part %s found %d times" % (where, part, len(hit)))
                hit[0]["rate_stages"] = [dict(st, round=None) for st in hit[0]["rate_stages"]]
    for e in exc:
        if e["kind"] == RATIO:
            k = _ensure_rate_ref(steps, e["item"], "ratio")
            i = _after_producer(steps, e["target"], where)
            steps.insert(i + 1, {"step": "scale", "target": e["target"], "result": e["target"], "params": {"r_from_ctx": k},
                                 "formula": "base*r"})
        elif e["kind"] == COST_MARKUP:
            k = _ensure_rate_ref(steps, e["item"], e["field"])
            i = _after_producer(steps, e["target"], where)
            steps.insert(i + 1, {"step": "scale", "target": e["target"], "result": e["target"], "params": {"m_from_ctx": k},
                                 "formula": "base*(1+m)"})
    # 4 prune what nothing reads any more (the left-out markups' references, the installation legs)
    keep_keys = {pair["price_out"]}
    while True:
        reads = [_reads(s) for s in steps]
        gone = [n for n, s in enumerate(steps) if s.get("step") in _PRUNABLE and _produces(s)
                and not (_produces(s) & (keep_keys | set().union(*[r for m, r in enumerate(reads) if m != n])))]
        if not gone:
            break
        steps = [s for n, s in enumerate(steps) if n not in gone]
    # 5 the cost's own output names
    po, co = pair["price_out"], pair["cost_out"]
    first_made = next((n for n, s in enumerate(steps) if po in _produces(s) and s.get("step") != "roundup"), None)
    if first_made is None:
        raise GenerationError("%s: nothing makes %s" % (where, po))
    if any(po in _reads(s) for s in steps[:first_made]):
        raise GenerationError("%s: %s is read before it is made" % (where, po))
    for n, s in enumerate(steps):
        if s.get("result") == po:
            s["result"] = co
        if s.get("target") == po and s.get("step") in ("scale", "roundup"):
            s["target"] = co
        for p in _param_dicts(s):
            for pk, pv in list(p.items()):
                if pk.endswith("_from_ctx") and pv == po:
                    p[pk] = co
    # 6 the installation output(s) the stored cost carries (R2): its own steps, unchanged
    outputs = [co]
    keep_install = [o for o in (stored_cost or {}).get("output") or [] if o != co]
    if keep_install:
        steps += _install_chain(stored_cost, keep_install)
        outputs = [o for o in stored_cost["output"]]
    # 7 COST WORDING
    # a switch-off variant (proofs only) may lack the step a removed exception makes: its wording is then skipped, unchecked
    variant = bool(without) or not general_rule or break_ is not None
    authored = set()
    for w in pair["wording"]:
        hit = [s for s in steps if _match(s, w["match"])]
        if len(hit) != 1 and variant:
            continue
        if len(hit) != 1:
            raise GenerationError("%s: wording %r matches %d steps" % (where, w["match"], len(hit)))
        hit[0]["explain"] = _word(w["explain"], names, where)
        authored.add(hit[0]["explain"])
    for s in steps:
        if s.get("pricing_input") and s.get("step") == "scale":
            ref_item = _pi_item_of(steps, s.get("target"))
            if ref_item is None:
                continue
            if "w_from_ctx" in (s.get("params") or {}) or any(v.endswith("_wastage") for v in _from_ctx_values(s.get("params") or {})):
                s["explain"] = _word("our cost multiplier = (1 - discount) x (1 + wastage), from {input:%s}: the wastage in place of the supply markup" % ref_item, names, where)
            elif s.get("formula") == "(1-base)*(1+m)" and (s.get("params") or {}).get("m") == 0:
                s["explain"] = _word("our cost multiplier = 1 - discount, from {input:%s}; the supply markup is left out" % ref_item, names, where)
            authored.add(s.get("explain"))
    install_steps = {json.dumps(s, sort_keys=True) for s in (_install_chain(stored_cost, keep_install) if keep_install else [])}
    for s in steps:
        if variant or json.dumps(s, sort_keys=True) in install_steps or s.get("step") == "rate_ref":
            continue
        line = s.get("explain") or ""
        if line not in authored and _PRICE_WORDS.search(line):
            raise GenerationError("%s: a price sentence would be left in a cost step: %r" % (where, line[:120]))
        if not line and s.get("step") == "apply_effective_multiplier":
            raise GenerationError("%s: an apply_effective_multiplier step needs cost wording" % where)
    out = {"output": outputs, "steps": steps, "note": PLAIN_LINE + "." + (" Also: %s." % pair["plain"] if pair["plain"] else "")}
    return out


def _pi_item_of(steps, key):
    for s in steps:
        if s.get("step") == "rate_ref" and s.get("result") == key:
            return (s.get("ref") or {}).get("item")
    return None


def generate_all(asset, stored=None, **kw):
    """{(category, cost id): generated pipeline} for every pair. `stored` = the asset whose cost pipelines give the installation
    steps to carry over (default: `asset` itself - so regenerating a generated file reproduces it: the drift test)."""
    stored = stored if stored is not None else asset
    scats = {c["category_id"]: c for c in stored["category_configs"]}
    return {(p["category"], p["cost"]): generate(asset, p, stored_cost=scats[p["category"]]["pipelines"].get(p["cost"]), **kw) for p in PAIRS}


def apply(asset, stored=None, **kw):
    """A copy of `asset` with every generated cost pipeline stored under its cost id; nothing else changes."""
    gen = generate_all(asset, stored=stored, **kw)
    out = copy.deepcopy(asset)
    for c in out["category_configs"]:
        for (cat, cid), pl in gen.items():
            if c["category_id"] == cat:
                c["pipelines"][cid] = pl
    return out


def drift(asset):
    """The cost pipelines of `asset` that are NOT what the generator makes from its own price pipelines: [(category, cost id)]."""
    canon = lambda o: json.dumps(o, sort_keys=True, separators=(",", ":"))
    cats = {c["category_id"]: c for c in asset["category_configs"]}
    return sorted(k for k, pl in generate_all(asset).items() if canon(pl) != canon(cats[k[0]]["pipelines"].get(k[1])))
