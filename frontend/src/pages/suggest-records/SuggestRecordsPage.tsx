/**
 * SRS-2 -- "AI Suggest Records" (route /suggest-records; the sidebar item directly under Rate Master; Admin only: the
 * route is a RoleRoute on RATE_MASTER_ACCESS and every server method checks `_is_nirmaan_admin` first).
 *
 * The approved mockup (SRS-D0, 27 Nov 13:53), its four parts: the filters (run dates default to the last 30 days,
 * project, BoQ, sheet, discipline, category, rates status, run by, a description search) with Apply / Clear and the two
 * Excel downloads; the list (50 a page, server-paged, newest run first) with a coloured status chip; the row detail
 * below (SuggestRecordDetail). READ ONLY: nothing here edits or deletes a record.
 */
import { useState } from "react";
import { Download } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useFrappeGetCall, useFrappePostCall } from "@/lib/frappe";
import { cn } from "@/lib/utils";
import { downloadBase64, downloadErrorMessage, type DownloadPayload } from "@/pages/pricing/rate-master/rateMasterDownload";

import { SuggestRecordDetail } from "./SuggestRecordDetail";
import {
  CAPS_LINE,
  EMPTY_TEXT,
  EXPORT_METHOD,
  LIST_METHOD,
  OPTIONS_METHOD,
  RECORD_METHOD,
  TONE_CLASS,
  defaultFilters,
  filtersPayload,
  lastPage,
  messageOf,
  pagerText,
  rateText,
  runDateText,
  statusTone,
  type FilterOptions,
  type SuggestFilters,
  type SuggestListReply,
  type SuggestRecordDetail as Detail,
} from "./suggestRecordsModel";

const ALL = "__all__";

interface PickProps {
  label: string;
  value: string;
  allLabel: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}

