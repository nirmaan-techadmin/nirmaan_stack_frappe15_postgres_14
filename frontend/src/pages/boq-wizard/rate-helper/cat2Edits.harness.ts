/**
 * CAT-2 (HVAC v91): a config of the newest file with v91's edits undone = what v90 held there, the twin of
 * services/boq_rate_master/cat2_undo_support.py (a copy of CAT-1's cat1Edits.harness.ts pointed at cat2Edits.json). Every v91 edit ADDS
 * `list_spec.code_targets`, so undoing it removes the key. `undoVav2c3d` applies it first, then CAT-1's `undoCat1`, then `undoVavfix`, so
 * every older comparison reads v91 as v90 (then v89 ...). Driven by `__fixtures__/cat2Edits.json` alone; a config holding a block that is
 * not v91's is refused. No other harness import (a jsdom test can use it).
 */
import path from "path";
import { pathToFileURL } from "url";
import type { RateCategoryConfig } from "../../pricing/rate-master/rateMasterTypes";
import { readJsonFixture } from "../../pricing/calculatorPanelParity.harness";

type Edit = { c: string; p: Array<string | number>; from: unknown; to: unknown };
const EDITS91 = readJsonFixture<{ configs: Edit[] }>(pathToFileURL(path.resolve(__dirname, "__fixtures__/cat2Edits.json")));
const MISSING = Symbol("missing");

const at = (cfg: unknown, p: ReadonlyArray<string | number>): unknown =>
  p.reduce<unknown>((n, k) => (n === MISSING || n === null || typeof n !== "object" || !(k in (n as object)) ? MISSING : (n as Record<string | number, unknown>)[k]), cfg);

/** PURE. `cfg` with v91's added key removed; a v90 (or older) config comes back as it is; one holding a different block throws. */
export function undoCat2(cfg: RateCategoryConfig): RateCategoryConfig {
  const id = (cfg as unknown as { category_id: string }).category_id;
  const mine = EDITS91.configs.filter((e) => e.c === id);
  if (!mine.length || mine.every((e) => at(cfg, e.p) === MISSING)) return cfg;
  if (!mine.every((e) => e.from === null && JSON.stringify(at(cfg, e.p)) === JSON.stringify(e.to))) throw new Error(`undoCat2: ${id} holds a code_targets block that is not v91's`);
  const out = structuredClone(cfg) as unknown as Record<string | number, unknown>;
  for (const e of [...mine].reverse()) {
    const parent = e.p.slice(0, -1).reduce<Record<string | number, unknown>>((n, k) => n[k] as Record<string | number, unknown>, out);
    delete parent[e.p[e.p.length - 1]];
  }
  return out as unknown as RateCategoryConfig;
}
