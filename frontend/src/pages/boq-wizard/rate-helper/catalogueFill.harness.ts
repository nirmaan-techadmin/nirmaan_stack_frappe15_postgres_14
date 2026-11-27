/**
 * CAT-1b (owner 2026-11-26 01:47 "a a a ok", QR-C-1 (a): "CAT-1b adds the TypeScript fill for the test readers (one parity test: TS fill =
 * Python fill on the asset)") -- THE WORDING FILL FOR TEST READERS of a rate FILE. TEST SUPPORT: no product screen reads this (the product
 * reads the served config, already filled by the server, `catalogue_lists.serve_config`).
 *
 * The ONE TypeScript twin of `nirmaan_stack/services/boq_rate_master/catalogue_lists.py`'s fill (`build` -> values / names,
 * `parse_placeholder`, `resolve_placeholder`, `fill_text`, `fill_node`), rule for rule:
 *   {{cat:<attr>=<value>}}        the value exactly as written, when an active SKU carries it on <attr>;
 *   {{item:<item_uid>}}           the SKU's name (the first of item / item_name / description that is set);
 *   {{item:<item_uid>:<attr>}}    that attribute of the SKU;
 *   {{note:<item_uid>}}           the SKU's own note (`item_notes`; CAT-3) -- refused when the SKU is gone or its note is empty;
 *   |lower  |trim                 applied left to right (Python str.lower / str.strip).
 * `catalogueFill.parity.test.ts` pins it to the Python fill byte for byte (the fixture the Python side writes and re-checks).
 *
 * THE ONE DIFFERENCE, on purpose: a placeholder that does not resolve THROWS here (`fillAssetForTests`), naming the place. The product fill
 * prints the value / "an item no longer in the catalogue" and the load gate refuses the file; a test reader must never print braces or a
 * silent stand-in.
 */

export type FillItem = {
  kind?: unknown; brand?: unknown; item_uid?: unknown; active?: unknown; attributes?: Record<string, unknown> | null;
  [k: string]: unknown;
};
export type FillBuilt = { values: Record<string, unknown[]>; names: Record<string, Record<string, string | number>>;
  /** CAT-3: each active SKU's note by item_uid ("" when it has none) */
  notes?: Record<string, string> };
export type FillProblem = [where: string, problem: string];

export const PLACEHOLDER_RE = /\{\{(cat|item|note):([^{}]*)\}\}/g;
const NAME_ATTRS = ["item", "item_name", "description"] as const;
const UNRESOLVED_ITEM_TEXT = "an item no longer in the catalogue";
// Python's str.strip() whitespace (str.isspace), so `|trim` strips exactly what the server strips -- NOT JavaScript's trim(), which also
// takes U+FEFF.
const PY_WS = "\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
const PY_STRIP = new RegExp(`^[${PY_WS}]+|[${PY_WS}]+$`, "g");
export const pyStrip = (s: string): string => s.replace(PY_STRIP, "");

const isScalar = (v: unknown): v is string | number => typeof v === "string" || typeof v === "number";

/** Python `_attrs`: the attributes, plus the brand column as `brand` when the attributes carry none. */
function attrsOf(i: FillItem): Record<string, unknown> {
  const a: Record<string, unknown> = { ...(i.attributes ?? {}) };
  let b = i.brand;
  if (typeof b === "string") b = pyStrip(b);
  if (b !== null && b !== undefined && b !== "" && !("brand" in a)) a.brand = b;
  return a;
}

const isActive = (i: FillItem): boolean => {
  const v = i.active === undefined ? 1 : i.active;
  return !(v === 0 || v === false || v === null || v === "" );
};

/** Python `build(...)["values"]` / `["names"]` from one discipline's items (active only). */
export function buildFillCatalogue(items: FillItem[]): FillBuilt {
  const values: Record<string, Set<unknown>> = {};
  const names: FillBuilt["names"] = {};
  const notes: Record<string, string> = {};
  for (const i of items) {
    if (!isActive(i)) continue;
    const a = attrsOf(i);
    const uid = pyStrip(typeof i.item_uid === "string" ? i.item_uid : "");
    if (uid) {
      const n: Record<string, string | number> = {};
      for (const [k, v] of Object.entries(a)) if (isScalar(v)) n[k] = v;
      names[uid] = n;
      notes[uid] = typeof i.item_notes === "string" ? i.item_notes : "";
    }
    for (const [k, v] of Object.entries(a)) {
      if (isScalar(v) && v !== "") (values[k] ??= new Set()).add(v);
    }
  }
  return { values: Object.fromEntries(Object.entries(values).map(([k, s]) => [k, [...s]])), names, notes };
}

type Parsed = ["cat", string, string, string[]] | ["item", string, string | null, string[]] | ["note", string, null, string[]] | null;

