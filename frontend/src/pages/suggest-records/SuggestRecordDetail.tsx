/**
 * SRS-2 -- one AI Suggest record's detail (the approved mockup's part 3): the row's identity; this row's AI input
 * exactly as sent; the shared AI question (FOLDED); this row's raw reply; the final values with confidence; the
 * suggested rates with their status and stamps. Read only: nothing here edits or deletes.
 */
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

import {
  bcsSupplyText,
  NO_FIGURE,
  TONE_CLASS,
  batchTokensText,
  rateText,
  runDateText,
  statusTone,
  type SuggestRecordDetail as Detail,
} from "./suggestRecordsModel";

interface Props {
  record: Detail;
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2 text-sm">
      <span className="text-muted-foreground min-w-[11rem]">{label}</span>
      <span className="font-medium break-all">{value}</span>
    </div>
  );
}

function Section({ title, open, children, testId }: { title: string; open: boolean; children: ReactNode; testId: string }) {
  return (
    <details open={open} className="rounded-md border p-3" data-testid={testId}>
      <summary className="cursor-pointer text-sm font-semibold">{title}</summary>
      <div className="mt-2">{children}</div>
    </details>
  );
}

const pre = "max-h-96 overflow-auto whitespace-pre-wrap break-all rounded bg-muted p-2 text-xs";

/** The row detail. */
export function SuggestRecordDetail({ record: r }: Props) {
  const tone = statusTone(r.rates.rates_status);
  return (
    <div className="space-y-3" data-testid="suggest-record-detail">
      <h3 className="text-base font-semibold">
        Row detail - {r.boq} / {r.sheet_name} / Excel row {r.excel_row}
      </h3>
      <div className="grid gap-1 rounded-md border p-3 md:grid-cols-2">
        <Field label="Project" value={r.project_name ?? NO_FIGURE} />
        <Field label="BoQ / committed version" value={`${r.boq} / v${r.committed_version ?? "?"}`} />
        <Field label="Row identifier (BoQ node)" value={r.boq_node ?? NO_FIGURE} />
        <Field label="Category / discipline" value={`${r.category_id ?? NO_FIGURE} / ${r.discipline ?? NO_FIGURE}`} />
        <Field label="Description" value={r.description ?? NO_FIGURE} />
        <Field label="Run date / run" value={`${runDateText(r.run_date)} / ${r.run?.suggestion_run ?? NO_FIGURE} (${r.run?.pass_kind ?? "?"})`} />
        <Field label="Run by" value={r.run?.run_by ?? NO_FIGURE} />
        <Field label="Model" value={r.run?.model ?? NO_FIGURE} />
        <Field label="Batch" value={`${r.batch_rows ?? "?"} rows in one AI call; ${batchTokensText(r.batch)}`} />
        <Field label="Catalogue stamp" value={r.catalogue_stamp ?? NO_FIGURE} />
      </div>

      <Section title="AI input - this row's own block, exactly as sent" open testId="detail-input">
        <pre className={pre}>{r.ai_input ?? "(none stored)"}</pre>
      </Section>

      <Section
        title={r.question
          ? `AI question shared by the batch - fingerprint ${r.question.name.slice(0, 12)}... (${r.question.bytes ?? "?"} bytes; stored once, shared by every row and run that sent the same text)`
          : "AI question shared by the batch - none stored"}
        open={false}
        testId="detail-question"
      >
        <pre className={pre}>{r.question?.text ?? ""}</pre>
      </Section>

      <Section title="Raw AI reply - this row's own part" open testId="detail-reply">
        <pre className={pre}>{r.raw_reply ?? "(no reply element for this row)"}</pre>
      </Section>

      <Section title={`Final attributes (${r.final_attributes.length})`} open testId="detail-final">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Attribute</TableHead>
              <TableHead>Value</TableHead>
              <TableHead>Confidence</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {r.final_attributes.map((a) => (
              <TableRow key={a.attribute}>
                <TableCell className="text-xs">{a.attribute}</TableCell>
                <TableCell className="text-xs">{a.value}</TableCell>
                <TableCell className="text-xs">{a.confidence ?? NO_FIGURE}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Section>

      <Section title="Suggested rates (as the helper showed them when the run finished)" open testId="detail-rates">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Supply</TableHead>
              <TableHead>Install</TableHead>
              <TableHead>Combined</TableHead>
              <TableHead>BCS supply</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Priced with</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow>
              <TableCell data-testid="detail-supply">{rateText(r.rates.supply_rate)}</TableCell>
              <TableCell data-testid="detail-install">{rateText(r.rates.install_rate)}</TableCell>
              <TableCell data-testid="detail-combined">{rateText(r.rates.combined_rate)}</TableCell>
              <TableCell data-testid="detail-bcs-supply">{bcsSupplyText(r.rates.bcs_supply_rate)}</TableCell>
              <TableCell>
                <Badge variant="outline" className={cn("whitespace-normal", TONE_CLASS[tone])}>{r.rates.rates_status ?? "pending"}</Badge>
              </TableCell>
              <TableCell className="text-xs break-all">
                catalogue {r.catalogue_stamp ?? NO_FIGURE} / pricing {r.rates.pricing_stamp ?? NO_FIGURE}
              </TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </Section>
    </div>
  );
}
