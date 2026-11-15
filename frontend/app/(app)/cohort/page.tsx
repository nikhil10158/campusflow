"use client";

import { useMutation } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { ProposalCard } from "@/components/ProposalCard";
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, PageHeader, Select, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { addDays, fmtDateTime, slotToHHMM } from "@/lib/format";
import { useNow, useSections } from "@/lib/hooks";
import { proposalFromCheck, type BookingBody, type CheckResponse } from "@/lib/proposal";
import type { Proposal } from "@/lib/types";

interface Slot {
  date: string;
  start: string;
  end: string;
  score: number;
  reasons: string[];
  rooms: { venue_id: number; code: string; capacity: number; state: string; walk_min: number }[];
}

interface CohortResult {
  attendees: number;
  slots: Slot[];
  heat_strips: Record<string, number[]>;
  sections: number;
}

function HeatStrip({ day, counts, total }: { day: string; counts: number[]; total: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-20 shrink-0 text-xs text-muted">{new Date(`${day}T00:00`).toLocaleDateString("en-IN", { weekday: "short", day: "2-digit", month: "short" })}</span>
      <div className="flex h-5 flex-1 overflow-hidden rounded">
        {counts.slice(32, 76).map((count, index) => (
          <div key={index} title={`${slotToHHMM(index + 32)}: ${count} of ${total} sections free`} className="flex-1" style={{ background: count === total ? "var(--good)" : count === 0 ? "var(--surface-2)" : `color-mix(in srgb, var(--good) ${Math.round((count / total) * 55)}%, var(--surface-2))` }} />
        ))}
      </div>
    </div>
  );
}

export default function CohortPage() {
  const { data: now } = useNow();
  const { data: sections } = useSections();
  const today = (now?.now ?? "2026-11-16").slice(0, 10);
  const [dept, setDept] = useState("CSE");
  const [semester, setSemester] = useState(5);
  const [names, setNames] = useState<string[]>(["A", "B"]);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [duration, setDuration] = useState(60);
  const [kind, setKind] = useState("Quiz");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const departments = useMemo(() => Array.from(new Set(sections?.map((s) => s.dept))), [sections]);

  const search = useMutation({
    mutationFn: () => api<CohortResult>("/availability/cohort-slots", { body: { dept, semester, start_date: from || addDays(today, 1), end_date: to || addDays(today, 7), duration_min: duration } }),
  });
  const propose = useMutation({
    mutationFn: async (slot: Slot) => {
      const room = slot.rooms[0];
      const body: BookingBody = { resource_type: "venue", resource_id: room.venue_id, start: slot.start, end: slot.end, event_title: `${kind}: ${dept} Sem ${semester} ${names.join("+")}`, attendees: search.data?.attendees ?? 0 };
      const check = await api<CheckResponse>("/proposals/check", { body });
      return proposalFromCheck(check, body, room.code);
    },
    onSuccess: setProposal,
  });

  const total = (sections ?? []).filter((s) => s.dept === dept && s.semester === semester && names.includes(s.name)).length || search.data?.sections || 2;

  return (
    <>
      <PageHeader title="Cohort Slot Finder" subtitle="Extra lectures, quizzes and workshops: the AND of every section's free time, then a free room near their home rooms." />
      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <Card title="Who and when">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); search.mutate(); }}>
            <Field label="Department"><Select value={dept} onChange={(e) => setDept(e.target.value)}>{departments.map((d) => <option key={d}>{d}</option>)}</Select></Field>
            <Field label="Semester"><Select value={semester} onChange={(e) => setSemester(Number(e.target.value))}>{[1, 3, 5, 7].map((s) => <option key={s}>{s}</option>)}</Select></Field>
            <div className="flex gap-3 text-sm">{["A", "B"].map((n) => <label key={n} className="flex items-center gap-1"><input type="checkbox" checked={names.includes(n)} onChange={() => setNames(names.includes(n) ? names.filter((x) => x !== n) : [...names, n])} /> Section {n}</label>)}</div>
            <div className="grid grid-cols-2 gap-2">
              <Field label="From"><Input type="date" value={from || addDays(today, 1)} onChange={(e) => setFrom(e.target.value)} /></Field>
              <Field label="To"><Input type="date" value={to || addDays(today, 7)} onChange={(e) => setTo(e.target.value)} /></Field>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Duration (min)"><Select value={duration} onChange={(e) => setDuration(Number(e.target.value))}>{[30, 45, 60, 90, 120, 180].map((d) => <option key={d}>{d}</option>)}</Select></Field>
              <Field label="Purpose"><Select value={kind} onChange={(e) => setKind(e.target.value)}><option>Quiz</option><option>Extra lecture</option><option>Workshop</option></Select></Field>
            </div>
            <Button type="submit" busy={search.isPending} className="w-full">Find common slots</Button>
          </form>
        </Card>
        <div className="space-y-4">
          {search.isError && <ErrorBox error={search.error} />}
          {search.data && (
            <>
              <Card title="Common free time (green = every section free)">
                <div className="space-y-1">{Object.entries(search.data.heat_strips).map(([day, counts]) => <HeatStrip key={day} day={day} counts={counts} total={total} />)}</div>
                <div className="ml-24 mt-1 flex justify-between text-[10px] text-muted"><span>08:00</span><span>12:00</span><span>16:00</span><span>19:00</span></div>
              </Card>
              <Card title={`Ranked slots for ${search.data.attendees} students`}>
                {search.data.slots.length === 0 && <Empty>No common free window. Try a longer date range or a shorter duration.</Empty>}
                <ol className="space-y-2">
                  {search.data.slots.map((slot) => (
                    <li key={slot.start} className="rounded-lg border border-line p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="font-medium">{fmtDateTime(slot.start)} – {fmtDateTime(slot.end).slice(-5)}</div>
                        <div className="flex items-center gap-2"><Badge tone="primary">score {slot.score}</Badge><Button variant="outline" onClick={() => propose.mutate(slot)} busy={propose.isPending && propose.variables?.start === slot.start}>Propose {kind.toLowerCase()}</Button></div>
                      </div>
                      <ul className="mt-1 text-xs text-muted">{slot.reasons.map((r) => <li key={r}>• {r}</li>)}</ul>
                      <div className="mt-2 flex flex-wrap gap-2">{slot.rooms.map((room) => <span key={room.venue_id} className="inline-flex items-center gap-1 text-xs"><Badge>{room.code} · {room.capacity}</Badge><StatusBadge state={room.state} /></span>)}</div>
                    </li>
                  ))}
                </ol>
              </Card>
            </>
          )}
          {propose.isError && <ErrorBox error={propose.error} />}
          {proposal && <ProposalCard proposal={proposal} onDiscard={() => setProposal(null)} />}
        </div>
      </div>
    </>
  );
}
