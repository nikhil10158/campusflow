"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, X } from "lucide-react";
import Link from "next/link";
import { QRCodeSVG } from "qrcode.react";
import { createContext, useContext, useState, type ReactNode } from "react";

import { api, ApiError } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useToasts } from "@/lib/store";
import type { Booking } from "@/lib/types";

import { Badge, Button, ErrorBox, Notice, cx } from "./ui";

interface TrailEntry {
  id: number;
  at: string;
  action: string;
  actor_name: string;
  actor_id: number | null;
  reason: string;
  scope: string | null;
}

interface PassRow {
  id: number;
  type: string;
  token: string;
  valid_from: string;
  valid_to: string;
  revoked: boolean;
}

interface Alternative {
  parts: { resource_id: number; resource_code: string; start: string; end: string; attendees: number }[];
  cost: number;
  what_changed: string;
  same_time: boolean;
  same_type: boolean;
  approval_chain: string[];
}

interface Recovery {
  rejection: { reason: string; by: string | null; by_id: number | null; at: string | null; scope: string | null };
  original: { resource_label: string; start: string; end: string; event_title: string; purpose: string; attendees: number };
  alternatives: Alternative[];
  resubmitted_as: number | null;
}

const STEPS = [
  { key: "PENDING", label: "Pending" },
  { key: "UNDER_REVIEW", label: "Under Review" },
  { key: "DECIDED", label: "Approved" },
];

export function StatusStepper({ status }: { status: string }) {
  const rejected = status === "REJECTED";
  const current = status === "PENDING" ? 0 : status === "UNDER_REVIEW" ? 1 : 2;
  return (
    <ol className="flex flex-wrap items-center gap-2 text-sm" aria-label="Request progress">
      {STEPS.map((step, index) => {
        const reached = index <= current;
        const last = index === 2;
        const label = last && rejected ? "Rejected" : step.label;
        const bad = last && rejected;
        return (
          <li key={step.key} className="flex items-center gap-2">
            <span className={cx("flex items-center gap-1.5 rounded-full px-3 py-1 font-medium", !reached ? "bg-surface2 text-muted" : bad ? "bg-badbg text-bad" : last ? "bg-goodbg text-good" : "bg-tint text-link")}>
              {reached && (bad ? <X className="h-3.5 w-3.5" aria-hidden /> : <Check className="h-3.5 w-3.5" aria-hidden />)}
              {label}
            </span>
            {index < 2 && <span className={cx("h-0.5 w-5 rounded", index < current ? "bg-primary" : "bg-line")} aria-hidden />}
          </li>
        );
      })}
    </ol>
  );
}

function Updates({ id, live }: { id: number; live: boolean }) {
  const trail = useQuery({ queryKey: ["trail", id], queryFn: () => api<TrailEntry[]>(`/bookings/${id}/trail`), refetchInterval: live ? 15000 : false });
  if (trail.isPending) return <p className="text-sm text-muted">Loading updates…</p>;
  if (trail.isError) return <ErrorBox error={trail.error} />;
  if (trail.data.length === 0) return <p className="text-sm text-muted">No updates yet.</p>;
  return (
    <ul className="space-y-1.5 text-sm">
      {trail.data.map((entry) => (
        <li key={entry.id} className="flex flex-wrap items-baseline gap-x-2">
          <Badge tone={entry.action === "Rejected" ? "bad" : entry.action === "Approved" || entry.action === "Confirmed" ? "good" : "info"}>{entry.action}</Badge>
          <span>{entry.actor_name}{entry.scope ? ` (${entry.scope})` : ""}</span>
          <span className="text-xs text-muted">{fmtDateTime(entry.at)}</span>
          {entry.reason && <span className="basis-full text-muted">Reason: {entry.reason}</span>}
        </li>
      ))}
    </ul>
  );
}

