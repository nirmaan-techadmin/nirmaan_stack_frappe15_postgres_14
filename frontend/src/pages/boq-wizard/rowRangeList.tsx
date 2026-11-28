/**
 * BCS-6a -- the long-list form of the note's row lists, shared by the sheet Summary panel's note and the BoQ summary's grey lines.
 * BCS-FX: moved here VERBATIM from BoqSummaryBlock.tsx (file size, rule S1); BoqSummaryBlock re-exports both names.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { rowRanges } from "./pricingRollup";

/** How many ranges the long list shows before "show all" (owner R5, 00:28: "the long list format is correct, but it should be
 *  shown in the block itself"). */
export const ROW_LIST_SHOWN = 8;

/**
 * BCS-6a -- THE LONG-LIST FORM (owner R5 00:26 "how do wew show all these ows in the list on the note"; mockup board 2): the
 * count first, the row numbers joined into ranges, "show all" opening the full list, each row number taking the user to that
 * row -- by `onJump` (the sheet page's own grid jump) or by `hrefFor` (the pricing route's `?row=` link, `matchRowHref`). An
 * empty list reads "none on this sheet". Shared by the sheet's Summary panel note and the BoQ summary's grey lines.
 */
export function RowRangeList({ rows, onJump, hrefFor }: { rows: readonly number[]; onJump?: (excelRow: number) => void;
  hrefFor?: (excelRow: number) => string }) {
  const [all, setAll] = useState(false);
  if (rows.length === 0) return <span>none on this sheet</span>;
  const ranges = rowRanges(rows);
  const shown = all ? ranges : ranges.slice(0, ROW_LIST_SHOWN);
  const num = (n: number) => onJump
    ? <button type="button" aria-label={`Go to row ${n}`} className="text-primary hover:underline" onClick={() => onJump(n)}>{n}</button>
    : hrefFor ? <Link aria-label={`Go to row ${n}`} className="text-primary hover:underline" to={hrefFor(n)}>{n}</Link> : <span>{n}</span>;
  return (
    <span>
      {rows.length} {rows.length === 1 ? "row" : "rows"}:{" "}
      {shown.map(([a, b], k) => (
        <span key={a}>{k > 0 ? ", " : ""}{num(a)}{b !== a && <>-{num(b)}</>}</span>
      ))}
      {ranges.length > ROW_LIST_SHOWN && (
        <>{!all && " ..."} <button type="button" className="text-primary hover:underline" onClick={() => setAll(!all)}>
          {all ? "show fewer" : "show all"}</button></>
      )}
    </span>
  );
}
