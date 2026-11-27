/**
 * CAT-3 (HVAC v92): a config of the newest file with v92's edits undone = what v91 held there, the twin of
 * services/boq_rate_master/cat3_undo_support.py. Every v92 config edit REPLACES a string with `{{note:<item_uid>}}`, so undoing it puts v91's
 * string back. `undoVav2c3d` applies it first, then CAT-2's `undoCat2`, so every older comparison reads v92 as v91 (then v90 ...). Driven by
 * `__fixtures__/cat3Edits.json` alone; a config holding neither string is refused. No other harness import (a jsdom test can use it).
 */
import path from "path";
import { pathToFileURL } from "url";
import type { RateCategoryConfig } from "../../pricing/rate-master/rateMasterTypes";
import { readJsonFixture } from "../../pricing/calculatorPanelParity.harness";

type Edit = { c: string; p: Array<string | number>; from: unknown; to: unknown };
const EDITS92 = readJsonFixture<{ configs: Edit[] }>(pathToFileURL(path.resolve(__dirname, "__fixtures__/cat3Edits.json")));
const MISSING = Symbol("missing");

const at = (cfg: unknown, p: ReadonlyArray<string | number>): unknown =>
  p.reduce<unknown>((n, k) => (n === MISSING || n === null || typeof n !== "object" || !(k in (n as object)) ? MISSING : (n as Record<string | number, unknown>)[k]), cfg);

/** PURE. `cfg` with v92's string edits undone; any other string there (v91's or an older file's) comes back as it is; a FOREIGN note
 *  placeholder at that path throws. */
export function undoCat3(cfg: RateCategoryConfig): RateCategoryConfig {
  const id = (cfg as unknown as { category_id: string }).category_id;
  const mine = EDITS92.configs.filter((e) => e.c === id);
  for (const e of mine) {
    const v = at(cfg, e.p);
    if (typeof v === "string" && v.includes("{{note:") && v !== e.to) throw new Error(`undoCat3: ${id} holds a note placeholder that is not v92's`);
  }
  const live = mine.filter((e) => at(cfg, e.p) === e.to);
  if (!live.length) return cfg;
  const out = structuredClone(cfg) as unknown as Record<string | number, unknown>;
  for (const e of live) {
    const parent = e.p.slice(0, -1).reduce<Record<string | number, unknown>>((n, k) => n[k] as Record<string | number, unknown>, out);
    parent[e.p[e.p.length - 1]] = structuredClone(e.from);
  }
  return out as unknown as RateCategoryConfig;
}
