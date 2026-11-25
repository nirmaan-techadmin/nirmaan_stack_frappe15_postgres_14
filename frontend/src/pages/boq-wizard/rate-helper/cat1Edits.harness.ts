/**
 * CAT-1 (HVAC v89): a config of the newest file with v89's edits undone = what v88 held there, the twin of
 * services/boq_rate_master/cat1_undo_support.py (a copy of VAV-FIX's vavfixEdits.harness.ts pointed at cat1Edits.json). `undoVav2c3d` applies it
 * first, then `undoVavfix`, so every older comparison reads v89 as v88 (then v87 ...). Driven by `__fixtures__/cat1Edits.json` alone; a config holding
 * neither v88's nor v89's values is refused. No other harness import (a jsdom test can use it).
 */
import path from "path";
import { pathToFileURL } from "url";
import type { RateCategoryConfig } from "../../pricing/rate-master/rateMasterTypes";
import { readJsonFixture } from "../../pricing/calculatorPanelParity.harness";

type Edit = { c: string; p: Array<string | number>; from: unknown; to: unknown };
const EDITS89 = readJsonFixture<{ configs: Edit[] }>(pathToFileURL(path.resolve(__dirname, "__fixtures__/cat1Edits.json")));
const MISSING = Symbol("missing");

const at = (cfg: unknown, p: ReadonlyArray<string | number>): unknown =>
  p.reduce<unknown>((n, k) => (n === MISSING || n === null || typeof n !== "object" || !(k in (n as object)) ? MISSING : (n as Record<string | number, unknown>)[k]), cfg);
const holds = (cfg: unknown, e: Edit, v: unknown): boolean => {
  const have = at(cfg, e.p);
  return v === null ? have === MISSING : have !== MISSING && JSON.stringify(have) === JSON.stringify(v);
};

/** PURE. `cfg` with v89's edits undone; a v88 (or older) config comes back as it is; one holding some but not all of v89's values throws. A key v89
 *  REMOVES is absent from older files too, so it never counts as a sign of v89. */
export function undoCat1(cfg: RateCategoryConfig): RateCategoryConfig {
  const id = (cfg as unknown as { category_id: string }).category_id;
  const mine = EDITS89.configs.filter((e) => e.c === id);
  if (!mine.length || mine.every((e) => holds(cfg, e, e.from)) || !mine.some((e) => e.to !== null && holds(cfg, e, e.to))) return cfg;
  if (!mine.every((e) => holds(cfg, e, e.to))) throw new Error(`undoCat1: ${id} holds neither v88's nor v89's values`);
  const out = structuredClone(cfg) as unknown as Record<string | number, unknown>;
  for (const e of [...mine].reverse()) {
    const parent = e.p.slice(0, -1).reduce<Record<string | number, unknown>>((n, k) => n[k] as Record<string | number, unknown>, out);
    const last = e.p[e.p.length - 1];
    if (e.from === null) delete parent[last]; else parent[last] = structuredClone(e.from);
  }
  return out as unknown as RateCategoryConfig;
}
