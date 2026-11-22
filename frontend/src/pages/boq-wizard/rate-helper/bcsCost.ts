/**
 * BCS-2 -- THE COST RULES SHARED BY THE HELPER, THE CHECK LINE AND THE MINT GATE. PURE: no React, no fetch.
 *
 * The rule (owner 2026-11-21): where no BCS supply is stated for an item, BCS supply = BoQ supply / (1 + supply margin). A
 * stated cost must AGREE with that rule; "rounding on the cost side also counts as agreeing", wastage is expected.
 *
 * NOTHING IS HARDCODED (owner 2026-11-22: "the discount % should change if the user changes it from th epricing input or
 * the category sheet itself. dont hardcode it"). The margin is never a number in this file: `resolveBcsMargin` reads it from
 * the category config's `bcs_default_margin`, which names the Pricing Input the BoQ supply already reads.
 */
import { roundUp } from "../../pricing/rate-master/ratePipelineInterpreter";
import type { RateMasterItem } from "../../pricing/rate-master/rateMasterTypes";

/** The formula cost, UNROUNDED: BoQ supply / (1 + supply margin). */
export function defaultBcsSupply(boqSupply: number, margin: number): number {
  return boqSupply / (1 + margin);
}

/** A equal, B rounding only, C wastage, D disagrees, E nothing stated (BCS-R1's classes). */
export type BcsClass = "A" | "B" | "C" | "D" | "E";

/** money is stored to 2 decimals, so equal means within half a paisa; a round-up test is exact (BCS-R1 P2b) */
const CLOSE = 0.005;
const EXACT = 1e-6;
const close = (a: number, b: number) => Math.abs(a - b) <= CLOSE;

function classify(stated: number, boqSupply: number, margin: number, roundDigits: number | null, wastage: number): BcsClass {
  const formula = defaultBcsSupply(boqSupply, margin);
  const rounds = (s: number) => roundDigits !== null && Math.abs(roundUp(s * (1 + margin), roundDigits) - boqSupply) <= EXACT;
  if (close(formula, stated)) return "A";
  if (rounds(stated)) return "B";
  if (wastage) {
    const s0 = stated / (1 + wastage);
    if (close(formula, s0) || rounds(s0)) return "C";
  }
  return "D";
}

/**
 * Does a stated cost agree with BoQ supply / (1 + margin)? BCS-R1's tests, in its order:
 *   A  |formula - stated| <= 0.005
 *   B  roundUp(stated x (1 + margin)) is the BoQ supply, with the BoQ pipeline's OWN round-up digits (`roundDigits`)
 *   C  after dividing the wastage out
 *   then, for a stated cost that still differs, the COST side's own round-up is taken away (`statedPre` is the stated cost
 *   BEFORE its round-up) and the tests run again; a pass is B or C (owner R-BCS-38 b: "rounding on the cost side ... yes")
 * `roundDigits` null = the BoQ figure has no round-up. `stated` undefined = no stated cost (E).
 */
export function bcsAgrees(
  stated: number | null | undefined,
  boqSupply: number,
  margin: number,
  roundDigits: number | null,
  wastage = 0,
  statedPre?: number | null,
): BcsClass {
  if (stated === null || stated === undefined) return "E";
  const c = classify(stated, boqSupply, margin, roundDigits, wastage);
  if (c !== "D" || statedPre === null || statedPre === undefined || statedPre === stated) return c;
  const c2 = classify(statedPre, boqSupply, margin, roundDigits, wastage);
  return c2 === "A" ? "B" : c2;
}

export const agrees = (c: BcsClass): boolean => c === "A" || c === "B" || c === "C";

/** One margin: which Pricing Input field, for which components, under which selection. */
export interface BcsMarginEntry {
  /** component names this margin prices; absent = every component of the category */
  components?: string[];
  /** applies only when each selected attribute has this value (a cable's insulation) */
  when?: Record<string, string | number>;
  ref: { kind: string; item: string };
  /** the rate field: `supply_markup` is the margin itself; `ratio` is our share of the quote, so margin = 1 / ratio - 1 */
  field: string;
}
export interface BcsDefaultMargin { entries: BcsMarginEntry[] }

/** The margin a cost component is checked with, LIVE from the Pricing Input; null when the config names none or it has no value. */
export function resolveBcsMargin(
  config: { bcs_default_margin?: BcsDefaultMargin } | null | undefined,
  items: readonly RateMasterItem[],
  component: string | null,
  selected: Record<string, string | number> = {},
): number | null {
  for (const e of config?.bcs_default_margin?.entries ?? []) {
    if (e.components && !(component !== null && e.components.includes(component))) continue;
    if (e.when && !Object.entries(e.when).every(([k, v]) => selected[k] === v)) continue;
    const it = items.find((i) => i.kind === e.ref.kind && (i.attributes as Record<string, unknown> | undefined)?.item === e.ref.item);
    const v = it?.rates?.[e.field];
    if (typeof v !== "number" || !Number.isFinite(v)) return null;
    if (e.field === "ratio") return v > 0 ? 1 / v - 1 : null;
    return v;
  }
  return null;
}
