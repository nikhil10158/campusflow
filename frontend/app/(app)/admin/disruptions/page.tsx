"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { CampusMap } from "@/components/CampusMap";
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, LoadingRows, Notice, PageHeader, Select, StatusBadge, ConfirmButton } from "@/components/ui";
import { api } from "@/lib/api";
import { addDays, fmtDateTime } from "@/lib/format";
import { useBuildings, useNow } from "@/lib/hooks";
import { useToasts } from "@/lib/store";

interface Item {
  key: string;
  kind: string;
  label: string;
  venue_code: string;
  date: string;
  start: string;
  severity: string;
  proposal: { venue_code?: string; start?: string; cost?: number; what_changed: string; walk_min?: number } | null;
  alternatives: { what_changed: string; cost: number }[];
}

interface Report {
  disruption_id: number;
  status?: string;
  kind: string;
  affected: number;
  resolved: number;
  unresolved: number;
  items: Item[];
}

const TONE: Record<string, "bad" | "warn" | "info"> = { high: "bad", medium: "warn", low: "info" };

function Body() {
  const params = useSearchParams();
  const { data: now } = useNow();
  const { data: buildings } = useBuildings();
  const push = useToasts((state) => state.push);
  const today = (now?.now ?? "2026-11-16").slice(0, 10);
  const [kind, setKind] = useState("venue");
  const [building, setBuilding] = useState("6");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [description, setDescription] = useState("Lab Complex 1 closed for repairs");
  const [report, setReport] = useState<Report | null>(null);
  const loadId = params.get("id");
  const stored = useQuery({ queryKey: ["disruption", loadId], queryFn: () => api<Report>(`/disruptions/${loadId}`), enabled: !!loadId });
  const shown = report ?? stored.data ?? null;
  const start = from || addDays(today, 2);
  const end = to || addDays(today, 3);

  const assess = useMutation({
    mutationFn: () => api<Report>("/disruptions/assess", { body: { kind, description, start: `${start}T00:00:00`, end: `${addDays(end, 1)}T00:00:00`, building_id: kind === "venue" ? Number(building) : null } }),
    onSuccess: setReport,
  });
  const apply = useMutation({
    mutationFn: () => api<{ changes: number }>(`/disruptions/${shown?.disruption_id}/submit`, { method: "POST" }),
    onSuccess: (result) => { push("good", `Applied ${result.changes} re-home changes; affected people are notified (mock)`); setReport((r) => (r ? { ...r, status: "APPLIED" } : r)); },
    onError: (e) => push("bad", e instanceof Error ? e.message : "Could not apply"),
  });
  const affectedBuildings: Record<number, number> = {};
  if (shown && kind === "venue") affectedBuildings[Number(building)] = shown.affected;

  return (
    <>
      <PageHeader help={["Choose what closed and for which days, then press Assess.", "Every affected class and booking gets a conflict-free new place where one exists.", "Approve the plan to apply it; people are notified (mock)."]} title="Disruption Center" subtitle="Close a building and see every class and booking it breaks with conflict-free re-home proposals. Nothing changes until you approve the whole plan." />
      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <div className="space-y-4">
          <Card title="What happened?">
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); assess.mutate(); }}>
              <Field label="Kind"><Select value={kind} onChange={(e) => setKind(e.target.value)}><option value="venue">Building or venue closed</option></Select></Field>
              <Field label="Building"><Select value={building} onChange={(e) => setBuilding(e.target.value)}>{buildings?.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}</Select></Field>
              <div className="grid grid-cols-2 gap-2"><Field label="First day"><Input type="date" value={start} onChange={(e) => setFrom(e.target.value)} /></Field><Field label="Last day"><Input type="date" value={end} onChange={(e) => setTo(e.target.value)} /></Field></div>
              <Field label="Description"><Input value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
              <Button type="submit" busy={assess.isPending} className="w-full">Assess impact</Button>
            </form>
            {assess.isError && <div className="mt-2"><ErrorBox error={assess.error} /></div>}
          </Card>
          <Card title="Impact map"><CampusMap highlight={affectedBuildings} selected={Number(building)} /></Card>
        </div>
        <div className="space-y-3">
          {assess.isPending && <LoadingRows rows={5} />}
          {!shown && !assess.isPending && <Empty>Run an assessment to see affected classes, bookings and re-home proposals.</Empty>}
          {shown && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex gap-2"><Badge tone="warn">{shown.affected} affected</Badge><Badge tone="good">{shown.resolved} re-homed</Badge><Badge tone={shown.unresolved ? "bad" : "good"}>{shown.unresolved} need a manual decision</Badge>{shown.status && <StatusBadge state={shown.status} />}</div>
                <ConfirmButton variant="primary" label="Approve and apply plan" question="Apply every re-home change?" onConfirm={() => apply.mutate()} busy={apply.isPending} disabled={shown.status === "APPLIED"} />
              </div>
              {shown.unresolved > 0 && <Notice tone="warn">Items without a proposal have no conflict-free alternative right now. Resolve them by hand or widen the options.</Notice>}
              <ul className="space-y-2">
                {shown.items.map((item) => (
                  <li key={item.key} className="rounded-lg border border-line bg-surface p-3 text-sm">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2"><Badge tone={TONE[item.severity]}>{item.severity}</Badge><strong>{item.label}</strong><span className="text-muted">{item.venue_code} · {fmtDateTime(item.start)}</span></div>
                      <Badge>{item.kind}</Badge>
                    </div>
                    {item.proposal ? <p className="mt-1 text-good">→ {item.proposal.what_changed}{item.proposal.walk_min ? ` (${item.proposal.walk_min} min walk)` : ""}</p> : <p className="mt-1 text-bad">No conflict-free re-home found</p>}
                    {item.alternatives.length > 1 && <p className="mt-1 text-xs text-muted">Other options: {item.alternatives.slice(1, 3).map((a) => a.what_changed).join("; ")}</p>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </>
  );
}

export default function DisruptionsPage() {
  return (
    <Suspense fallback={<LoadingRows />}>
      <Body />
    </Suspense>
  );
}
