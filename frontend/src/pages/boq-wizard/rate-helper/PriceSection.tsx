/**
 * BCS-3 -- THE ONE SECTION PIECE: a BoQ section (what we quote the customer) or a BCS section (our cost), open or folded.
 *
 * Used by the helper panel AND the calculator (the calculator mounts the same panel, `variant="calculator"`), so the two
 * can never draw a section differently. It draws the shell only -- the tag, the colour, the fold -- and the body it is
 * given; every figure in it comes from the helper's result (the interpreter's outputs), never from this file.
 *
 * THE LOOK (approved mockup 24 Nov, owner R3 / R5 / R6): BoQ = light green (#f0fdf4 / border #86efac / solid tag #15803d),
 * BCS = light blue (#eff6ff / #93c5fd / #1d4ed8), EQUAL weight ("the color schemer ... highlights the BCS nuch more
 * prominently" -> equal). These are exactly Tailwind's green-50 / green-300 / green-700 and blue-50 / blue-300 / blue-700,
 * the palette the repo already uses, so no colour is typed in. The section of the column the user clicked is OPEN and
 * EMPHASISED (a thicker border); the other is FOLDED to one line that opens on a tap (R6, "I agree").
 */
import type { ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { moneyValue } from "./attributeWorkingLines";

export type PriceSide = "boq" | "bcs";

/** The tags, word for word as approved (R3, 14:16: "BoQ tags on the BoQ boxes with verbiage like what we quote to customer"). */
export const SECTION_TAG: Record<PriceSide, string> = {
  boq: "BoQ - what we quote the customer",
  bcs: "BCS - our cost",
};

const LOOK: Record<PriceSide, { box: string; tag: string }> = {
  boq: { box: "bg-green-50 border-green-300 dark:bg-green-950/30 dark:border-green-800", tag: "bg-green-700 text-white" },
  bcs: { box: "bg-blue-50 border-blue-300 dark:bg-blue-950/30 dark:border-blue-800", tag: "bg-blue-700 text-white" },
};

export interface PriceSectionProps {
  side: PriceSide;
  /** open = the body shows; folded = one line: the tag, the figure, a chevron */
  open: boolean;
  /** the section of the clicked column: a thicker border (the other section, opened by a tap, keeps the thin one) */
  emphasised?: boolean;
  /** the figure the folded line shows (null/undefined = an em dash, never a 0) */
  foldedFigure?: number | null;
  /** a tap on the folded line (or on an open section's tag line) -- absent = the section cannot fold */
  onToggle?: () => void;
  className?: string;
  children?: ReactNode;
}

export function PriceSection({ side, open, emphasised = false, foldedFigure, onToggle, className, children }: PriceSectionProps) {
  const look = LOOK[side];
  const tag = <span className={cn("rounded px-1.5 py-0.5 text-[10px] font-semibold leading-none", look.tag)}>{SECTION_TAG[side]}</span>;
  if (!open) {
    return (
      <button
        type="button"
        onClick={onToggle}
        disabled={!onToggle}
        data-testid={`price-section-${side}-folded`}
        aria-expanded={false}
        className={cn("flex w-full items-center justify-between gap-2 rounded-md border px-2 py-1 text-left text-xs", look.box, className)}
      >
        {tag}
        <span className="flex items-center gap-1 tabular-nums">
          <span className="font-semibold text-foreground">{typeof foldedFigure === "number" ? moneyValue(foldedFigure) : "—"}</span>
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
        </span>
      </button>
    );
  }
  return (
    <section
      data-testid={`price-section-${side}`}
      data-emphasised={emphasised ? "1" : "0"}
      className={cn("rounded-md px-2 py-1.5", emphasised ? "border-2" : "border", look.box, className)}
    >
      <div className="mb-1 flex items-center justify-between gap-2">
        {tag}
        {onToggle && (
          <button type="button" onClick={onToggle} aria-expanded aria-label={`Fold ${SECTION_TAG[side]}`} className="rounded p-0.5 text-muted-foreground hover:bg-muted">
            <ChevronDown className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      {children}
    </section>
  );
}
