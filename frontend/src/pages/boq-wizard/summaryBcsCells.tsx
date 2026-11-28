/**
 * BCS-S5 / BCS-FX -- the sheet Summary panel's BCS cells for one row (the BoQ amount when shown, BCS Total Amount, % Margin).
 * BCS-FX: moved here from SummaryPanel.tsx (file size, rule S1); the panel's figures are formatted by the one Indian style.
 */
import { bcsBlankReasonText, formatBcsMargin, type BcsComputedCell } from "./bcsColumns";
import type { BcsSectionTotals } from "./bcsRollup";
import { NOT_FINAL_MARK } from "./bcsPoint5";
import { indianAmount } from "./indianAmount";

/**
 * BCS-S5: one row's three BCS cells, rendered OUTSIDE the `columns.map` loop.
 *
 * ⚠️ A BLANK IS NEVER A 0 HERE, and the reason is carried in the `title` -- the same rule the
 * grid's computed cells keep. A section nobody has costed shows an EMPTY cost cell and an EMPTY
 * % Margin; rendering 0 / 0% would be a confident claim ("this section costs nothing", "we make
 * nothing on it") about a section where nothing is known. `fmtAmount` already distinguishes the
 * two: null -> "", a genuine 0 -> "0".
 *
 * No colour scale, deliberately: the grid presents % Margin as plain right-aligned figures, and a
 * second visual language for the same number in the panel above it would be its own confusion.
 */
export function bcsCells(totals: BcsSectionTotals | undefined, keyPrefix: string, cls: string, notFinal = false, boqAmount = false) {
  const marginCell: BcsComputedCell = totals?.margin ?? { kind: "blank", reason: "no_cost" };
  return (
    <>
      {/* BCS-FX (R-BCS-179): the BoQ amount column, only on a sheet with no Amount (Total) column. */}
      {boqAmount && (
        <td key={`${keyPrefix}-boq`} className={cls}>
          {indianAmount(totals?.tendered ?? null)}
        </td>
      )}
      <td key={`${keyPrefix}-cost`} className={cls}>
        {indianAmount(totals?.cost ?? null)}
      </td>
      {/* BCS-S8: the tendered `<td>` was removed here. `totals.tendered` is deliberately still
          populated -- `sectionMarginPercent` divides by it. */}
      <td
        key={`${keyPrefix}-margin`}
        className={cls}
        title={marginCell.kind === "blank" ? bcsBlankReasonText(marginCell.reason) : undefined}
      >
        {marginCell.kind === "value" ? formatBcsMargin(marginCell.value) : null}
        {/* BCS-FX (R-BCS-174): a shown margin that includes a point-5 row is "Not final"; the figure itself is unchanged. */}
        {marginCell.kind === "value" && notFinal ? NOT_FINAL_MARK : null}
      </td>
    </>
  );
}