function BookingPass({ booking }: { booking: Booking }) {
  const passes = useQuery({ queryKey: ["passes", booking.id], queryFn: () => api<PassRow[]>("/passes", { params: { booking_id: booking.id } }) });
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  if (passes.isPending) return <p className="text-sm text-muted">Loading pass…</p>;
  if (passes.isError) return <ErrorBox error={passes.error} />;
  if (passes.data.length === 0) return <p className="text-sm text-muted">No pass has been issued for this booking.</p>;
  return (
    <div className="flex flex-wrap gap-4">
      {passes.data.map((pass) => (
        <div key={pass.id} className="flex items-center gap-4 rounded-xl border border-line bg-surface p-3">
          <div className="rounded-lg bg-white p-2">
            <QRCodeSVG value={`${origin}/pass/${pass.token}`} size={104} />
          </div>
          <div className="text-sm">
            <p className="font-semibold">{booking.event_title}</p>
            <p className="text-muted">Pass #{pass.id} · {pass.type}</p>
            <p className="text-muted">{fmtDateTime(pass.valid_from)} to {fmtDateTime(pass.valid_to)}</p>
            <div className="mt-1 flex items-center gap-2">
              <Badge tone={pass.revoked ? "bad" : "good"}>{pass.revoked ? "Revoked" : "Valid booking pass"}</Badge>
              <Link href={`/pass/${pass.token}`} className="text-xs text-link underline">Open pass</Link>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function RejectionRecovery({ booking }: { booking: Booking }) {
  const client = useQueryClient();
  const push = useToasts((state) => state.push);
  const [picked, setPicked] = useState<number | null>(null);
  const recovery = useQuery({ queryKey: ["recovery", booking.id], queryFn: () => api<Recovery>(`/bookings/${booking.id}/recovery`) });
  const resubmit = useMutation({
    mutationFn: (choice: Alternative | null) => api<Booking>(`/bookings/${booking.id}/resubmit`, { body: choice ? { resource_id: choice.parts[0].resource_id, start: choice.parts[0].start, end: choice.parts[0].end } : {} }),
    onSuccess: (created) => {
      push("good", `Resubmitted as request #${created.id}. It follows the normal approval process.`);
      client.invalidateQueries();
    },
    onError: (problem) => push("bad", problem instanceof ApiError ? problem.message : "Could not resubmit"),
  });
  if (recovery.isPending) return <p className="text-sm text-muted">Loading what you can do next…</p>;
  if (recovery.isError) return <ErrorBox error={recovery.error} />;
  const data = recovery.data;
  return (
    <div className="space-y-3">
      <Notice tone="bad">
        <span className="block font-semibold">Why it was rejected</span>
        <span className="block">{data.rejection.reason || "No reason was given."}</span>
        <span className="mt-1 block text-xs">{data.rejection.by ? `By ${data.rejection.by}` : ""}{data.rejection.scope ? ` (${data.rejection.scope})` : ""}{data.rejection.at ? ` · ${fmtDateTime(data.rejection.at)}` : ""}</span>
      </Notice>
      {data.resubmitted_as ? (
        <Notice tone="good">Already resubmitted as request #{data.resubmitted_as}.</Notice>
      ) : (
        <>
          <p className="text-sm text-muted">Your details are kept: {data.original.event_title}, {data.original.attendees} people, {data.original.resource_label}, {fmtDateTime(data.original.start)} to {fmtDateTime(data.original.end)}. Pick another option and resubmit; nothing needs retyping.</p>
          {data.alternatives.length === 0 ? (
            <Notice tone="warn">No free alternative was found for these requirements. You can still resubmit the original request.</Notice>
          ) : (
            <ul className="space-y-2" role="radiogroup" aria-label="Alternatives">
              {data.alternatives.map((option, index) => (
                <li key={index}>
                  <button
                    role="radio"
                    aria-checked={picked === index}
                    onClick={() => setPicked(index)}
                    className={cx("flex w-full flex-wrap items-center justify-between gap-2 rounded-xl border p-3 text-left text-sm transition", picked === index ? "border-primary bg-tint" : "border-line bg-surface hover:border-primary")}
                  >
                    <span>
                      <span className="block font-semibold">{option.parts[0].resource_code} · {fmtDateTime(option.parts[0].start)} to {fmtDateTime(option.parts[0].end)}</span>
                      <span className="block text-muted">{option.what_changed}</span>
                    </span>
                    <span className="flex items-center gap-1.5">
                      {option.same_time && <Badge tone="good">Same date and time</Badge>}
                      {!option.same_type && <Badge tone="warn">Different room type</Badge>}
                      <Badge>{option.parts[0].attendees} people</Badge>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => picked !== null && resubmit.mutate(data.alternatives[picked])} disabled={picked === null} busy={resubmit.isPending}>Resubmit with selected option</Button>
            <Button variant="outline" onClick={() => resubmit.mutate(null)} busy={resubmit.isPending}>Resubmit original</Button>
          </div>
        </>
      )}
    </div>
  );
}

const TrackContext = createContext<{ open: boolean; toggle: () => void } | null>(null);

export function TrackToggle() {
  const track = useContext(TrackContext);
  if (!track) return null;
  return (
    <button onClick={track.toggle} aria-expanded={track.open} className="flex items-center gap-1 text-xs text-link underline">
      Track <ChevronDown className={cx("h-3 w-3 transition-transform", track.open && "rotate-180")} aria-hidden />
    </button>
  );
}

export function RequestRow({ booking, className, children }: { booking: Booking; className: string; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const status = booking.track?.status ?? booking.status;
  const showStepper = ["PENDING", "UNDER_REVIEW", "APPROVED", "REJECTED"].includes(status);
  return (
    <TrackContext.Provider value={{ open, toggle: () => setOpen(!open) }}>
      <li className={className}>{children}</li>
      {open && (
        <li className="slide space-y-3 rounded-xl border border-line bg-surface2 p-3">
          {showStepper ? <StatusStepper status={status} /> : <p className="text-sm text-muted">Status: {booking.status.replace(/_/g, " ").toLowerCase()}</p>}
          <Updates id={booking.id} live={open} />
          {status === "APPROVED" && <BookingPass booking={booking} />}
          {status === "REJECTED" && <RejectionRecovery booking={booking} />}
        </li>
      )}
    </TrackContext.Provider>
  );
}
