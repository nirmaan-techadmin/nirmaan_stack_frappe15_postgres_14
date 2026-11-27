/**
 * CAT-3 (owner 2026-11-26 00:10, R6; 01:14 "1 approved" -- the mockup; CAT-D1 review caveat 1: the EDIT dialog too). WHAT STOPS
 * WORKING if this row is deactivated or changed: the amber box, the details fold (Admin) and the green "still works" line. It NEVER
 * blocks -- the caller's button reads "Deactivate anyway" / "Save anyway" while the box shows. The list comes from the server
 * (`rate_master_item_usage`, built on CAT-1's reference gate); nothing is decided here.
 */
import { AlertTriangle } from "lucide-react";

export type UsageLine = { config: string; path: string; message: string; line?: string };
export type ItemUsage = {
  action: "deactivate" | "edit";
  will_stop: UsageLine[];
  still_works: number;
  also: UsageLine[];
  labels?: Record<string, string>;
  last_carrier_of?: Array<[string, unknown]>;
  ms?: number;
};

/** True when the box must show (something stops working) -- the caller's button then reads "... anyway". */
export function usageWarns(u: ItemUsage | null | undefined): boolean {
  return !!u && u.will_stop.length > 0;
}

/** Distinct places (config + the path's first two segments) the will-stop lines sit in, for the fold's heading. */
export function usagePlaces(u: ItemUsage): number {
  return new Set(u.will_stop.map((s) => `${s.config}|${s.path.split(".").slice(0, 3).join(".")}`)).size;
}

export const USAGE_COPY = {
  headDeactivate: (label: string) => `This is the only active ${label}. These stop working until the rate file is updated:`,
  headEdit: "This change leaves something without a row that carries it. These stop working until the rate file is updated:",
  tail: "The next rate-file load is refused until these name a stocked item.",
  fold: (places: number, settings: number) => `Details for Admin (${places} place${places === 1 ? "" : "s"}, ${settings} setting${settings === 1 ? "" : "s"})`,
  still: (n: number) => `${n} other setting${n === 1 ? "" : "s"} name values that other rows still carry - they keep working.`,
  nothing: "Nothing stops working: every value this row carries is still carried by another row, and nothing points at this row by itself.",
  also: (n: number) => `${n} worked example${n === 1 ? "" : "s"} name${n === 1 ? "s" : ""} it (information only).`,
  checking: "Checking what uses this row...",
};

export function ItemUsageBox({ usage, label, isAdmin, loading, testId }: {
  usage: ItemUsage | null | undefined;
  label: string;
  isAdmin: boolean;
  loading?: boolean;
  testId?: string;
}) {
  if (loading) return <p className="text-xs text-muted-foreground" data-testid={`${testId ?? "usage"}-loading`}>{USAGE_COPY.checking}</p>;
  if (!usage) return null;
  if (!usageWarns(usage)) {
    return usage.action === "deactivate"
      ? <p className="text-xs text-emerald-700 dark:text-emerald-400" data-testid={`${testId ?? "usage"}-nothing`}>{USAGE_COPY.nothing}</p>
      : null;
  }
  return (
    <div className="space-y-1.5 rounded border border-amber-500/50 bg-amber-50 p-2 text-xs text-amber-950 dark:bg-amber-950/30 dark:text-amber-100" data-testid={testId ?? "usage-box"}>
      <div className="flex gap-1.5 font-medium">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>{usage.action === "edit" ? USAGE_COPY.headEdit : USAGE_COPY.headDeactivate(label)}</span>
      </div>
      <ul className="ml-5 list-disc space-y-0.5">
        {usage.will_stop.map((s, i) => <li key={`${s.config}-${s.path}-${i}`}>{s.line ?? s.message}</li>)}
      </ul>
      <p>{USAGE_COPY.tail}</p>
      {isAdmin ? (
        <details data-testid={`${testId ?? "usage-box"}-fold`}>
          <summary className="cursor-pointer">{USAGE_COPY.fold(usagePlaces(usage), usage.will_stop.length)}</summary>
          <ul className="ml-4 mt-1 space-y-0.5 font-mono text-[11px]">
            {usage.will_stop.map((s, i) => <li key={`d-${i}`}>{s.config} &gt; {s.path} - {s.message}</li>)}
          </ul>
        </details>
      ) : null}
      {usage.still_works > 0 ? <p className="text-emerald-700 dark:text-emerald-400" data-testid={`${testId ?? "usage-box"}-still`}>{USAGE_COPY.still(usage.still_works)}</p> : null}
      {usage.also.length > 0 ? <p className="text-muted-foreground">{USAGE_COPY.also(usage.also.length)}</p> : null}
    </div>
  );
}

/** CAT-3 (R6, the mockup): the CSV preview's section "Values no row will carry after this upload" -- listed, never blocking. */
export function UploadValuesLost({ lost }: {
  lost?: { values: Array<[string, unknown]>; will_stop: UsageLine[] } | null;
}) {
  if (!lost || lost.values.length === 0) return null;
  return (
    <div className="space-y-1 rounded border border-amber-500/50 bg-amber-50 p-2 text-xs text-amber-950 dark:bg-amber-950/30 dark:text-amber-100" data-testid="upload-values-lost">
      <div className="flex gap-1.5 font-medium">
        <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        <span>Values no row will carry after this upload ({lost.values.length})</span>
      </div>
      <ul className="ml-5 list-disc">
        {lost.values.map(([attr, v]) => <li key={`${attr}=${String(v)}`}>{attr}: &quot;{String(v)}&quot;</li>)}
      </ul>
      {lost.will_stop.length > 0 ? (
        <>
          <p>These stop working until the rate file is updated:</p>
          <ul className="ml-5 list-disc">
            {lost.will_stop.map((s, i) => <li key={`ws-${i}`}>{s.line ?? s.message}</li>)}
          </ul>
          <p>The next rate-file load is refused until they are updated. The upload itself is not blocked.</p>
        </>
      ) : null}
    </div>
  );
}
