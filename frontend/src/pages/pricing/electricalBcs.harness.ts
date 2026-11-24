/**
 * BCS-2 -- the harness the Electrical cost tests share. It holds NO pricing arithmetic: every figure comes from the product's
 * interpreter (`runPipeline`) on the newest Electrical asset, and every verdict from `bcsAgrees`.
 */
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { agrees, bcsAgrees, resolveBcsMargin, type BcsClass, type BcsDefaultMargin } from "@/pages/boq-wizard/rate-helper/bcsCost";
import { runPipeline } from "./rate-master/ratePipelineInterpreter";
import type { Pipeline, RateMasterItem } from "./rate-master/rateMasterTypes";
import { readJsonFixture } from "./calculatorPanelParity.harness";

export interface Golden { id: string; attrs: Record<string, string | number>; expect: Record<string, Record<string, number>> }
export interface Cfg {
  category_id: string;
  pipelines: Record<string, Pipeline>;
  goldens?: Golden[];
  bcs_default_margin?: BcsDefaultMargin;
  summary_inputs?: string[];
}
export interface Asset { items: RateMasterItem[]; category_configs: Cfg[]; goldens: Record<string, Golden[]> }

const DATA_DIR = fileURLToPath(new URL("../../../../nirmaan_stack/services/boq_rate_master/data/", import.meta.url));
const PREFIX = "rate_master_electrical_all_v";
export const readAsset = (version: number): Asset => readJsonFixture<Asset>(pathToFileURL(join(DATA_DIR, `${PREFIX}${version}.json`)));
export const newestVersion = (): number => Math.max(...readdirSync(DATA_DIR).filter((f) => f.startsWith(PREFIX) && f.endsWith(".json")).map((f) => Number(f.slice(PREFIX.length, -5))).filter(Number.isFinite));   // "v16a" is an early name, never the newest

/** the items as `get_rate_master_items` serves them: the brand column projected into the attributes */
export const served = (a: Asset): RateMasterItem[] =>
  a.items.map((i) => ({ ...i, discipline: "Electrical", attributes: { ...i.attributes, ...(i.brand ? { brand: i.brand } : {}) } }));
export const cfgOf = (a: Asset, cat: string): Cfg => a.category_configs.find((c) => c.category_id === cat)!;
export const clone = <T,>(x: T): T => structuredClone(x);

/** a copy of the items with one Pricing Input's field changed -- a fixture, never live data */
export const withInput = (items: RateMasterItem[], id: string, field: string, value: number): RateMasterItem[] => {
  let hit = 0;
  const out = items.map((i) => {
    if (!i.kind.endsWith("_pricing_input") || i.attributes.item !== id) return i;
    hit += 1;
    return { ...i, rates: { ...i.rates, [field]: value } };
  });
  if (hit !== 1) throw new Error(`input ${id}: ${hit} rows`);
  return out;
};
export const inputValue = (items: RateMasterItem[], id: string, field: string): number => {
  const v = items.find((i) => i.kind === "electrical_pricing_input" && i.attributes.item === id)?.rates?.[field];
  if (typeof v !== "number") throw new Error(`no ${id}.${field}`);
  return v;
};

export interface Pair { cat: string; price: string; out: string; cost: string; costOut: string }
/** every Electrical category's supply price and its cost */
export const PAIRS: Pair[] = [
  { cat: "cabletray_raceway", price: "tray_boq_supply", out: "supply_per_rmt", cost: "tray_bcs", costOut: "bcs_supply" },
  { cat: "conduit_piping", price: "conduit_boq", out: "supply_per_mtr", cost: "conduit_bcs", costOut: "bcs_supply_per_mtr" },
  { cat: "db_switchgear", price: "db_buildup_supply", out: "supply", cost: "db_buildup_bcs", costOut: "bcs_supply" },
  { cat: "earthing", price: "earthing_boq", out: "supply", cost: "earthing_bcs", costOut: "bcs_supply" },
  { cat: "industrial_sockets", price: "indsock_boq", out: "supply", cost: "indsock_bcs", costOut: "bcs_supply" },
  { cat: "junction_box_raceway", price: "jb_boq", out: "supply", cost: "jb_bcs", costOut: "bcs_supply" },
  { cat: "lighting_mgmt_system", price: "lms_boq", out: "supply", cost: "lms_bcs", costOut: "bcs_supply" },
  { cat: "miscellaneous", price: "misc_boq", out: "supply", cost: "misc_bcs", costOut: "bcs_supply" },
  { cat: "point_wiring", price: "pw_boq_supply", out: "supply", cost: "pw_bcs", costOut: "bcs_supply" },
  { cat: "popup_boxes", price: "popup_boq", out: "supply", cost: "popup_bcs", costOut: "bcs_supply" },
  { cat: "switches_sockets", price: "swsock_boq", out: "supply", cost: "swsock_bcs", costOut: "bcs_supply" },
  { cat: "wiring_cabling", price: "cable_boq", out: "supply_per_mtr", cost: "cable_bcs", costOut: "bcs_supply_per_mtr" },
  { cat: "wiring_cabling", price: "termination_boq", out: "supply_per_set", cost: "termination_bcs", costOut: "bcs_supply_per_set" },
];

/** a pipeline with every round-up taken out: the figure BEFORE rounding, for the cost-side test */
const unrounded = (p: Pipeline): Pipeline => ({
  ...p,
  steps: (p.steps as Array<Record<string, unknown>>).filter((s) => s.step !== "roundup")
    .map((s) => (Array.isArray(s.rate_stages) ? { ...s, rate_stages: (s.rate_stages as Array<Record<string, unknown>>).map(({ round: _r, ...x }) => x) } : s)),
}) as Pipeline;

