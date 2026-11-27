/**
 * CAT-3 TEST HARNESS (not product code): label items read from a RAW rate file the way the server does.
 *
 * In the product every item reaches the browser through `get_rate_master_items`, which serves `labels` made by the server's
 * ONE label rule (`catalogue_labels.py`). Tests that read a rate file straight from disk get no served labels, so this
 * harness attaches them from `__fixtures__/catalogueLabels.json` -- the rule's own output per catalogue value, written by
 * the rule and proved equal to it by `test_catalogue_labels` (Python) -- so a test sees exactly what the server serves. A
 * value the fixture does not list gets no label (as the server gives none to a value its rule cannot read).
 */
import fixture from "./__fixtures__/catalogueLabels.json";

type RuleMap = { from_attr: string; scope_kinds: string[]; total: boolean; values: Record<string, string> };
const RULES = (fixture as unknown as { rules: Record<string, RuleMap> }).rules;

type AnyItem = { kind?: unknown; attributes?: Record<string, unknown> | null; labels?: unknown };

/** The labels the server would serve for one item (from the fixture). */
export function fixtureLabels(it: AnyItem): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [id, r] of Object.entries(RULES)) {
    if (!r.scope_kinds.includes(String(it.kind ?? ""))) continue;
    const v = it.attributes?.[r.from_attr];
    if (typeof v === "string" && r.values[v] !== undefined) out[id] = r.values[v];
  }
  return out;
}

/** Items with `labels` attached as the server serves them (an item that already carries labels keeps its own). */
export function withLabels<T extends AnyItem>(items: ReadonlyArray<T>): T[] {
  return items.map((it) => (it.labels !== undefined ? it : ({ ...it, labels: fixtureLabels(it) } as T)));
}
