/**
 * BCS-3 -- THE COST SIDE OF A HELPER SUGGESTION, AND THE SPLIT LINES OF AN ADDED PART. PURE: no React, no fetch.
 *
 * WHAT IT DOES. For each price block the helper already shows (a non-BCS pipeline), it runs that block's PAIRED cost
 * pipeline (a `*_bcs` pipeline of the same category) through the SAME interpreter, on the SAME selection, and returns one
 * cost block per price block: the cost pipeline's own working lines and its supply figure. Nothing here computes a price
 * or a cost: every figure is an interpreter output or a step trace's value (owner R9: "dont hardcode it").
 *
 * THE PAIRING IS READ FROM THE RATE FILE, never a typed table (`pairedCostPipelineId`). A price block's supply output
 * (`supply`, `supply_per_mtr`, ...) pairs with the cost pipeline producing `bcs_<that output>`; failing that, a category
 * with exactly ONE cost pipeline producing a `bcs_supply...` output pairs it. A block producing no supply (an
 * installation-only pipeline) has no cost block: the cost is supply only (R-BCS-29 / R-BCS-38).
 *
 * THE SPLIT LINES (owner R4, 24 Nov 14:17: "1 conduit as its own line, price and cost: yes; 2 a line for the pop-up box
 * itself: yes"). Where a pipeline makes an output as `base + <part>` (a `scale` step whose formula is `base+<name>` and
 * whose `<name>_from_ctx` names an earlier value), the two parts are shown as their own lines, read from the step trace:
 * the base is the output's value just before that step, the part is the named value. In the live Electrical file exactly
 * two pipelines (and their cost twins) do this: the cable (cable + its conduit) and the pop-up box (the box + its
 * modules); HVAC has none. Display only -- the figures row and every total stay the interpreter's outputs (P4d).
 */
import { noneRefusalOf, runPipeline } from "@/pages/pricing/rate-master/ratePipelineInterpreter";
import type { Pipeline, PipelineResult, RateCategoryConfig, RateMasterItem, StepTrace } from "@/pages/pricing/rate-master/rateMasterTypes";
import { moneyValue } from "./attributeWorkingLines";
import type { BcsSide, RateKind, WorkingsGroup } from "./rateHelperTypes";

/** The line every cost block ends with (owner R-BCS-29: installation is one figure per BoQ, on the BoQ summary). BCS-W (owner 20:09
 *  "ok"; mockup board 3): the panel DRAWS it once per panel / calculator result, below the sections (`BcsSide.installNote`), and
 *  leaves it out of each drawn block; the helper's own blocks still end with it. */
export const BCS_INSTALL_NOTE = "Installation cost is one figure for the whole BoQ, on the BoQ summary";
/** The word in front of a cost block's figure. */
export const BCS_SUPPLY_WORD = "BCS supply";

/**
 * BCS-W (owner R5, 24 Nov 21:54 / 21:56 "1a"): a BCS figure ON SCREEN is whole rupees, ROUNDED UP, thousands separated (2009.6 ->
 * "2,010", 441.6 -> "442", 6090.6 -> "6,091"); the value stored and written stays exact (`bcsExactText`). The figure is first held
 * to the paisa, so a float like 1568.0000000002 reads 1,568, not 1,569. Display only: no figure changes.
 */
