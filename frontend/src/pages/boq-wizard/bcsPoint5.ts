/**
 * BCS-FX (owner R-BCS-174, 28 Nov 00:04 / 00:07; QR-P5-SOURCE ruled (a)) -- NOTE POINT 5: the rows that have a BoQ SUPPLY amount
 * but no BCS supply cost yet, and the margin's "*".
 *
 * PURE. It reads the SAME per-row figures the Summary panel already has -- the rollup's own row amounts (`RollupNode.ownAmounts`,
 * the figure each Amount column shows: formula-aware, reconciliation-aware) and the stored cost rows (`ratesByExcelRow`) -- and
 * works nothing out a second time. The margin's own calculation (`pricingRollup.ts`, `bcsColumns.ts`, `bcsRollup.ts`) is not
 * touched and not re-done here: point 5 and the "*" only READ.
 *
 * A row is listed when
 *   - its BoQ supply amount, as the Amount (Supply) column shows it, is above 0 -- on a combined-rate sheet (ONE rate column,
 *     `bcsLiveRateKinds` = ["combined"]) the combined BoQ amount, as the Amount (Total) column shows it. A sheet with supply and
 *     install rates but NO Amount (Supply) column (e.g. only an Amount (Total)) has its supply amount as the row's quantity x
 *     its supply rate, the two cells the grid shows; AND
 *   - its BCS supply is blank or 0 -- on a combined-rate sheet the BCS combined cost. A typed 0 is listed (R-BCS-175).
 * Never listed: an install-only row (it has no supply amount); a row point 3 leaves out of the margin (`leftOut`).
 */
import { bcsAmountAxes, type BcsRateKind } from "./bcsColumns";
import type { RollupColumn, RollupNode } from "./pricingRollup";
import { resolveDescriptorValue } from "./reviewRender";
import type { BcsRowRate, ColumnDescriptor, PricedRow } from "./boqTypes";

/** The new note line, word for word (R-BCS-181). */
export const POINT5_TEXT = "These rows have a BoQ supply amount but no BCS supply cost yet:";
/** The line under the panel / the BoQ summary table when point 5 lists a row (R-BCS-181). */
export const NOT_FINAL_LINE = "* Not final: some rows have no BCS cost yet (see point 5).";
/** The mark on a % Margin that includes a point-5 row. */
export const NOT_FINAL_MARK = "*";

/** The amount columns point 5 reads on this sheet: the supply ones, or on a combined-rate sheet the total ones (else all). */
export function point5AmountColumns(columns: readonly RollupColumn[], kinds: readonly BcsRateKind[]): RollupColumn[] {
  const combined = kinds.length === 1 && kinds[0] === "combined";
  if (!combined) return columns.filter((c) => bcsAmountAxes(c.descriptor)?.kind === "supply");
  const totals = columns.filter((c) => bcsAmountAxes(c.descriptor)?.kind === "total");
  return totals.length > 0 ? totals : [...columns];
}

/** One row's BoQ amount point 5 checks: the sum of its own shown amounts in `cols` (null cells count as 0). */
export function point5BoqAmount(node: RollupNode, cols: readonly RollupColumn[]): number {
  let s = 0;
  for (const c of cols) {
    const v = node.ownAmounts[c.col];
    if (typeof v === "number" && Number.isFinite(v)) s += v;
  }
  return s;
}

/** One row's BCS figure point 5 checks: supply, or combined on a combined-rate sheet. Blank (no record, null) = 0. */
export function point5BcsFigure(rate: BcsRowRate | undefined, kinds: readonly BcsRateKind[]): number {
  if (!rate) return 0;
  const combined = kinds.length === 1 && kinds[0] === "combined";
  const v = Number(combined ? rate.combined_rate : rate.supply_rate);
  return Number.isFinite(v) ? v : 0;
}

export interface Point5Input {
  /** The rollup's forest and amount columns (`rollupByParent(...).roots / .columns`). */
  roots: readonly RollupNode[];
  columns: readonly RollupColumn[];
  /** The stored cost rows by Excel row (`BcsRollupInput.ratesByExcelRow`). */
  ratesByExcelRow: ReadonlyMap<number, BcsRowRate>;
  /** The sheet's live rate kinds (`BcsRollupInput.kinds`). */
  kinds: readonly BcsRateKind[];
  /** Point 3's rows (`amountExceptions(...).leftOut`): never listed. */
  leftOut: readonly number[];
  /** The sheet's rows and descriptors: read only on a halves sheet with no Amount (Supply) column (qty x supply rate). */
  rows?: readonly PricedRow[];
  descriptors?: readonly ColumnDescriptor[];
}

const num = (v: unknown): number => {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
};

/** A halves sheet with no Amount (Supply) column: each row's quantity x supply rate, as the grid's two cells show them. */
function supplyByQtyRate(rows: readonly PricedRow[], descriptors: readonly ColumnDescriptor[]): Map<number, number> {
  const qty = descriptors.filter((d) => d.value_field === "qty_total");
  const rate = descriptors.filter((d) => d.value_field === "rate_supply");
  const out = new Map<number, number>();
  if (qty.length === 0 || rate.length === 0) return out;
  for (const r of rows) {
    if (r.source_row_number === null || r.source_row_number === undefined) continue;
    const q = qty.reduce((s, d) => s + num(resolveDescriptorValue(r, d)), 0);
    const p = rate.reduce((s, d) => s + num(resolveDescriptorValue(r, d)), 0);
    out.set(r.source_row_number, q * p);
  }
  return out;
}

/** Point 5's rows (Excel row numbers, ascending). */
export function point5Rows(input: Point5Input): number[] {
  const cols = point5AmountColumns(input.columns, input.kinds);
  const combined = input.kinds.length === 1 && input.kinds[0] === "combined";
  const byQtyRate = cols.length === 0 && !combined ? supplyByQtyRate(input.rows ?? [], input.descriptors ?? []) : null;
  if (cols.length === 0 && (byQtyRate === null || byQtyRate.size === 0)) return [];
  const out = new Set(input.leftOut);
  const rows: number[] = [];
  const walk = (n: RollupNode) => {
    const er = n.sourceRowNumber;
    const boq = er === null ? 0 : byQtyRate ? (byQtyRate.get(er) ?? 0) : point5BoqAmount(n, cols);
    if (er !== null && !out.has(er) && boq > 0
        && point5BcsFigure(input.ratesByExcelRow.get(er), input.kinds) === 0) rows.push(er);
    n.children.forEach(walk);
  };
  input.roots.forEach(walk);
  return rows.sort((a, b) => a - b);
}

/** The panel's row indexes whose % Margin includes a point-5 row: each listed row's own node and every ancestor. */
export function point5MarkedRowIndexes(roots: readonly RollupNode[], listed: readonly number[]): Set<number> {
  const want = new Set(listed);
  const marked = new Set<number>();
  const walk = (n: RollupNode): boolean => {
    let hit = n.sourceRowNumber !== null && want.has(n.sourceRowNumber);
    for (const c of n.children) if (walk(c)) hit = true;
    if (hit) marked.add(n.rowIndex);
    return hit;
  };
  roots.forEach(walk);
  return marked;
}
