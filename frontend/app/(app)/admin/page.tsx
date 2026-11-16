"use client";

import { Sparkles, ClipboardCheck, Upload, BarChart3 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { Badge, Button, Card, ErrorBox, Input, LoadingRows, Notice, PageHeader, Stat, ConfirmButton, QuickTiles } from "@/components/ui";
import { api } from "@/lib/api";
import { fmtDateTime, isoLocal } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { useToasts } from "@/lib/store";
import type { AgentStatus, ApprovalItem } from "@/lib/types";

interface Kpis {
  classroom_time_utilisation_pct: number;
  seat_utilisation_pct: number;
  ghost_classes: number;
  ghost_bookable_hours_per_week: number;
  guest_house: { occupancy_pct: number; waitlisted: number };
  bookings: { confirmed: number; held: number; waitlisted: number };
}

export default function AdminHome() {
  const client = useQueryClient();
  const push = useToasts((state) => state.push);
  const { data: now } = useNow();
  const [custom, setCustom] = useState("");
  const kpis = useQuery({ queryKey: ["kpis"], queryFn: () => api<Kpis>("/reports/monthly") });
  const inbox = useQuery({ queryKey: ["approvals"], queryFn: () => api<ApprovalItem[]>("/approvals") });
  const status = useQuery({ queryKey: ["agent-status"], queryFn: () => api<AgentStatus>("/agent/status") });
  const audit = useQuery({ queryKey: ["audit-verify"], queryFn: () => api<{ ok: boolean; checked: number }>("/audit/verify") });

  const setClock = useMutation({
    mutationFn: (value: string) => api<{ expired: number; escalated: number }>("/demo/now", { body: { now: value } }),
    onSuccess: (result) => {
      push("info", `Clock moved. ${result.escalated} step(s) escalated, ${result.expired} hold(s) expired.`);
      client.invalidateQueries();
    },
    onError: (e) => push("bad", e instanceof Error ? e.message : "Could not change the clock"),
  });
  const reset = useMutation({
    mutationFn: () => api("/demo/reset", { method: "POST" }),
    onSuccess: () => { push("good", "Demo state restored"); client.invalidateQueries(); },
  });
  const shift = (hours: number) => {
    if (!now) return;
    const next = new Date(now.now);
    next.setHours(next.getHours() + hours);
    setClock.mutate(isoLocal(next));
  };
  const stale = inbox.data?.filter((i) => !i.still_valid).length ?? 0;
  const escalated = inbox.data?.filter((i) => i.escalated).length ?? 0;

  return (
    <>
      <PageHeader title="Command Center" subtitle="Everything time-based follows the demo clock, so holds, escalations and no-shows can be shown on demand." />
      <QuickTiles items={[
        { href: "/", title: "Ask the planner", icon: Sparkles, text: "Describe an event or a room need in one sentence." },
        { href: "/approvals", title: "Approvals", icon: ClipboardCheck, text: "Decisions waiting for you.", badge: inbox.data?.length ? <Badge tone="warn">{inbox.data.length} waiting</Badge> : undefined },
        { href: "/admin/timetables", title: "Import timetable", icon: Upload, text: "Upload a CSV, Excel or PDF and review changes." },
        { href: "/admin/reports", title: "Ghost classes", icon: BarChart3, text: "Free rooms nobody is using." },
      ]} />
      {kpis.isPending ? <LoadingRows rows={2} /> : kpis.isError ? <ErrorBox error={kpis.error} /> : (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
          <Stat label="Classroom utilisation" value={`${kpis.data.classroom_time_utilisation_pct}%`} />
          <Stat label="Seat utilisation" value={`${kpis.data.seat_utilisation_pct}%`} />
          <Stat label="Ghost classes" value={kpis.data.ghost_classes} tone="warn" />
          <Stat label="Guest house occupancy" value={`${kpis.data.guest_house.occupancy_pct}%`} />
          <Stat label="Pending approvals" value={inbox.data?.length ?? "…"} tone={escalated ? "bad" : undefined} />
        </div>
      )}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Demo clock">
          <p className="mb-2 text-sm">Now: <strong>{now ? fmtDateTime(now.now) : "…"}</strong></p>
          <div className="flex flex-wrap gap-2">
            {[[12, "+12 h"], [24, "+1 day"], [72, "+3 days"]].map(([h, label]) => <Button key={label} variant="outline" onClick={() => shift(Number(h))} busy={setClock.isPending}>{label}</Button>)}
          </div>
          <div className="mt-3 flex gap-2"><Input type="datetime-local" value={custom} onChange={(e) => setCustom(e.target.value)} aria-label="Custom demo time" /><Button onClick={() => custom && setClock.mutate(`${custom}:00`.slice(0, 19))} disabled={!custom}>Set</Button></div>
          <div className="mt-3"><ConfirmButton label="Reset demo data" question="Restore the original demo data?" onConfirm={() => reset.mutate()} busy={reset.isPending} /></div>
        </Card>
        <Card title="Alerts">
          <ul className="space-y-2 text-sm">
            <li className="flex items-center justify-between"><span>Escalated approvals</span><Badge tone={escalated ? "bad" : "good"}>{escalated}</Badge></li>
            <li className="flex items-center justify-between"><span>Stale requests (need alternatives)</span><Badge tone={stale ? "warn" : "good"}>{stale}</Badge></li>
            <li className="flex items-center justify-between"><span>Waitlisted guest requests</span><Badge tone="info">{kpis.data?.guest_house.waitlisted ?? 0}</Badge></li>
            <li className="flex items-center justify-between"><span>Ghost-class hours to recover per week</span><Badge tone="ghost">{kpis.data?.ghost_bookable_hours_per_week ?? 0}</Badge></li>
            <li className="flex items-center justify-between"><span>Audit chain</span>{audit.data ? <Badge tone={audit.data.ok ? "good" : "bad"}>{audit.data.ok ? `verified (${audit.data.checked} entries)` : "BROKEN"}</Badge> : "…"}</li>
          </ul>
          <div className="mt-3 flex flex-wrap gap-2 text-sm"><Link className="text-link underline" href="/approvals">Open approvals</Link><Link className="text-link underline" href="/admin/reports">Ghost classes</Link><Link className="text-link underline" href="/admin/audit">Audit log</Link></div>
        </Card>
        <Card title="AI assistant quota">
          {status.data ? <><p className="text-sm">Mode <Badge tone={status.data.mode === "live" ? "good" : "neutral"}>{status.data.mode}</Badge> {status.data.model && <span className="text-xs text-muted">{status.data.model}</span>}</p><p className="mt-2 text-sm">{status.data.calls_today} of {status.data.daily_limit} calls used today</p>{status.data.mode === "offline" && <Notice tone="info">No Gemini key is set. The deterministic parser and extractive policy answers handle every demo command.</Notice>}</> : <LoadingRows rows={1} />}
        </Card>
        <Card title="Bookings">
          {kpis.data && <div className="grid grid-cols-3 gap-2 text-center"><Stat label="Confirmed" value={kpis.data.bookings.confirmed} tone="good" /><Stat label="Held" value={kpis.data.bookings.held} tone="warn" /><Stat label="Waitlisted" value={kpis.data.bookings.waitlisted} /></div>}
        </Card>
      </div>
    </>
  );
}
