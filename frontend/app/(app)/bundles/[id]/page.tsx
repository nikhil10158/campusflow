"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, Clock, XCircle } from "lucide-react";
import { use } from "react";

import { Badge, Button, Card, ErrorBox, LoadingRows, Notice, PageHeader, StatusBadge, cx, ConfirmButton } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useToasts } from "@/lib/store";
import type { Booking } from "@/lib/types";

interface BundleDetail {
  id: number;
  title: string;
  status: string;
  components: Booking[];
  timeline: { stage: string; at: string; detail: string }[];
}

const STAGES = ["HELD", "APPROVALS", "CONFIRMED"];
const KIND: Record<string, string> = { venue: "Venue", guest_room: "Guest room", parking: "Parking" };

function stageOf(status: string, bundle: string): number {
  if (bundle === "CONFIRMED") return 2;
  if (status === "CONFIRMED") return 2;
  return 1;
}

export default function BundlePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const client = useQueryClient();
  const push = useToasts((state) => state.push);
  const query = useQuery({ queryKey: ["bundle", id], queryFn: () => api<BundleDetail>(`/bundles/${id}`), refetchInterval: 8000 });
  const cancel = useMutation({
    mutationFn: () => api(`/bundles/${id}/cancel`, { method: "POST" }),
    onSuccess: () => { push("good", "All components released; passes revoked"); client.invalidateQueries({ queryKey: ["bundle", id] }); },
    onError: (e) => push("bad", e instanceof Error ? e.message : "Cancel failed"),
  });
  const accept = useMutation({
    mutationFn: () => api(`/bundles/${id}/accept-partial`, { method: "POST" }),
    onSuccess: () => { push("good", "Partial bundle accepted"); client.invalidateQueries({ queryKey: ["bundle", id] }); },
    onError: (e) => push("bad", e instanceof Error ? e.message : "Could not accept"),
  });

  if (query.isPending) return <LoadingRows rows={5} />;
  if (query.isError) return <ErrorBox error={query.error} />;
  const bundle = query.data;
  const finished = ["CANCELLED", "CONFIRMED", "REJECTED"].includes(bundle.status);

  return (
    <>
      <PageHeader title={bundle.title} subtitle={`Bundle #${bundle.id}: all components are held together and confirmed together or not at all.`} actions={<StatusBadge state={bundle.status} />} />
      {bundle.status === "PARTIAL" && (
        <div className="mb-4">
          <Notice tone="warn">
            One component was rejected, expired or no longer fits. Nothing is silently half-booked. You can accept what is already approved, replace the failed component (ask the Concierge for alternatives), or cancel everything.
          </Notice>
        </div>
      )}
      <Card title="Saga" className="mb-4">
        <ol className="flex flex-wrap items-center gap-3 text-sm">
          {["SUBMITTED", "APPROVALS", bundle.status === "PARTIAL" ? "PARTIAL" : bundle.status === "CANCELLED" ? "CANCELLED" : "CONFIRMED"].map((stage, index) => {
            const reached = bundle.status === "CONFIRMED" || (index === 0) || (index === 1 && !["SUBMITTED"].includes(bundle.status));
            const failed = ["PARTIAL", "CANCELLED", "REJECTED"].includes(stage);
            return (
              <li key={stage} className={cx("flex items-center gap-2 rounded-full px-3 py-1", failed ? "bg-warnbg text-warn" : reached ? "bg-goodbg text-good" : "bg-surface2 text-muted")}>
                {failed ? <XCircle className="h-4 w-4" /> : reached ? <CheckCircle2 className="h-4 w-4" /> : <Circle className="h-4 w-4" />}
                {stage}
              </li>
            );
          })}
        </ol>
      </Card>
      <div className="grid gap-4 lg:grid-cols-3">
        {bundle.components.map((component) => (
          <Card key={component.id} title={<span className="flex items-center gap-2">{KIND[component.resource_type]} <StatusBadge state={component.status} /></span>}>
            <p className="text-sm font-medium">{component.event_title}</p>
            <p className="text-xs text-muted">{fmtDateTime(component.start)} → {fmtDateTime(component.end)}</p>
            {component.hold_expires_at && component.status === "HELD" && <p className="mt-1 flex items-center gap-1 text-xs text-warn"><Clock className="h-3 w-3" /> hold expires {fmtDateTime(component.hold_expires_at)}</p>}
            <ol className="mt-3 space-y-1">
              {component.steps.map((step) => (
                <li key={step.id} className="flex items-center justify-between text-xs">
                  <span>{step.order}. {step.scope}</span>
                  <StatusBadge state={step.status} />
                </li>
              ))}
            </ol>
            {component.steps.some((s) => s.comment && s.status === "REJECTED") && <p className="mt-2 text-xs text-bad">Reason: {component.steps.find((s) => s.status === "REJECTED")?.comment}</p>}
          </Card>
        ))}
      </div>
      <Card title="Timeline" className="mt-4">
        <ul className="space-y-2 text-sm">
          {bundle.timeline.map((event, index) => (
            <li key={index} className="flex items-center gap-2"><Badge tone={event.stage === "REJECTED" ? "bad" : event.stage === "APPROVED" ? "good" : "info"}>{event.stage}</Badge><span className="text-muted">{fmtDateTime(event.at)}</span><span>{event.detail}</span></li>
          ))}
        </ul>
      </Card>
      {!finished && (
        <div className="mt-4 flex flex-wrap gap-2">
          {bundle.status === "PARTIAL" && <Button onClick={() => accept.mutate()} busy={accept.isPending}>Accept partial</Button>}
          <ConfirmButton label="Cancel all (releases every hold)" question="Release every part of this bundle?" onConfirm={() => cancel.mutate()} busy={cancel.isPending} />
        </div>
      )}
    </>
  );
}