export function bcsFigureText(v: number): string {
  if (!Number.isFinite(v)) return String(v);
  const paise = Math.round(v * 100) / 100;
  return Math.ceil(paise - 1e-9).toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

/** BCS-W (owner "1a"): the EXACT figure "Use this value" writes, to the paisa, as the box beside it shows it (2,009.60). */
export function bcsExactText(v: number): string {
  return Number.isFinite(v) ? v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : String(v);
}

/** The value typed in the box beside "Use this value" on the BCS side, separators allowed ("2,009.60" -> 2009.6). */
export function parseBcsValue(text: string): number {
  return Number.parseFloat(String(text).replace(/,/g, ""));
}

/** A cost block's working line AS DRAWN (the panel maps each cost line through it; the helper's own lines stay exact): the figure
 *  after "= " -- ending the line, or before ", rounded ..." -- shows whole, rounded up. */
export function bcsLine(line: string): string {
  return line.replace(/= (-?\d[\d,]*(?:\.\d+)?)(?=$|, rounded)/, (_m, n: string) => `= ${bcsFigureText(Number(n.replace(/,/g, "")))}`);
}

/** A number written as text ("2925", "-1377.5", "2,196") with its whole part grouped as `bcsFigureText` groups it (en-IN) and its
 *  decimals kept exactly as written: "2925" -> "2,925", "1377.5" -> "1,377.5". */
function groupedNumberText(text: string): string {
  const [whole, frac] = text.replace(/,/g, "").split(".");
  const n = Number(whole);
  if (!/^-?\d+$/.test(whole) || !Number.isFinite(n)) return text;
  const grouped = (whole.startsWith("-") ? "-" : "") + Math.abs(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  return frac === undefined ? grouped : `${grouped}.${frac}`;
}

/**
 * BCS-W2 (owner R2, 25 Nov 13:08 "2. yes"): a BoQ figure ON SCREEN carries the thousands separator a BCS figure already carries
 * (`bcsFigureText`'s grouping: 2925 -> "2,925", 8638 -> "8,638"), and keeps its decimals exactly as it printed before (the figure to
 * the paisa, `moneyValue`: 1377.5 -> "1,377.5"). Display only: the box beside "Use this value", the value written, the copied
 * value and every amount stay as they are.
 */
export function boqFigureText(v: number): string {
  const m = moneyValue(v);
  return typeof m === "number" && Number.isFinite(m) ? groupedNumberText(String(m)) : String(m);
}

/** BCS-W2 (owner R2): a BoQ working line AS DRAWN -- its result figure (after "= ", ending the line or before ", rounded ...", the
 *  place `bcsLine` reads; and the figure after "rounded up to the rupee: " ending a line) with the thousands separator, its
 *  decimals as written. The helper's own lines stay exact. */
export function boqLine(line: string): string {
  return line
    .replace(/= (-?\d[\d,]*(?:\.\d+)?)(?=$|, rounded)/, (_m, n: string) => `= ${groupedNumberText(n)}`)
    .replace(/(rounded up to the rupee: )(-?\d[\d,]*(?:\.\d+)?)$/, (_m, lead: string, n: string) => `${lead}${groupedNumberText(n)}`);
}

/** The supply output of a pipeline: the first output that is `supply` or `supply_<unit>`. */
export function supplyOutputOf(pl: Pipeline | undefined): string | undefined {
  return (pl?.output ?? []).find((o) => o === "supply" || o.startsWith("supply_"));
}

/** The cost supply output of a cost pipeline: the first `bcs_supply` / `bcs_supply_<unit>` output. */
export function costSupplyOutputOf(pl: Pipeline | undefined): string | undefined {
  return (pl?.output ?? []).find((o) => o === "bcs_supply" || o.startsWith("bcs_supply_"));
}

/**
 * The cost pipeline paired with a price pipeline, read from the config (module doc). `costIds` are the category's cost
 * pipeline ids (the caller's own BCS test decides which ids those are). null = this price block has no cost block.
 */
export function pairedCostPipelineId(config: RateCategoryConfig, pricePid: string, costIds: readonly string[]): string | null {
  const pipes = (config.pipelines ?? {}) as Record<string, Pipeline>;
  const out = supplyOutputOf(pipes[pricePid]);
  if (!out) return null;
  const exact = costIds.find((id) => (pipes[id]?.output ?? []).includes(`bcs_${out}`));
  if (exact) return exact;
  const supplyCosts = costIds.filter((id) => costSupplyOutputOf(pipes[id]) !== undefined);
  return supplyCosts.length === 1 ? supplyCosts[0] : null;
}

/** "box_supply" -> "Box"; a part named only by the output's own words falls back to the matched row's kind. */
function partWord(key: string, outputKey: string, pl: Pipeline): string {
  const drop = new Set(["bcs", ...outputKey.split("_")]);
  const words = key.split("_").filter((w) => w && !drop.has(w));
  if (words.length > 0) return words.join(" ");
  const match = (pl.steps ?? []).find((s) => (s as { step?: string }).step === "match_master_row") as
    | { params?: { kind?: unknown } }
    | undefined;
  const kind = typeof match?.params?.kind === "string" ? match.params.kind : "";
  return kind.replace(/_/g, " ");
}

const cap = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);
const roundWords = (digits: number) => (digits <= -1 ? "rounded up to tens" : digits === 0 ? "rounded up to the rupee" : "rounded up");

/** One output's two parts, as lines, or null when the output is not `base + <part>` or the part is zero / absent. */
export interface AddedParts {
  /** "Cable supply = 80" / "Box supply = 7200" -- the base the part is added to */
  baseLine: string;
  /** "Conduit supply = 45.3" / "Modules supply = 1940" */
  partLine: string;
  /** "Cable + conduit = 125.3, rounded up to the rupee" -- only when a round-up follows the sum */
  sumLine?: string;
  base: number;
  part: number;
}

/**
 * The parts of `outputKey` from the step trace (module doc). `word` is the output's own word ("Supply", "Install",
 * "BCS supply"), so a line reads "<Base word> <word> = n". Reads ONLY the trace: no arithmetic beyond formatting.
 */
export function addedParts(pl: Pipeline, res: PipelineResult, outputKey: string, word: string): AddedParts | null {
  if (res.status !== "ok") return null;
  const steps: StepTrace[] = res.steps ?? [];
  const cfgStep = (pl.steps ?? []).find((s) => {
    const c = s as { step?: string; result?: string; formula?: string };
    return c.step === "scale" && c.result === outputKey && typeof c.formula === "string" && /^\s*base\s*\+\s*\w+\s*$/.test(c.formula);
  }) as { target?: string; formula?: string; params?: Record<string, unknown> } | undefined;
  if (!cfgStep || typeof cfgStep.target !== "string") return null;
  const name = (cfgStep.formula ?? "").split("+")[1].trim();
  const partKey = cfgStep.params?.[`${name}_from_ctx`];
  if (typeof partKey !== "string") return null;
  // the trace of THAT step: a scale producing the output whose params name this part (rate_ref steps run first, so a trace's
  // position is not the config's -- the step is found by what it read, never by its index)
  const i = steps.findIndex((st) => st.step === "scale" && st.produced?.key === outputKey && (st.params ?? {})[`${name}_from_ctx`] === partKey);
  if (i <= 0) return null;
  const base = steps[i - 1].runningValues?.[cfgStep.target];
  const part = steps[i].runningValues?.[partKey];
  if (typeof base !== "number" || typeof part !== "number" || !Number.isFinite(base) || !Number.isFinite(part)) return null;
  if (part === 0) return null; // nothing added (a cable with no conduit): no split, the block reads as today
  const w = word.toLowerCase().replace(/^bcs /, "");
  const baseWord = partWord(cfgStep.target, outputKey, pl);
  const lead = word.startsWith("BCS") ? "BCS " : "";
  // the price's own round-up right after the sum is SAID only where it changed the figure (80 + 45.5 = 125.5 -> 126); a sum
  // that is already whole reads as the two parts and the output, nothing more
  const round = steps[i + 1];
  const rounded = round?.step === "roundup" && round.produced?.key === outputKey && Math.abs((round.produced?.value ?? NaN) - (base + part)) > 1e-9;
  return {
    baseLine: `${lead}${lead ? baseWord : cap(baseWord)} ${w} = ${moneyValue(base)}`,
    partLine: `${lead}${lead ? name : cap(name)} ${w} = ${moneyValue(part)}`,
    ...(rounded
      ? { sumLine: `${cap(baseWord)} + ${name} = ${moneyValue(base + part)}, ${roundWords(Number((round.params as { digits?: number })?.digits ?? 0))}` }
      : {}),
    base,
    part,
  };
}

export interface PriceBlock {
  /** the price pipeline id */
  pid: string;
  /** the block's label as the BoQ section shows it (the cost block carries the same label) */
  label: string;
}

/**
 * THE COST SIDE (module doc). `blocks` = the price blocks in display order; `primaryPid` = the block whose cost is the
 * appliable value; `costIds` = the category's cost pipeline ids. Returns undefined when no block has a cost pipeline
 * (a category with no BCS calculation -- every HVAC category, or a config served without its cost content).
 */
export function computeBcsSide(
  config: RateCategoryConfig,
  items: RateMasterItem[],
  selected: Record<string, string | number>,
  blocks: readonly PriceBlock[],
  primaryPid: string,
  costIds: readonly string[],
  stacked: boolean,
  /** the block's step lines by the SAME rule as its price block (R7); absent = none (the wiring blocks list none) */
  linesOf?: (pl: Pipeline, res: PipelineResult) => string[],
): BcsSide | undefined {
  const pipes = (config.pipelines ?? {}) as Record<string, Pipeline>;
  const sections: WorkingsGroup[] = [];
  const values: Partial<Record<RateKind, number>> = {};
  const headlines: { label: string; values: Partial<Record<RateKind, number>> }[] = [];
  for (const b of blocks) {
    const cid = pairedCostPipelineId(config, b.pid, costIds);
    if (!cid) continue;
    const pl = pipes[cid];
    const out = costSupplyOutputOf(pl);
    const res = runPipeline(cid, pl, items, selected);
    const lines: string[] = [];
    const finals: Record<string, number> = {};
    const figures: Partial<Record<RateKind, number>> = {};
    if (res.status === "ok" && out && typeof res.finals[out] === "number") {
      // the SAME order as the price block (owner R4 / P4c): the base (the box itself) LEADS the block, before the parts it
      // carries; the added part and any round-up sit just before the figure line
      const parts = addedParts(pl, res, out, BCS_SUPPLY_WORD);
      if (parts) lines.push(parts.baseLine);
      if (linesOf) lines.push(...linesOf(pl, res));
      if (parts) lines.push(parts.partLine, ...(parts.sumLine ? [parts.sumLine] : []));
      lines.push(`${BCS_SUPPLY_WORD} = ${moneyValue(res.finals[out])}`);
      finals[out] = res.finals[out];
      figures.supply_rate = res.finals[out];
      if (b.pid === primaryPid) values.supply_rate = res.finals[out];
    } else {
      // a row the helper cannot price shows the refusal in both sections, and no cost (P3b)
      lines.push(
        noneRefusalOf(res) ??
          (res.status === "no_match" ? "No cost rate row matches these answers."
            : res.status === "ok" ? "No BCS supply for these answers." // ran, but produced no supply (nor did the price)
              : "The cost calculation could not run."),
      );
    }
    lines.push(BCS_INSTALL_NOTE); // the helper's block keeps it; the panel draws it ONCE below the sections (BCS-W, `installNote`)
    sections.push({ label: b.label, derivation: lines, finals, figures, figureKinds: ["supply_rate"] });
    headlines.push({ label: b.label, values: figures });
  }
  if (sections.length === 0) return undefined;
  return { sections, values, installNote: BCS_INSTALL_NOTE, ...(stacked ? { headlines } : {}) };
}
