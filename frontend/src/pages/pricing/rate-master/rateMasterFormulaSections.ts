/**
 * BCS-W -- THE FORMULA ROW'S CELL IN TWO SECTIONS: the price lines (BoQ - what we quote the customer) and the cost lines (BCS -
 * our cost). PURE. Owner R2 (2026-11-24 13:12: "make BoQ and BCS explantion visibly different"), R4 (23:31: "it should be more
 * like a section header"); the approved mockup board 1.
 *
 * It adds NO wording of its own and changes none: each section is `columnNote` (rateMasterSpec.ts, unchanged, the file
 * export's twin) run over the category's PRICE pipelines and over its COST pipelines (`*_bcs`, the same test the helper uses,
 * `isBcsPipelineId`). A cost line that is also a price line stays in the BoQ section only, as the single cell did. A band step
 * (the wiring gland) may carry a line per band (`bands[i].explain`): on the price side the band's own line names its band; on
 * the cost side the step's own line (the generated cost wording) is the cost line.
 */
import type { RateCategoryConfig } from "./rateMasterTypes";
import { BOQ_RATE_NOTE, columnNote } from "./rateMasterSpec";

export interface FormulaSections {
  /** the price lines, in the order the single cell showed them */
  boq: string[];
  /** the cost lines not already a price line; [] = the cell shows the BoQ section only */
  bcs: string[];
}

/** The same test as the helper's `isBcsPipelineId` (a cost pipeline's id names "bcs"). */
const isCostPipeline = (id: string): boolean => id.toLowerCase().includes("bcs");
const NO_PIPELINE = "a TYPED rate. No pipeline reads it yet.";

type Band = { target?: string; explain?: string };
type Step = { step?: string; explain?: string; bands?: Band[] } & Record<string, unknown>;

/** The config with only the pipelines `keep` names; on the price side a band step takes the line of the band naming `rateKey`. */
function only(config: RateCategoryConfig, keep: (id: string) => boolean, rateKey: string, bandLines: boolean): RateCategoryConfig {
  // read loosely (the `Pipeline` union does not give every step `bands`); nothing here writes into the config
  const pipes = (config.pipelines ?? {}) as unknown as Record<string, { steps?: Step[] } & Record<string, unknown>>;
  const kept: Record<string, unknown> = {};
  for (const [id, pl] of Object.entries(pipes)) {
    if (!keep(id)) continue;
    kept[id] = !bandLines ? pl : {
      ...pl,
      steps: (pl.steps ?? []).map((s) => {
        const band = s.step === "component_band" ? (s.bands ?? []).find((b) => b?.target === rateKey && typeof b.explain === "string" && b.explain) : undefined;
        return band ? { ...s, explain: band.explain } : s;
      }),
    };
  }
  return { ...config, pipelines: kept } as RateCategoryConfig;
}

/** The FORMULA row's cell for one rate column, split into its BoQ and BCS sections (module doc). */
export function columnNoteSections(config: RateCategoryConfig, rateKey: string, derivedCount = 0): FormulaSections {
  const boq = columnNote(only(config, (id) => !isCostPipeline(id), rateKey, true), rateKey, derivedCount).split("\n");
  const seen = new Set(boq);
  const bcs = columnNote(only(config, isCostPipeline, rateKey, false), rateKey, 0)
    .split("\n")
    .filter((l) => l && l !== NO_PIPELINE && l !== BOQ_RATE_NOTE && !seen.has(l));
  return { boq, bcs: [...new Set(bcs)] };
}

/** Is this config an Electrical category's? (the FORMULA row's sections are Electrical's: owner R2 / R4) */
export function isElectricalConfig(config: RateCategoryConfig | null | undefined): boolean {
  return String((config as { discipline?: unknown } | null | undefined)?.discipline ?? "") === "Electrical";
}

/** Owner (mockup board 1): the explanation-row line shows ONCE per FORMULA row on an Electrical category - under the first
 *  formula column; every other discipline keeps it under both, as today. */
export function formulaHintShownUnder(config: RateCategoryConfig | null | undefined, column: "supply" | "install"): boolean {
  return !isElectricalConfig(config) || column === "supply";
}
