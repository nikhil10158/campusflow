"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileUp } from "lucide-react";
import { useRef, useState, type DragEvent } from "react";

import { Badge, Button, Card, Empty, ErrorBox, LoadingRows, Notice, PageHeader, StatusBadge, cx, ConfirmButton } from "@/components/ui";
import { api, download } from "@/lib/api";
import { WEEKDAYS, minToHHMM } from "@/lib/format";
import { useToasts } from "@/lib/store";

interface Issue {
  severity: string;
  code: string;
  message: string;
  suggested_fix: string;
}

interface Preview {
  job_id: number;
  status: string;
  filename: string;
  format: string;
  rows: number;
  ai_extracted: boolean;
  notes: string[];
  clarifications: { id: string; question: string; options: string[] }[];
  issues: Issue[];
  errors: number;
  warnings: number;
  diff: { sections: number[]; added: { course: string; weekday: number; start_min: number; venue: string }[]; removed: { course: string; weekday: number; start_min: number; venue: string }[]; moved: { course: string; from: { weekday: number; start_min: number; venue: string }; to: { weekday: number; start_min: number; venue: string } }[]; unchanged: number };
  affected_bookings: { booking_id: number; title: string; start: string; conflicts_with: string }[];
  ready_to_import: boolean;
}

interface Version {
  id: number;
  source_file: string;
  format: string;
  status: string;
  created_at: string;
  entries: number;
  errors: number;
}