const lastDigits = (p: Pipeline, key: string): number | null => {
  const r = (p.steps as Array<{ step: string; target?: string; params?: { digits?: number } }>).filter((s) => s.step === "roundup" && s.target === key);
  return r.length ? (r[r.length - 1].params?.digits ?? null) : null;
};
type Trace = ReturnType<typeof runPipeline>;
const producedAll = (r: Trace, key: string): number[] => r.steps.filter((s) => s.produced?.key === key).map((s) => s.produced!.value);
const produced = (r: Trace, key: string): number | null => producedAll(r, key).at(-1) ?? null;

const wastageOf = (cfg: Cfg, items: RateMasterItem[], comp: string | null, sel: Golden["attrs"]): number => {
  for (const e of cfg.bcs_default_margin?.entries ?? []) {
    if (e.components && !(comp !== null && e.components.includes(comp))) continue;
    if (e.when && !Object.entries(e.when).every(([k, v]) => sel[k] === v)) continue;
    return items.find((i) => i.kind === e.ref.kind && i.attributes.item === e.ref.item)?.rates?.wastage ?? 0;
  }
  return 0;
};

export interface PartVerdict { part: string; price: number; cost: number | null; margin: number; cls: BcsClass }

/**
 * A golden's parts, each with its verdict. A category with ONE margin is judged on its total; a category with several (a cable
 * and its conduit, a box and its modules, sockets with a breaker, point wiring, lug and gland) part by part, each part with its
 * own margin and its own round-up, as BCS-R1 judged them.
 */
export function verdicts(cfg: Cfg, pair: Pair, items: RateMasterItem[], sel: Golden["attrs"]): PartVerdict[] | null {
  const P = cfg.pipelines[pair.price];
  const C = cfg.pipelines[pair.cost];
  const price = runPipeline(pair.price, P, items, sel);
  if (price.status !== "ok" || !Number.isFinite(price.finals[pair.out])) return null;
  const cost = C ? runPipeline(pair.cost, C, items, sel) : null;
  const costPre = C ? runPipeline(pair.cost, unrounded(C), items, sel) : null;
  const ok = cost?.status === "ok";
  const margin = (part: string | null): number => {
    const m = resolveBcsMargin(cfg as never, items, part, sel);
    if (m === null) throw new Error(`${cfg.category_id}: no margin for ${part}`);
    return m;
  };
  const judge = (part: string, comp: string | null, boq: number, stated: number | null, pre: number | null, digits: number | null): PartVerdict => {
    const m = margin(comp);
    return { part, price: boq, cost: stated, margin: m, cls: bcsAgrees(stated, boq, m, digits, wastageOf(cfg, items, comp, sel), pre) };
  };
  const total = () => [judge("total", null, price.finals[pair.out], ok ? cost!.finals[pair.costOut] : null, costPre?.finals[pair.costOut] ?? null, lastDigits(P, pair.out))];
  const refs = (P.steps as Array<{ step: string; name?: string; rate_stages?: Array<{ round?: string | null }> }>).filter((s) => s.step === "component_ref" && s.name);

  if (pair.price === "indsock_boq" || pair.price === "pw_boq_supply") {
    return refs.filter((s) => (produced(price, s.name!) ?? 0) > 0).map((s) => {
      const q = price.steps.find((x) => x.produced?.key === s.name)?.qty ?? 1;
      const per = (r: Trace | null) => { const v = r ? produced(r, s.name!) : null; return v === null ? null : v / q; };
      const up0 = (s.rate_stages ?? []).some((x) => x.round === "up0");
      return judge(s.name!, s.name!, per(price)!, ok ? per(cost) : null, per(costPre), up0 ? 0 : null);
    });
  }
  if (pair.price === "termination_boq") {
    // the markup is inside each part; one set, so the parts stand alone
    return ["lug", "gland"].map((n) => judge(n, n, produced(price, n)!, ok ? produced(cost!, n) : null, null, null));
  }
  if (pair.price === "cable_boq") {
    const seq = producedAll(price, "supply_per_mtr");                 // discounted, rounded to tens, x runs, + conduit, rounded
    const conduit = produced(price, "conduit") ?? 0;
    const cSeq = ok ? producedAll(cost!, "bcs_supply_per_mtr") : [];  // discounted, rounded, x runs [, + conduit]
    const pre = costPre ? producedAll(costPre, "bcs_supply_per_mtr") : [];
    const runs = Number(sel.runs ?? 1);
    const out = [judge("cable", null, seq[2] / runs, cSeq.length ? cSeq[2] / runs : null, pre.length ? pre[0] : null, -1)];
    if (conduit > 0) out.push(judge("conduit", "conduit", conduit, ok ? produced(cost!, "conduit") : null, null, null));
    return out;
  }
  if (pair.price === "popup_boq") {
    // BCS-2b (v74): a GENERATED popup_bcs names its parts as the price does - the box after its ratio is the LAST "box_supply",
    // the modules "module_supply"; v73's hand-written one named them the FIRST "bcs_supply" and "module_cost".
    const generated = !((C?.steps ?? []) as Array<{ result?: string }>).some((s) => s.result === "module_cost");
    const boxCost = !ok ? null : generated ? (producedAll(cost!, "box_supply").at(-1) ?? null) : (producedAll(cost!, "bcs_supply")[0] ?? null);
    const out = [judge("box", null, produced(price, "box_supply")!, boxCost, null, null)];
    const mods = produced(price, "module_supply") ?? 0;
    if (mods > 0) out.push(judge("modules", "switch", mods, ok ? produced(cost!, generated ? "module_supply" : "module_cost") : null, null, lastDigits(P, "module_supply")));
    return out;
  }
  return total();
}

export const allAgree = (v: PartVerdict[] | null): boolean => v !== null && v.length > 0 && v.every((x) => agrees(x.cls));
