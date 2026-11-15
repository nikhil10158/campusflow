"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import { ProposalCard } from "@/components/ProposalCard";
import { Button, Card, Empty, ErrorBox, Field, Input, LoadingRows, Notice, PageHeader, Select, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { addDays, fmtDateTime } from "@/lib/format";
import { useNow, useVenues } from "@/lib/hooks";
import { proposalFromCheck, type BookingBody, type CheckResponse } from "@/lib/proposal";
import type { Booking, Proposal } from "@/lib/types";

interface Person {
  id: number;
  email: string;
  role: string;
  name: string;
}

export default function StudentPage() {
  const { data: now } = useNow();
  const { data: venues } = useVenues("classroom");
  const today = (now?.now ?? "2026-11-16").slice(0, 10);
  const [title, setTitle] = useState("Club meeting");
  const [day, setDay] = useState("");
  const [start, setStart] = useState("16:00");
  const [end, setEnd] = useState("17:00");
  const [people, setPeople] = useState(30);
  const [room, setRoom] = useState("");
  const [sponsor, setSponsor] = useState("");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const mine = useQuery({ queryKey: ["bookings-student"], queryFn: () => api<Booking[]>("/bookings") });
  const faculty = useQuery({ queryKey: ["faculty-users"], queryFn: () => api<Person[]>("/auth/demo-users") });
  const sponsors = (faculty.data ?? []).filter((p) => p.role === "faculty");
  const check = useMutation({
    mutationFn: async () => {
      const chosen = venues?.find((v) => String(v.id) === room) ?? venues?.[0];
      if (!chosen) throw new Error("Pick a room");
      const sponsorUser = sponsors.find((s) => String(s.id) === sponsor);
      const body: BookingBody = { resource_type: "venue", resource_id: chosen.id, start: `${day || addDays(today, 3)}T${start}:00`, end: `${day || addDays(today, 3)}T${end}:00`, event_title: title, attendees: people, sponsor_id: sponsorUser ? sponsorUser.id : null };
      const result = await api<CheckResponse>("/proposals/check", { body });
      return proposalFromCheck(result, body, chosen.code);
    },
    onSuccess: setProposal,
  });
  return (
    <>
      <PageHeader title="My requests" subtitle="Clubs request rooms through a faculty sponsor. You only ever see your own bookings." actions={<Link href="/find" className="text-sm text-primary underline">See free rooms</Link>} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Club room request">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); check.mutate(); }}>
            <Field label="Title"><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
            <div className="grid grid-cols-3 gap-2"><Field label="Date"><Input type="date" value={day || addDays(today, 3)} onChange={(e) => setDay(e.target.value)} /></Field><Field label="From"><Input type="time" value={start} onChange={(e) => setStart(e.target.value)} /></Field><Field label="To"><Input type="time" value={end} onChange={(e) => setEnd(e.target.value)} /></Field></div>
            <div className="grid grid-cols-2 gap-2"><Field label="People"><Input type="number" value={people} onChange={(e) => setPeople(Number(e.target.value))} /></Field><Field label="Room"><Select value={room} onChange={(e) => setRoom(e.target.value)}>{venues?.map((v) => <option key={v.id} value={v.id}>{v.code} ({v.capacity})</option>)}</Select></Field></div>
            <Field label="Faculty sponsor" hint="Required: students cannot submit alone (BP-1.2)"><Select value={sponsor} onChange={(e) => setSponsor(e.target.value)}><option value="">Choose a sponsor…</option>{sponsors.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select></Field>
            {!sponsor && <Notice tone="warn">Without a sponsor the policy engine will block the request.</Notice>}
            <Button type="submit" busy={check.isPending} className="w-full">Check and prepare proposal</Button>
          </form>
          {check.isError && <div className="mt-2"><ErrorBox error={check.error} /></div>}
        </Card>
        <div className="space-y-4">
          {proposal && <ProposalCard proposal={proposal} onDiscard={() => setProposal(null)} />}
          <Card title="My bookings">
            {mine.isPending ? <LoadingRows rows={3} /> : mine.data?.length === 0 ? <Empty>No bookings yet.</Empty> : (
              <ul className="space-y-1 text-sm">{mine.data?.map((b) => <li key={b.id} className="flex items-center justify-between border-b border-line py-1"><span>#{b.id} {b.event_title} · {fmtDateTime(b.start)}</span><StatusBadge state={b.status} /></li>)}</ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}

