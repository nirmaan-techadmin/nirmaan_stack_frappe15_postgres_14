/**
 * BCS-FX (owner R-BCS-180 ODD-13, R-BCS-181 W39) -- the Calculator's category picker: which categories it offers, when it shows
 * a scroll cue, and the line beside it. Moved out of PricingCalculator.tsx (file size, rule S1). PURE.
 */
import { isPricingInputConfig } from "./rate-master/rateMasterSpec";
import { costPipelineIds } from "@/pages/boq-wizard/rate-helper/pricingSheetHelper";
import type { RateCategoryConfig } from "./rate-master/rateMasterTypes";

/** BCS-FX (owner R-BCS-181, W39): the line beside the category picker, word for word. */
export const CALCULATOR_LINE = "Every field starts blank. No price shows until the needed fields are filled. Nothing here is saved.";
/** BCS-FX (owner R-BCS-180, ODD-13): how many categories the picker's list shows before it scrolls (its max height, 15 rem). */
export const PICKER_VISIBLE = 7;
/** BCS-FX (ODD-13): the cue under a list that scrolls. */
export const PICKER_SCROLL_CUE = "Scroll for more categories";

/**
 * BCS-FX (owner R-BCS-180, ODD-13): is this category offered in the Calculator's picker? A PRICING INPUTS category (its config
 * holds only Pricing Input kinds -- `isPricingInputConfig`, the Rate Master's own test, no typed id) prices nothing, so it is not
 * offered; it stays in the registry and on its own Rate Master page. PURE.
 */
export function offeredInCalculator(config: RateCategoryConfig | null | undefined): boolean {
  return !isPricingInputConfig(config);
}

/** BCS-FX (ODD-12): does this category have a cost (BCS) calculation? -- the Calculator's folded "fill the fields" line shows only then. */
export function hasCostCalculation(config: RateCategoryConfig | null | undefined): boolean {
  return !!config && costPipelineIds(config).length > 0;
}

/** BCS-FX (ODD-13): how many categories the picker offers (Pricing Inputs left out) -- the scroll cue shows above PICKER_VISIBLE. */
export function offeredCount(categories: readonly { category_id: string }[], configs: ReadonlyMap<string, RateCategoryConfig>): number {
  return categories.filter((c) => offeredInCalculator(configs.get(c.category_id))).length;
}
