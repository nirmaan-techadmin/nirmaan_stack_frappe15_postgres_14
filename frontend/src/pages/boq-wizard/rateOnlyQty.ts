/**
 * BCS-FX (owner R-BCS-180, ODD-8: "show "RO" in the quantity cell") -- what a RATE-ONLY row's quantity cell shows.
 *
 * PURE, display only. A rate-only row is the one the note's point 4 already never lists (`pricingRollup.rateWithoutQuantity`):
 * (a) the parser marked it (`is_rate_only`), or (b) the uploaded file's quantity cell reads a rate-only text (`qty_cell_text`, the
 * list `reconcile.RATE_ONLY_QTY_TEXTS`). Its quantity cell then shows the file's own text ("RO", exactly as the file has it; "RO"
 * when the parser marked the row without one) instead of 0. Every other row, and any quantity the row really holds, shows as
 * before. No figure is changed: the amount, the margin and every rule read the stored quantity as they always did.
 */
import { isBcsQtyColumn } from "./bcsColumns";
import { isRateOnlyQtyText } from "./reconcile";
import type { ColumnDescriptor, PricedRow } from "./boqTypes";

/** The text shown in place of the quantity, or null to show the cell as it always was. */
export function rateOnlyQtyText(row: PricedRow, d: ColumnDescriptor, value: unknown): string | null {
  if (!isBcsQtyColumn(d)) return null;
  const text = typeof row.qty_cell_text === "string" ? row.qty_cell_text.trim() : "";
  const rateOnly = row.is_rate_only === 1 || isRateOnlyQtyText(row.qty_cell_text);
  if (!rateOnly) return null;
  const n = typeof value === "number" ? value : value === null || value === undefined || value === "" ? 0 : Number(value);
  if (Number.isFinite(n) && n !== 0) return null; // a real quantity is shown as it is
  return text || "RO";
}