export default function TimetableImportPage() {
  const client = useQueryClient();
  const push = useToasts((state) => state.push);
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const samples = useQuery({ queryKey: ["samples"], queryFn: () => api<{ name: string; size: number }[]>("/timetables/samples") });
  const versions = useQuery({ queryKey: ["versions"], queryFn: () => api<Version[]>("/timetables/versions") });

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api<Preview>("/timetables/upload", { form });
    },
    onSuccess: setPreview,
  });
  const answer = useMutation({ mutationFn: ({ id, value }: { id: string; value: string }) => api<Preview>(`/timetables/${preview?.job_id}/answer`, { body: { answers: { [id]: value } } }), onSuccess: setPreview });
  const approve = useMutation({
    mutationFn: () => api(`/timetables/${preview?.job_id}/import`, { method: "POST" }),
    onSuccess: () => { push("good", "Timetable imported as the new active version"); setPreview(null); client.invalidateQueries(); },
    onError: (e) => push("bad", e instanceof Error ? e.message : "Import blocked"),
  });
  const rollback = useMutation({
    mutationFn: (id: number) => api(`/timetables/versions/${id}/rollback`, { method: "POST" }),
    onSuccess: () => { push("good", "Previous version restored"); client.invalidateQueries(); },
    onError: (e) => push("bad", e instanceof Error ? e.message : "Rollback failed"),
  });

  function drop(event: DragEvent) {
    event.preventDefault();
    setOver(false);
    const file = event.dataTransfer.files[0];
    if (file) upload.mutate(file);
  }

  return (
    <>
      <PageHeader help={["Drop a CSV, Excel grid or PDF. Nothing is changed yet.", "Answer any questions and fix any errors shown.", "Check the differences, then press Approve import. You can roll back later."]} title="Timetable Ingestion" subtitle="CSV lists, Excel grids and PDF grids are parsed, normalised, validated and previewed. Nothing becomes active until an administrator approves the import." />
      <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          <div
            onDragOver={(e) => { e.preventDefault(); setOver(true); }}
            onDragLeave={() => setOver(false)}
            onDrop={drop}
            className={cx("flex flex-col items-center gap-2 rounded-xl border-2 border-dashed p-8 text-center", over ? "border-primary bg-primary/5" : "border-line")}
          >
            <FileUp className="h-8 w-8 text-muted" aria-hidden />
            <p className="text-sm">Drop a timetable file here, or</p>
            <Button variant="outline" onClick={() => input.current?.click()} busy={upload.isPending}>Choose a file</Button>
            <input ref={input} type="file" accept=".csv,.xlsx,.pdf" hidden onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} />
          </div>
          {upload.isError && <ErrorBox error={upload.error} />}
          {preview && (
            <Card title={<span className="flex items-center gap-2">{preview.filename} <Badge tone="info">{preview.format.replace("_", " ")}</Badge> {preview.ai_extracted && <Badge tone="ghost">AI-extracted — please review</Badge>}</span>}>
              <div className="flex flex-wrap gap-2 text-sm"><Badge>{preview.rows} rows</Badge><Badge tone={preview.errors ? "bad" : "good"}>{preview.errors} errors</Badge><Badge tone={preview.warnings ? "warn" : "good"}>{preview.warnings} warnings</Badge><StatusBadge state={preview.status} /></div>
              {preview.clarifications.length > 0 && (
                <div className="mt-3 space-y-2">
                  {preview.clarifications.map((c) => (
                    <div key={c.id} className="rounded-lg border border-primary/40 p-3">
                      <p className="mb-2 text-sm font-medium">{c.question}</p>
                      <div className="flex flex-wrap gap-2">{c.options.map((o) => <button key={o} onClick={() => answer.mutate({ id: c.id, value: o })} className="chip">{o}</button>)}</div>
                    </div>
                  ))}
                </div>
              )}
              {preview.issues.length > 0 && (
                <ul className="mt-3 space-y-1 text-sm">
                  {preview.issues.map((i, idx) => <li key={idx} className="rounded-lg border border-line p-2"><Badge tone={i.severity === "error" ? "bad" : "warn"}>{i.code}</Badge> {i.message}<div className="text-xs text-muted">Fix: {i.suggested_fix}</div></li>)}
                </ul>
              )}
              <div className="mt-3 grid gap-3 md:grid-cols-3 text-sm">
                <div><div className="text-xs text-muted">Unchanged</div><div className="text-xl font-semibold">{preview.diff.unchanged}</div></div>
                <div><div className="text-xs text-muted">Added / removed</div><div className="text-xl font-semibold">{preview.diff.added.length} / {preview.diff.removed.length}</div></div>
                <div><div className="text-xs text-muted">Moved</div><div className="text-xl font-semibold">{preview.diff.moved.length}</div></div>
              </div>
              {[...preview.diff.added.map((a) => `+ ${a.course} ${WEEKDAYS[a.weekday]} ${minToHHMM(a.start_min)} ${a.venue}`), ...preview.diff.removed.map((a) => `- ${a.course} ${WEEKDAYS[a.weekday]} ${minToHHMM(a.start_min)} ${a.venue}`), ...preview.diff.moved.map((m) => `~ ${m.course}: ${WEEKDAYS[m.from.weekday]} ${minToHHMM(m.from.start_min)} ${m.from.venue} → ${WEEKDAYS[m.to.weekday]} ${minToHHMM(m.to.start_min)} ${m.to.venue}`)].slice(0, 20).map((line) => <p key={line} className="font-mono text-xs">{line}</p>)}
              {preview.affected_bookings.length > 0 && <div className="mt-3"><Notice tone="warn">{preview.affected_bookings.length} booking(s) would clash with the new timetable: {preview.affected_bookings.map((b) => `#${b.booking_id} ${b.title}`).join(", ")}</Notice></div>}
              <div className="mt-4 flex items-center gap-2">
                <ConfirmButton variant="primary" label="Approve import" question="Make this the active timetable?" onConfirm={() => approve.mutate()} busy={approve.isPending} disabled={!preview.ready_to_import} />
                <Button variant="ghost" onClick={() => setPreview(null)}>Discard</Button>
                {!preview.ready_to_import && <span className="text-xs text-muted">Answer every question and fix every error first.</span>}
              </div>
            </Card>
          )}
        </div>
        <div className="space-y-4">
          <Card title="Sample files (synthetic)">
            {samples.data?.map((s) => <div key={s.name} className="flex items-center justify-between py-1 text-sm"><span>{s.name}</span><Button variant="ghost" onClick={() => download(`/timetables/samples/${s.name}`, s.name)}>Download</Button></div>)}
          </Card>
          <Card title="Version history">
            {versions.isPending ? <LoadingRows rows={3} /> : versions.data?.length === 0 ? <Empty>No versions</Empty> : (
              <ul className="space-y-2">
                {versions.data?.map((v) => (
                  <li key={v.id} className="flex items-center justify-between rounded-lg border border-line p-2 text-sm">
                    <span>v{v.id} · {v.source_file}<div className="text-xs text-muted">{v.entries} entries · {v.format}</div></span>
                    <span className="flex items-center gap-2"><StatusBadge state={v.status} />{v.status === "ARCHIVED" && <ConfirmButton variant="outline" label="Roll back" question="Restore this version?" onConfirm={() => rollback.mutate(v.id)} />}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

