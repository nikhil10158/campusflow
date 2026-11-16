"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { api } from "@/lib/api";
import { addDays, slotToHHMM } from "@/lib/format";
import { useNow, useVenues } from "@/lib/hooks";
import { proposalFromCheck, type BookingBody, type CheckResponse } from "@/lib/proposal";
import type { Proposal, Segment, Venue } from "@/lib/types";

import { ProposalCard } from "./ProposalCard";
import { Badge, Button, Card, ErrorBox, Field, Input, LoadingRows, PageHeader, Select } from "./ui";

interface Props {
  type: "lab" | "amphitheatre";
  title: string;
  subtitle: string;
  rules: { rule: string; text: string }[];
  chain: string[];
}

export function VenueModule({ type, title, subtitle, rules, chain }: Props) {
  const { data: venues, isPending } = useVenues(type);
  const { data: now } = useNow();
  const today = (now?.now ?? "2026-11-16").slice(0, 10);
  const [venueId, setVenueId] = useState<number | null>(null);
  const [day, setDay] = useState("");
  const [start, setStart] = useState("14:00");
  const [end, setEnd] = useState("17:00");
  const [attendees, setAttendees] = useState(30);
  const [name, setName] = useState("Practice session");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const selected: Venue | undefined = venues?.find((v) => v.id === venueId) ?? venues?.[0];
  const date = day || addDays(today, type === "lab" ? 4 : 5);

  const calendar = useQuery({
    queryKey: ["module-calendar", selected?.id, today],
    queryFn: () => api<{ days: { date: string; segments: Segment[] }[] }>(`/availability/venue/${selected?.id}`, { params: { date_from: today, days: 7 } }),
    enabled: !!selected,
  });

  const check = useMutation({
    mutationFn: async () => {
      if (!selected) throw new Error("Choose a room");
      const body: BookingBody = { resource_type: "venue", resource_id: selected.id, start: `${date}T${start}:00`, end: `${date}T${end}:00`, event_title: name, attendees };
      const result = await api<CheckResponse>("/proposals/check", { body });
      return proposalFromCheck(result, body, selected.code);
    },
    onSuccess: setProposal,
  });

  return (
    <>
      <PageHeader title={title} subtitle={subtitle} actions={<Link href="/" className="text-sm text-link underline">Ask the Concierge instead</Link>} />
      <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
        <div className="space-y-4">
          <Card title="Approval chain">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              {chain.map((step, index) => (
                <span key={step} className="inline-flex items-center gap-2">
                  <Badge tone="info">{step}</Badge>
                  {index < chain.length - 1 && <ArrowRight className="h-4 w-4 text-muted" aria-hidden />}
                </span>
              ))}
              <Badge tone="good">Confirmed + pass</Badge>
            </div>
            <ul className="mt-3 space-y-1 text-xs text-muted">
              {rules.map((r) => (
                <li key={r.rule}><Badge tone="info">{r.rule}</Badge> {r.text}</li>
              ))}
            </ul>
          </Card>
          <Card title={`${title} (${venues?.length ?? "…"})`}>
            {isPending && <LoadingRows rows={4} />}
            <div className="grid gap-2 md:grid-cols-2">
              {venues?.map((venue) => (
                <button key={venue.id} onClick={() => setVenueId(venue.id)} className={`rounded-lg border p-3 text-left ${selected?.id === venue.id ? "border-primary bg-primary/5" : "border-line hover:bg-surface2"}`}>
                  <div className="flex items-center justify-between"><span className="font-semibold">{venue.code}</span><span className="text-xs text-muted">seats {venue.capacity}</span></div>
                  <div className="text-xs text-muted">{venue.name}</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {venue.features.map((f) => <Badge key={f}>{f}</Badge>)}
                    {venue.lab_type && <Badge tone="info">{venue.lab_type}</Badge>}
                    {venue.needs_supervisor && <Badge tone="warn">supervisor</Badge>}
                  </div>
                  {venue.eligible_depts.length > 0 && <div className="mt-1 text-xs text-muted">Open to {venue.eligible_depts.join(", ")}</div>}
                  <div className="mt-1 text-xs text-muted">Buffers {venue.setup_buffer_min}/{venue.teardown_buffer_min} min</div>
                </button>
              ))}
            </div>
          </Card>
          {selected && (
            <Card title={`Next 7 days · ${selected.code}`}>
              {calendar.isPending ? <LoadingRows rows={3} /> : (
                <ul className="space-y-1 text-sm">
                  {calendar.data?.days.map((d) => (
                    <li key={d.date} className="flex flex-wrap gap-2"><span className="w-24 text-muted">{new Date(`${d.date}T00:00`).toLocaleDateString("en-IN", { weekday: "short", day: "2-digit", month: "short" })}</span>{d.segments.length === 0 ? <Badge tone="good">free</Badge> : d.segments.map((s, i) => <Badge key={i} tone={s.layer === "held" ? "warn" : s.layer === "maintenance" ? "bad" : "info"}>{slotToHHMM(s.start_slot)}–{slotToHHMM(s.end_slot)} {s.layer === "timetable" ? "class" : s.layer}</Badge>)}</li>
                  ))}
                </ul>
              )}
            </Card>
          )}
        </div>
        <div className="space-y-4">
          <Card title={`Request ${selected?.code ?? "a room"}`}>
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); check.mutate(); }}>
              <Field label="Title"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
              <Field label="Date"><Input type="date" value={date} onChange={(e) => setDay(e.target.value)} /></Field>
              <div className="grid grid-cols-3 gap-2">
                <Field label="From"><Input type="time" value={start} onChange={(e) => setStart(e.target.value)} /></Field>
                <Field label="To"><Input type="time" value={end} onChange={(e) => setEnd(e.target.value)} /></Field>
                <Field label="People"><Input type="number" value={attendees} onChange={(e) => setAttendees(Number(e.target.value))} /></Field>
              </div>
              <Field label="Room"><Select value={selected?.id ?? ""} onChange={(e) => setVenueId(Number(e.target.value))}>{venues?.map((v) => <option key={v.id} value={v.id}>{v.code}</option>)}</Select></Field>
              <Button type="submit" busy={check.isPending} className="w-full">Check and prepare proposal</Button>
            </form>
            {check.isError && <div className="mt-2"><ErrorBox error={check.error} /></div>}
          </Card>
          {proposal && <ProposalCard proposal={proposal} onDiscard={() => setProposal(null)} />}
        </div>
      </div>
    </>
  );
}