/** Python `parse_placeholder`. */
export function parsePlaceholder(kind: string, body: string): Parsed {
  const parts = body.split("|");
  const head = parts[0];
  const mods = parts.slice(1).map(pyStrip);
  if (mods.some((m) => m !== "lower" && m !== "trim")) return null;
  if (kind === "cat") {
    const eq = head.indexOf("=");
    if (eq < 0) return null;
    const attr = head.slice(0, eq);
    if (!pyStrip(attr)) return null;
    return ["cat", pyStrip(attr), head.slice(eq + 1), mods];
  }
  const bits = head.split(":");
  const uid = pyStrip(bits[0]);
  if (!uid || bits.length > 2) return null;
  if (kind === "note") return bits.length === 1 ? ["note", uid, null, mods] : null;
  const attr = bits.length === 2 && pyStrip(bits[1]) ? pyStrip(bits[1]) : null;
  return ["item", uid, attr, mods];
}

const applyMods = (s: string, mods: string[]): string =>
  mods.reduce((acc, m) => (m === "lower" ? acc.toLowerCase() : pyStrip(acc)), s);

/** Python `item_name`. */
function itemName(names: FillBuilt["names"], uid: string, attr: string | null): string | null {
  const a = names[uid];
  if (a === undefined) return null;
  if (attr) {
    const v = a[attr];
    return v === undefined || v === "" ? null : String(v);
  }
  for (const k of NAME_ATTRS) {
    const v = a[k];
    if (v !== undefined && v !== "") return String(v);
  }
  return null;
}

/** Python `resolve_placeholder`: [text, problem | null]. */
export function resolvePlaceholder(kind: string, body: string, built: FillBuilt): [string, string | null] {
  const p = parsePlaceholder(kind, body);
  if (p === null) return [body, `malformed placeholder '{{${kind}:${body}}}'`];
  if (p[0] === "cat") {
    const [, attr, value, mods] = p;
    const carried = (built.values[attr] ?? []).some((v) => typeof v === "string" && v === value);
    return [applyMods(value, mods), carried ? null : `names ${attr} = '${value}' - no active SKU carries it`];
  }
  if (p[0] === "note") {
    const [, uid, , mods] = p;
    if (built.names[uid] === undefined) return [UNRESOLVED_ITEM_TEXT, `names the note of item ${uid} - no active SKU has that id`];
    const note = built.notes?.[uid] ?? "";
    if (!pyStrip(note)) return [note, `names the note of item ${uid} - that item's note is empty`];
    return [applyMods(note, mods), null];
  }
  const [, uid, attr, mods] = p;
  const name = itemName(built.names, uid, attr);
  if (name === null) return [UNRESOLVED_ITEM_TEXT, `points at item ${uid}${attr ? ` (${attr})` : ""} - no active SKU has that id`];
  return [applyMods(name, mods), null];
}

/** Python `fill_text`. */
export function fillText(s: string, built: FillBuilt, problems?: FillProblem[], where = ""): string {
  if (!s.includes("{{")) return s;
  return s.replace(PLACEHOLDER_RE, (_m, kind: string, body: string) => {
    const [text, prob] = resolvePlaceholder(kind, body, built);
    if (prob && problems) problems.push([where, prob]);
    return text;
  });
}

/** Python `fill_node`: a COPY with every string VALUE filled (keys never). */
export function fillNode<T>(node: T, built: FillBuilt, problems?: FillProblem[], where = ""): T {
  if (typeof node === "string") return fillText(node, built, problems, where) as unknown as T;
  if (Array.isArray(node)) return node.map((v, i) => fillNode(v, built, problems, `${where}[${i}]`)) as unknown as T;
  if (node !== null && typeof node === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(node as Record<string, unknown>)) out[k] = fillNode(v, built, problems, where ? `${where}.${k}` : k);
    return out as T;
  }
  return node;
}

/** True when a parsed JSON value is a rate-master asset file (`items` + `category_configs`). */
export function isRateAsset(x: unknown): x is { items: FillItem[]; category_configs: Array<Record<string, unknown>> } {
  return x !== null && typeof x === "object" && Array.isArray((x as { items?: unknown }).items)
    && Array.isArray((x as { category_configs?: unknown }).category_configs);
}

/**
 * THE TEST READERS' FILL: a rate asset with every config's wording filled from the asset's OWN items (what the server serves for that
 * file once loaded). An asset with no placeholder comes back as the SAME object (every older file). A placeholder that does not resolve
 * THROWS with its place named -- never braces.
 */
export function fillAssetForTests<T>(asset: T): T {
  if (!isRateAsset(asset)) return asset;
  if (!asset.category_configs.some((c) => JSON.stringify(c).includes("{{"))) return asset;
  const built = buildFillCatalogue(asset.items);
  const problems: FillProblem[] = [];
  const configs = asset.category_configs.map((c) => fillNode(c, built, problems, String(c.category_id ?? "?")));
  if (problems.length) {
    throw new Error(`fillAssetForTests: ${problems.length} placeholder(s) do not resolve: `
      + problems.slice(0, 5).map(([w, p]) => `${w} ${p}`).join("; "));
  }
  return { ...asset, category_configs: configs } as T;
}
