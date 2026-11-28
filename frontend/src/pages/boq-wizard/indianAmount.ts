/**
 * BCS-FX (owner R-BCS-180, ODD-7 "one Indian style everywhere"; QR-FORMAT ruled (a)) -- THE ONE number style for an amount on
 * the BCS screens: Indian grouping (12,34,567), up to two decimals, a blank for no value and "0" for a genuine zero.
 *
 * Shared by the sheet Summary panel's amount and cost cells and the grid's BCS Total Amount cell, so the same figure reads the
 * same on both. The BoQ summary keeps its own whole-rupee `bcsFigureText` (already en-IN). Display only: no figure is changed,
 * rounded or recomputed here.
 */
export function indianAmount(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "";
  if (n === 0) return "0";
  return n.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}
