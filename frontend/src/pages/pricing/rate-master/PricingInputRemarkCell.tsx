/**
 * BCS-W -- a template Pricing Input remark on the Rate Master grid: worked out from the row's current values
 * (`remarkSections`), the price sentence in the green BoQ section and the cost sentence in the blue BCS section (BCS-3's
 * section piece, the same look as the helper panel). Owner Question 1 answer 1a (2026-11-25); the approved mockup board 2.
 * The full text is the cell's hover title, as the plain remark's is.
 */
import { PriceSection } from "@/pages/boq-wizard/rate-helper/PriceSection";
import { remarkSections } from "./pricingInputRemarks";

export interface RemarkCellProps {
  /** the stored remark (a template) */
  remark: unknown;
  /** the row's current figures (the draft while the row is edited) */
  values: Readonly<Record<string, unknown>>;
}

export function RemarkCell({ remark, values }: RemarkCellProps) {
  const s = remarkSections(remark, values);
  // the grid keeps a row short (the owner's five-line rule for this table): two sections clamp to two lines each
  const clamp = s.boq && s.bcs ? "line-clamp-2" : "line-clamp-3";
  return (
    <div className="space-y-1" title={[s.boq, s.bcs].filter(Boolean).join("\n")} data-testid="pi-remark-sections">
      {s.boq && (
        <PriceSection side="boq" open className="py-1">
          <div className={clamp}>{s.boq}</div>
        </PriceSection>
      )}
      {s.bcs && (
        <PriceSection side="bcs" open className="py-1">
          <div className={clamp}>{s.bcs}</div>
        </PriceSection>
      )}
    </div>
  );
}
