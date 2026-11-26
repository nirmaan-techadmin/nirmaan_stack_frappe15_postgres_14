/**
 * CAT-2 (QR-COMPAT (a), ANSWER to CAT2-5, 2026-11-27 01:03) -- TEST SUPPORT, no product code. Since HVAC v91 the catalogue values the
 * code rules pick as ONE target live in each config's `list_spec.code_targets` (owner 2026-11-26 00:10, R1); an asset minted before v91
 * carries none, so on it those rules do not fire (the live server only ever serves the newest version). An older test that drives one
 * of those rules on an older asset gives that asset the role blocks READ FROM THE NEWEST HVAC ASSET on disk -- never typed -- by wrapping
 * its load under its PIN; its assertions are unchanged. Configs the newest asset carries no block for are left as they are.
 */
import { readdirSync } from "node:fs";
import path from "path";
import { pathToFileURL } from "url";
import { readJsonFixture } from "../../pricing/calculatorPanelParity.harness";

type Cfg = { category_id?: unknown; list_spec?: Record<string, unknown> };
// path + pathToFileURL, not import.meta.url: a jsdom test file has no file-scheme module URL (the cat1Edits.harness precedent)
const DATA_DIR = path.resolve(__dirname, "../../../../../nirmaan_stack/services/boq_rate_master/data");
let newest: Map<string, unknown> | null = null;

/** The newest committed HVAC asset's `list_spec.code_targets` blocks, by category_id (read once). */
export function newestCodeTargets(): Map<string, unknown> {
  if (newest) return newest;
  const files = readdirSync(DATA_DIR).filter((f) => /^rate_master_hvac_all_v\d+\.json$/.test(f));
  files.sort((x, y) => Number(x.match(/_v(\d+)/)![1]) - Number(y.match(/_v(\d+)/)![1]));
  const a = readJsonFixture<{ category_configs: Cfg[] }>(pathToFileURL(path.join(DATA_DIR, files[files.length - 1])));
  newest = new Map(a.category_configs.filter((c) => c.list_spec?.code_targets).map((c) => [String(c.category_id), c.list_spec!.code_targets]));
  return newest;
}

/** `asset` with each config's `list_spec.code_targets` set from the newest asset (a copy; configs without a block untouched). */
export function withNewestCodeTargets<T>(asset: T): T {
  const blocks = newestCodeTargets();
  const a = asset as unknown as { category_configs: Cfg[] };
  return {
    ...a,
    category_configs: a.category_configs.map((c) => (blocks.has(String(c.category_id)) && c.list_spec
      ? { ...c, list_spec: { ...c.list_spec, code_targets: structuredClone(blocks.get(String(c.category_id))) } } : c)),
  } as unknown as T;
}
