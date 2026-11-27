/**
 * CAT-3 (owner 2026-11-26 00:11 / 00:53, R1 / R2): CATALOGUE LABELS, read from the served items.
 *
 * A label (`conductor = al`, `poles = 3`, `cloth_cladding = cloth`) is made on the SERVER from each catalogue row's own
 * values by ONE rule (`nirmaan_stack/services/boq_rate_master/catalogue_labels.py`) and served on every item as `labels`
 * (`get_rate_master_items`). Code that recognises a GROUP of rows names the LABEL VALUE through `labelValue` and finds the
 * catalogue's own spelling through `valueCarrying` -- so a new SKU is recognised with nobody typing anything, and no
 * catalogue spelling is typed here. This module NEVER computes a label: it only reads what the server served.
 *
 * `LABEL_VALUES` is the closed set of label values the rule makes (a reader can name nothing else -- `labelValue` is typed
 * on it); `test_catalogue_labels` (Python) and `catalogueLabels.test.ts` prove it equals the rule's own list.
 */

/** The label values the server's rule makes, per label id (poles 1+N / 3+N: dormant -- no SKU carries them yet). */
export const LABEL_VALUES = {
  conductor: ["al", "cu"],
  armour: ["unarmoured", "armoured"],
  poles: ["1", "2", "3", "4", "1+N", "3+N"],
  cloth_cladding: ["cloth", "cloth_on_aluminium"],
} as const;

/** The attribute each label is made from (attribute ids are the config's own words, not catalogue values; for DISPLAY only -- the
 * Rate Master chip shows the row's own value of this attribute). `test_catalogue_labels` proves it equals the rule's `from_attr`. */
export const LABEL_FROM = {
  conductor: "material",
  armour: "insulation",
  poles: "pole",
  cloth_cladding: "cladding",
  cladding_gauge: "cladding",
} as const;
/** Labels whose value is CAPTURED from the row's value (the gauge digits), shown as captured. */
export const CAPTURE_LABELS: ReadonlySet<string> = new Set(["cladding_gauge"]);

export type LabelId = keyof typeof LABEL_VALUES;
export type LabelValue<K extends LabelId> = (typeof LABEL_VALUES)[K][number];
/** The served `labels` map of one item ({label id: value}); `cladding_gauge` carries a captured gauge ("24"). */
export type ItemLabels = Partial<Record<LabelId | "cladding_gauge", string>>;

type Labelled = { labels?: ItemLabels | Record<string, string> | null; attributes?: Record<string, unknown> | null };

/** The checked spelling of a label value a reader names (typed on `LABEL_VALUES`). */
export function labelValue<K extends LabelId>(_id: K, v: LabelValue<K>): string {
  return v;
}

/** One item's label for `id`, as served (undefined when the item carries none). */
export function itemLabel(it: Labelled, id: LabelId | "cladding_gauge"): string | undefined {
  const v = (it.labels as Record<string, string> | null | undefined)?.[id];
  return typeof v === "string" ? v : undefined;
}

/**
 * PURE. The catalogue value of `attr` carried by the items whose labels match every pair in `want` -- the ONE distinct
 * value, else undefined (none carries it, or two different spellings do: the reader then treats it as not stocked rather
 * than guess). `["armour", "armoured"]` over the cable SKUs gives their own "armoured" spelling.
 */
export function valueCarrying(
  items: ReadonlyArray<Labelled>,
  want: Partial<Record<LabelId | "cladding_gauge", string>>,
  attr: string,
): string | undefined {
  const pairs = Object.entries(want).filter(([, v]) => v !== undefined) as Array<[LabelId | "cladding_gauge", string]>;
  const seen = new Set<string>();
  for (const it of items) {
    if (!pairs.every(([id, v]) => itemLabel(it, id) === v)) continue;
    const raw = it.attributes?.[attr];
    if (typeof raw === "string" && raw !== "") seen.add(raw);
  }
  return seen.size === 1 ? Array.from(seen)[0] : undefined;
}
