"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowUpRight, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge, Button, Card, Empty, ErrorBox, Input, LoadingRows, Notice, PageHeader, StatusBadge } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useToasts } from "@/lib/store";
import type { Alternative, ApprovalItem } from "@/lib/types";

interface ExceptionRow {
  id: number;
  date: string;
  status: string;
  reason: string;
  course_code: string;
  venue_code: string;
  start_min: number;
  end_min: number;
}

function Item({ item }: { item: ApprovalItem }) {
  const client = useQueryClient();
  const push = useToasts((state) => state.push);
  const [comment, setComment] = useState("");
  const [stale, setStale] = useState<{ message: string; alternatives: Alternative[] } | null>(null);
  const decide = useMutation({
    mutationFn: ({ approve }: { approve: boolean }) => (approve ? api(`/approvals/${item.step_id}/approve`, { body: { comment } }) : api(`/approvals/${item.step_id}/reject`, { body: { comment } })),
    onSuccess: (result, vars) => {
      const outcome = (result as { outcome?: string }).outcome;
      push("good", vars.approve ? (outcome === "confirmed" ? "Approved — booking confirmed, passes issued (mock)" : outcome === "partial" ? "Approved, but the bundle is now PARTIAL" : "Step approved") : "Rejected with reason");
      client.invalidateQueries({ queryKey: ["approvals"] });
    },
    onError: (error) => {
      const failure = error as ApiError;
      if (failure.status === 409) setStale({ message: failure.message, alternatives: (failure.data.alternatives as Alternative[]) ?? [] });
      else push("bad", failure.message);
    },
  });
  const booking = item.booking;
  const alternatives = stale?.alternatives.length ? stale.alternatives : item.alternatives;
  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="flex items-center gap-2 text-base font-semibold">
            {booking.event_title}
            {item.escalated && <Badge tone="warn"><ArrowUpRight className="h-3 w-3" /> escalated</Badge>}
          </div>
          <p className="text-xs text-muted">{booking.resource_type.replace("_", " ")} · {fmtDateTime(booking.start)} → {fmtDateTime(booking.end)} · {booking.attendees ?? "?"} people</p>
          {booking.bundle_id && <Link href={`/bundles/${booking.bundle_id}`} className="text-xs text-primary underline">part of bundle #{booking.bundle_id}</Link>}
        </div>
        <div className="flex flex-col items-end gap-1">
          <Badge tone="info">step {item.order}: {item.scope}</Badge>
          {item.due_at && <span className="text-xs text-muted">due {fmtDateTime(item.due_at)}</span>}
        </div>
      </div>
      <div className="mt-3">
        {item.still_valid && !stale ? (
          <Badge tone="good"><CheckCircle2 className="h-3 w-3" /> still valid (re-checked just now)</Badge>
        ) : (
          <Notice tone="warn">
            <strong>Stale — re-run alternatives.</strong> {(stale?.message ?? item.conflicts[0]) || "The booking no longer fits."}
          </Notice>
        )}
      </div>
      {item.violations.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs">
          {item.violations.map((v) => (
            <li key={v.code + v.message} className={v.severity === "hard" ? "text-bad" : "text-warn"}><AlertTriangle className="mr-1 inline h-3 w-3" />{v.message} <Badge tone="info">{v.rule_id}</Badge></li>
          ))}
        </ul>
      )}
      {(!item.still_valid || stale) && alternatives.length > 0 && (
        <ol className="mt-2 space-y-1 text-xs">
          {alternatives.slice(0, 3).map((a, i) => <li key={i} className="rounded border border-line p-2">{a.what_changed} <span className="text-muted">(cost {a.cost}) {a.citations?.join(", ")}</span></li>)}
        </ol>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comment (required to reject)" className="max-w-xs" aria-label="Comment" />
        <Button onClick={() => decide.mutate({ approve: true })} busy={decide.isPending && decide.variables?.approve === true} disabled={!item.still_valid && !stale}>Approve</Button>
        <Button variant="danger" onClick={() => decide.mutate({ approve: false })} busy={decide.isPending && decide.variables?.approve === false} disabled={!comment.trim()}>Reject</Button>
      </div>
    </Card>
  );
}

function Releases() {
  const client = useQueryClient();
  const push = useToasts((state) => state.push);
  const list = useQuery({ queryKey: ["exceptions"], queryFn: () => api<ExceptionRow[]>("/exceptions") });
  const decide = useMutation({
    mutationFn: ({ id, approve, comment }: { id: number; approve: boolean; comment: string }) => (approve ? api(`/exceptions/${id}/approve`, { body: {} }) : api(`/exceptions/${id}/reject`, { body: { comment } })),
    onSuccess: () => { push("good", "Decision recorded"); client.invalidateQueries({ queryKey: ["exceptions"] }); },
    onError: (e) => push("bad", e instanceof Error ? e.message : "Not allowed"),
  });
  const proposed = list.data?.filter((e) => e.status === "PROPOSED") ?? [];
  return (
    <Card title="Class-slot release proposals (HoD or admin)">
      {proposed.length === 0 ? <Empty>No release proposals are waiting.</Empty> : (
        <ul className="space-y-2">
          {proposed.map((e) => (
            <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line p-2 text-sm">
              <span>{e.course_code} in {e.venue_code} on {e.date} <StatusBadge state={e.status} /> <span className="text-xs text-muted">{e.reason}</span></span>
              <span className="flex gap-2"><Button onClick={() => decide.mutate({ id: e.id, approve: true, comment: "" })}>Approve release</Button><Button variant="danger" onClick={() => decide.mutate({ id: e.id, approve: false, comment: "Slot still needed" })}>Reject</Button></span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default function ApprovalsPage() {
  const query = useQuery({ queryKey: ["approvals"], queryFn: () => api<ApprovalItem[]>("/approvals"), refetchInterval: 20000 });
  return (
    <>
      <PageHeader help={["Only steps that are yours to decide are listed.", "Each one is re-checked just now; if the world changed you will see 'stale' and alternatives.", "Approve, or reject with a short reason."]} title="Approvals" subtitle="Only steps inside your scope appear. Every approval re-checks availability and policy first; a stale request must be re-planned instead of approved blindly." />
      {query.isPending && <LoadingRows rows={3} />}
      {query.isError && <ErrorBox error={query.error} />}
      {query.data?.length === 0 && <Empty>Nothing is waiting for you.</Empty>}
      <div className="space-y-3">{query.data?.map((item) => <Item key={item.step_id} item={item} />)}</div>
      <div className="mt-6"><Releases /></div>
    </>
  );
}
