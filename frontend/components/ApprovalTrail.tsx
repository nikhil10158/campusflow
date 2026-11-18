"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";

import { Badge, Card, Empty, ErrorBox, LoadingRows } from "./ui";

interface Row {
  id: number;
  at: string;
  action: string;
  booking_id: number;
  booking_title: string | null;
  resource: string | null;
  actor_name: string;
  actor_id: number | null;
  reason: string;
  scope: string | null;
}

const TONE: Record<string, "good" | "bad" | "warn" | "info" | "neutral"> = { Approved: "good", Confirmed: "good", Rejected: "bad", Cancelled: "bad", Expired: "bad", Escalated: "warn", Updated: "info", Submitted: "neutral", Resubmitted: "info" };

export function ApprovalTrail() {
  const trail = useQuery({ queryKey: ["approval-trail"], queryFn: () => api<{ items: Row[] }>("/audit/approvals", { params: { limit: 200 } }), refetchInterval: 30000 });
  return (
    <Card title="Approval trail">
      <p className="mb-3 text-sm text-muted">Who approved, rejected or updated each booking, when, and why. Only administrators can see this page.</p>
      {trail.isPending ? <LoadingRows rows={5} /> : trail.isError ? <ErrorBox error={trail.error} /> : trail.data.items.length === 0 ? <Empty>No approval activity yet.</Empty> : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead>
              <tr className="border-b border-line text-muted">
                <th className="py-2 pr-3 font-medium">When</th>
                <th className="py-2 pr-3 font-medium">Booking</th>
                <th className="py-2 pr-3 font-medium">Action</th>
                <th className="py-2 pr-3 font-medium">By</th>
                <th className="py-2 font-medium">Reason</th>
              </tr>
            </thead>
            <tbody>
              {trail.data.items.map((row) => (
                <tr key={row.id} className="border-b border-line align-top">
                  <td className="whitespace-nowrap py-2 pr-3 text-muted">{fmtDateTime(row.at)}</td>
                  <td className="py-2 pr-3"><span className="font-medium">#{row.booking_id}</span> {row.booking_title}<span className="block text-xs text-muted">{row.resource}</span></td>
                  <td className="py-2 pr-3"><Badge tone={TONE[row.action] ?? "neutral"}>{row.action}</Badge>{row.scope && <span className="ml-1 text-xs text-muted">{row.scope}</span>}</td>
                  <td className="py-2 pr-3">{row.actor_name}{row.actor_id ? <span className="block text-xs text-muted">ID {row.actor_id}</span> : null}</td>
                  <td className="py-2 text-muted">{row.reason || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