/** One dropdown filter; "All ..." clears it (a Radix item cannot carry an empty value). */
function Pick({ label, value, allLabel, options, onChange }: PickProps) {
  return (
    <label className="flex flex-col gap-1 text-xs text-muted-foreground">
      {label}
      <Select value={value || ALL} onValueChange={(v) => onChange(v === ALL ? "" : v)}>
        <SelectTrigger className="h-8 w-44 text-xs" aria-label={label}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>{allLabel}</SelectItem>
          {options.map((o) => (
            <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  );
}

const plain = (xs: string[] | undefined) => (xs ?? []).map((x) => ({ value: x, label: x }));

/** The page. */
export function SuggestRecordsPage() {
  const [draft, setDraft] = useState<SuggestFilters>(() => defaultFilters());
  const [applied, setApplied] = useState<SuggestFilters>(() => defaultFilters());
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string | null>(null);
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);

  const payload = filtersPayload(applied);
  const { data: listData, isLoading, error } = useFrappeGetCall(LIST_METHOD, { filters: payload, page }, `suggest-records:${payload}:${page}`);
  const { data: optionsData } = useFrappeGetCall(OPTIONS_METHOD, undefined, "suggest-records:options");
  const { data: recordData } = useFrappeGetCall(RECORD_METHOD, { name: selected }, selected ? `suggest-record:${selected}` : null);
  const { call: callExport } = useFrappePostCall(EXPORT_METHOD);

  const list = messageOf<SuggestListReply>(listData);
  const options = messageOf<FilterOptions>(optionsData);
  const record = selected ? messageOf<Detail>(recordData) : null;
  const rows = list?.rows ?? [];
  const total = list?.total ?? 0;
  const set = (k: keyof SuggestFilters) => (v: string) => setDraft((d) => ({ ...d, [k]: v }));

  const apply = () => {
    setApplied(draft);
    setPage(1);
    setSelected(null);
  };
  const clear = () => {
    const d = defaultFilters();
    setDraft(d);
    setApplied(d);
    setPage(1);
    setSelected(null);
  };
  const download = async (kind: "summary" | "full") => {
    setDownloadError(null);
    setDownloading(kind);
    try {
      const res = messageOf<DownloadPayload>(await callExport({ filters: payload, kind }));
      if (res) downloadBase64(res, `ai_suggest_records_${kind}.xlsx`);
    } catch (e: unknown) {
      setDownloadError(downloadErrorMessage(e));
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="flex-1 space-y-4 p-4" data-testid="suggest-records-page">
      <div>
        <h2 className="text-xl font-semibold">AI Suggest Records</h2>
        <p className="text-sm text-muted-foreground">
          Every AI Suggest run, row by row: what was sent to the AI, what it replied, the final attributes and the
          suggested rates. Records are kept for one year, then deleted automatically every night.
        </p>
      </div>

      <div className="space-y-3 rounded-md border p-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            Run date from
            <Input type="date" className="h-8 w-40 text-xs" value={draft.date_from} onChange={(e) => set("date_from")(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            Run date to
            <Input type="date" className="h-8 w-40 text-xs" value={draft.date_to} onChange={(e) => set("date_to")(e.target.value)} />
          </label>
          <Pick label="Project" value={draft.project} allLabel="All projects" options={options?.projects ?? []} onChange={set("project")} />
          <Pick label="BoQ" value={draft.boq} allLabel="All BoQs" options={plain(options?.boqs)} onChange={set("boq")} />
          <Pick label="Sheet" value={draft.sheet_name} allLabel="All sheets" options={plain(options?.sheets)} onChange={set("sheet_name")} />
          <Pick label="Discipline" value={draft.discipline} allLabel="All" options={plain(options?.disciplines)} onChange={set("discipline")} />
          <Pick label="Category" value={draft.category_id} allLabel="All categories" options={plain(options?.categories)} onChange={set("category_id")} />
          <Pick label="Rates" value={draft.rates_status} allLabel="Any status" options={plain(options?.rates_statuses)} onChange={set("rates_status")} />
          <Pick label="Run by" value={draft.run_by} allLabel="Anyone" options={plain(options?.run_by)} onChange={set("run_by")} />
          <label className="flex flex-col gap-1 text-xs text-muted-foreground">
            Search description
            <Input className="h-8 w-48 text-xs" value={draft.search} onChange={(e) => set("search")(e.target.value)} />
          </label>
          <Button size="sm" onClick={apply}>Apply</Button>
          <Button size="sm" variant="outline" onClick={clear}>Clear</Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" disabled={downloading !== null} onClick={() => void download("summary")}>
            <Download className="mr-1 h-4 w-4" /> Download Excel - summary
          </Button>
          <Button size="sm" variant="outline" disabled={downloading !== null} onClick={() => void download("full")}>
            <Download className="mr-1 h-4 w-4" /> Download Excel - full (with AI input and reply)
          </Button>
          <span className="text-xs text-muted-foreground">{CAPS_LINE}</span>
        </div>
        {downloadError ? <p className="text-sm text-red-700" role="alert">{downloadError}</p> : null}
      </div>

      {error ? <p className="text-sm text-red-700" role="alert">{downloadErrorMessage(error)}</p> : null}
      {!isLoading && !error && rows.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid="suggest-records-empty">{EMPTY_TEXT}</p>
      ) : null}

      {rows.length > 0 ? (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run date</TableHead>
                <TableHead>Project</TableHead>
                <TableHead>BoQ</TableHead>
                <TableHead>Sheet</TableHead>
                <TableHead>Excel row</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Final attributes (first 3)</TableHead>
                <TableHead>Supply</TableHead>
                <TableHead>Install</TableHead>
                <TableHead>Combined</TableHead>
                <TableHead>Rates</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow
                  key={r.name}
                  data-testid="suggest-record-row"
                  className={cn("cursor-pointer text-xs", selected === r.name && "bg-muted")}
                  onClick={() => setSelected(r.name)}
                >
                  <TableCell className="whitespace-nowrap">{runDateText(r.run_date)}</TableCell>
                  <TableCell>{r.project_name ?? "-"}</TableCell>
                  <TableCell className="whitespace-nowrap">{r.boq}</TableCell>
                  <TableCell>{r.sheet_name}</TableCell>
                  <TableCell>{r.excel_row}</TableCell>
                  <TableCell className="max-w-xs truncate" title={r.description ?? ""}>{r.description}</TableCell>
                  <TableCell>{r.category_id}</TableCell>
                  <TableCell className="max-w-sm truncate" title={r.first_values}>{r.first_values}</TableCell>
                  <TableCell data-testid="row-supply">{rateText(r.supply_rate)}</TableCell>
                  <TableCell data-testid="row-install">{rateText(r.install_rate)}</TableCell>
                  <TableCell data-testid="row-combined">{rateText(r.combined_rate)}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={cn("whitespace-normal", TONE_CLASS[statusTone(r.rates_status)])}>
                      {r.rates_status ?? "pending"}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <div className="flex items-center justify-between p-2 text-xs text-muted-foreground">
            <span>{pagerText(page, total)}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
              <Button size="sm" variant="outline" disabled={page >= lastPage(total)} onClick={() => setPage((p) => p + 1)}>Next</Button>
            </div>
          </div>
        </div>
      ) : null}

      {record ? <SuggestRecordDetail record={record} /> : null}
    </div>
  );
}

export { SuggestRecordsPage as Component };
export default SuggestRecordsPage;
