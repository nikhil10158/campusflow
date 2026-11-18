"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { ApprovalTrail } from "@/components/ApprovalTrail";
import { Badge, Button, Card, Empty, Field, Input, LoadingRows, Notice, PageHeader, cx } from "@/components/ui";
import { API_URL, api, download } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useVenues } from "@/lib/hooks";

interface Entry {
  id: number;
  ts: string;
  actor: string;
  action: string;
  detail: Record<string, unknown>;
  hash: string;
}

interface Mail {
  id: number;
  channel: string;
  recipient: string;
  subject: string;
  body: string;
  created_at: string;
}

type Tab = "audit" | "outbox" | "calendar" | "trail";

function AuditTab() {
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const log = useQuery({ queryKey: ["audit", action, actor], queryFn: () => api<{ items: Entry[] }>("/audit", { params: { action, actor, limit: 150 } }) });
  const verify = useMutation({ mutationFn: () => api<{ ok: boolean; checked: number; broken_at: number | null }>("/audit/verify") });
  return (
    <Card title="Hash-chained audit log" actions={<div className="flex gap-2"><Button variant="outline" onClick={() => download("/exports/audit.xlsx", "audit.xlsx")}>Excel</Button><Button onClick={() => verify.mutate()} busy={verify.isPending}><ShieldCheck className="h-4 w-4" /> Verify chain</Button></div>}>
      {verify.data && <div className="mb-3"><Notice tone={verify.data.ok ? "good" : "bad"}>{verify.data.ok ? `Chain verified: ${verify.data.checked} entries, every hash matches.` : `Chain BROKEN at entry #${verify.data.broken_at}. The log was edited outside the application.`}</Notice></div>}
      <div className="mb-3 flex flex-wrap gap-2"><Field label="Action contains"><Input value={action} onChange={(e) => setAction(e.target.value)} placeholder="agent, approval, booking…" /></Field><Field label="Actor contains"><Input value={actor} onChange={(e) => setActor(e.target.value)} placeholder="email" /></Field></div>
      {log.isPending ? <LoadingRows rows={6} /> : (
        <ul className="divide-y divide-line text-sm">
          {log.data?.items.map((entry) => (
            <li key={entry.id} className="py-1.5">
              <button className="flex w-full items-center gap-2 text-left" onClick={() => setOpen(open === entry.id ? null : entry.id)} aria-expanded={open === entry.id}>
                {open === entry.id ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                <span className="w-10 text-xs text-muted">#{entry.id}</span>
                <Badge tone={entry.action.startsWith("agent") ? "info" : entry.action.includes("approv") || entry.action.includes("confirm") ? "good" : entry.action.includes("reject") || entry.action.includes("forbidden") ? "bad" : "neutral"}>{entry.action}</Badge>
                <span className="truncate text-xs text-muted">{entry.actor}</span>
                <span className="ml-auto shrink-0 text-xs text-muted">{fmtDateTime(entry.ts)}</span>
              </button>
              {open === entry.id && <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-surface2 p-3 text-xs">{JSON.stringify(entry.detail, null, 2)}{"\n"}hash {entry.hash}</pre>}
            </li>
          ))}
          {log.data?.items.length === 0 && <Empty>No entries match.</Empty>}
        </ul>
      )}
    </Card>
  );
}

function OutboxTab() {
  const mail = useQuery({ queryKey: ["outbox"], queryFn: () => api<Mail[]>("/outbox", { params: { limit: 80 } }) });
  return (
    <Card title="Mock outbox (email and WhatsApp are never really sent)">
      {mail.isPending ? <LoadingRows rows={4} /> : mail.data?.length === 0 ? <Empty>No notifications yet.</Empty> : (
        <ul className="space-y-2">
          {mail.data?.map((m) => <li key={m.id} className="rounded-lg border border-line p-2 text-sm"><div className="flex items-center justify-between"><span><Badge tone={m.channel === "whatsapp" ? "good" : "info"}>{m.channel}</Badge> to {m.recipient}</span><span className="text-xs text-muted">{fmtDateTime(m.created_at)}</span></div><div className="font-medium">{m.subject}</div><div className="text-xs text-muted">{m.body}</div></li>)}
        </ul>
      )}
    </Card>
  );
}

function CalendarTab() {
  const { data: venues } = useVenues();
  const token = useQuery({ queryKey: ["ics-token"], queryFn: () => api<{ url: string }>("/ics/token") });
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Your personal feed (token protected)">
        <p className="break-all rounded bg-surface2 p-2 font-mono text-xs">{token.data ? `${API_URL}${token.data.url}` : "…"}</p>
        <p className="mt-2 text-xs text-muted">Subscribe in any calendar app. Only your own confirmed bookings appear.</p>
      </Card>
      <Card title="Venue feeds (busy blocks only)">
        <ul className="grid max-h-72 grid-cols-2 gap-1 overflow-y-auto text-xs">
          {venues?.map((v) => <li key={v.id}><a className={cx("text-link underline")} href={`${API_URL}/ics/venues/${v.code}.ics`}>{v.code}.ics</a></li>)}
        </ul>
      </Card>
    </div>
  );
}

export default function AuditPage() {
  const [tab, setTab] = useState<Tab>("audit");
  return (
    <>
      <PageHeader title="Audit, Outbox and Calendars" subtitle="Every login, search, tool call, approval, import, release and export is chained by hash. Edit one row and verification turns red at that row." />
      <div className="mb-4 flex gap-2" role="tablist">
        {([["audit", "Audit log"], ["trail", "Approval trail"], ["outbox", "Outbox"], ["calendar", "Calendar feeds"]] as [Tab, string][]).map(([key, label]) => (
          <Button key={key} role="tab" aria-selected={tab === key} variant={tab === key ? "primary" : "outline"} onClick={() => setTab(key)}>{label}</Button>
        ))}
      </div>
      {tab === "audit" ? <AuditTab /> : tab === "trail" ? <ApprovalTrail /> : tab === "outbox" ? <OutboxTab /> : <CalendarTab />}
    </>
  );
}
