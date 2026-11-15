"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useRef, useState, type PointerEvent } from "react";

import { ProposalCard } from "@/components/ProposalCard";
import { Badge, Button, Card, ErrorBox, Field, Input, LoadingRows, PageHeader, Select, StatusBadge, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { addDays, slotToHHMM } from "@/lib/format";
import { useNow, useVenues } from "@/lib/hooks";
import { proposalFromCheck, type BookingBody, type CheckResponse } from "@/lib/proposal";
import type { DayVenue, Proposal, Segment } from "@/lib/types";

const FIRST_SLOT = 28;
const LAST_SLOT = 88;
const SPAN = LAST_SLOT - FIRST_SLOT;
const LAYER_COLOR: Record<string, string> = {
  timetable: "var(--layer-timetable)",
  confirmed: "var(--layer-confirmed)",
  held: "var(--layer-held)",
  maintenance: "var(--layer-maintenance)",
};

interface Selection {
  key: string;
  venueId: number;
  from: number;
  to: number;
}

function slotAt(event: PointerEvent<HTMLDivElement>): number {
  const box = event.currentTarget.getBoundingClientRect();
  const ratio = Math.min(0.999, Math.max(0, (event.clientX - box.left) / box.width));
  return FIRST_SLOT + Math.floor(ratio * SPAN);
}

function Row({ rowKey, label, venueId, segments, released, selection, onSelect, onFinish }: {
  rowKey: string; label: string; venueId: number; segments: Segment[]; released: number[]; selection: Selection | null;
  onSelect: (next: Selection | null) => void; onFinish: (next: Selection) => void;
}) {
  const dragging = useRef(false);
  const mine = selection && selection.key === rowKey ? selection : null;
  return (
    <div className="flex items-center border-b border-line/60">
      <div className="w-24 shrink-0 truncate pr-2 text-xs font-medium">{label}</div>
      <div
        className="relative h-7 flex-1 cursor-crosshair touch-none select-none bg-surface"
        style={{ backgroundImage: "linear-gradient(to right, var(--line) 1px, transparent 1px)", backgroundSize: `${100 / (SPAN / 4)}% 100%` }}
        onPointerDown={(event) => {
          dragging.current = true;
          event.currentTarget.setPointerCapture(event.pointerId);
          const slot = slotAt(event);
          onSelect({ key: rowKey, venueId, from: slot, to: slot + 1 });
        }}
        onPointerMove={(event) => {
          if (dragging.current && mine) onSelect({ ...mine, to: Math.max(mine.from + 1, slotAt(event) + 1) });
        }}
        onPointerUp={() => {
          dragging.current = false;
          if (mine) onFinish(mine);
        }}
      >
        {released.filter((slot) => slot >= FIRST_SLOT && slot < LAST_SLOT).map((slot) => (
          <div key={`r${slot}`} className="absolute top-0 h-full" title="Released: pre-slotted class cancelled or released" style={{ left: `${((slot - FIRST_SLOT) / SPAN) * 100}%`, width: `${100 / SPAN}%`, background: "var(--layer-released)", opacity: 0.55 }} />
        ))}
        {segments.map((segment, index) => (
          <div
            key={index}
            title={`${segment.time} ${segment.label}`}
            className={cx("absolute top-0.5 h-6 overflow-hidden rounded text-[10px] leading-6 text-white", segment.ghost && "ring-2 ring-ghost")}
            style={{ left: `${((Math.max(segment.start_slot, FIRST_SLOT) - FIRST_SLOT) / SPAN) * 100}%`, width: `${((Math.min(segment.end_slot, LAST_SLOT) - Math.max(segment.start_slot, FIRST_SLOT)) / SPAN) * 100}%`, background: LAYER_COLOR[segment.layer] }}
          >
            <span className="px-1">{segment.label.slice(0, 14)}</span>
          </div>
        ))}
        {mine && (
          <div className="pointer-events-none absolute top-0 h-full border-2 border-primary bg-primary/20" style={{ left: `${((mine.from - FIRST_SLOT) / SPAN) * 100}%`, width: `${((mine.to - mine.from) / SPAN) * 100}%` }} />
        )}
      </div>
    </div>
  );
}

export default function TimelinePage() {
  const { data: now } = useNow();
  const [view, setView] = useState<"day" | "week">("day");
  const [day, setDay] = useState("");
  const [type, setType] = useState("classroom");
  const [venueId, setVenueId] = useState<number | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [feasible, setFeasible] = useState<{ state: string; explanation: string; free: boolean } | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [title, setTitle] = useState("Extra session");
  const [attendees, setAttendees] = useState(30);
  const date = day || (now?.now ?? "2026-11-16").slice(0, 10);
  const { data: venues } = useVenues();

  const dayQuery = useQuery({ queryKey: ["day-view", date, type], queryFn: () => api<{ holiday: boolean; venues: DayVenue[] }>("/availability/day", { params: { day: date, types: type } }), enabled: view === "day" });
  const weekQuery = useQuery({ queryKey: ["week-view", date, venueId], queryFn: () => api<{ venue: { code: string }; days: { date: string; segments: Segment[]; released_slots: number[]; holiday: boolean }[] }>(`/availability/venue/${venueId}`, { params: { date_from: date, days: 7 } }), enabled: view === "week" && venueId !== null });

  const explain = useMutation({
    mutationFn: async (picked: Selection) => {
      const rowDate = picked.key.includes("|") ? picked.key.split("|")[1] : date;
      const start = `${rowDate}T${slotToHHMM(picked.from)}:00`;
      const end = `${rowDate}T${slotToHHMM(picked.to)}:00`;
      const result = await api<{ state: string; explanation: string; free: boolean }>("/availability/explain", { params: { venue_id: picked.venueId, start, end } });
      return { ...result, start, end };
    },
    onSuccess: (value) => setFeasible(value),
  });

  const book = useMutation({
    mutationFn: async () => {
      if (!selection) throw new Error("Select a window first");
      const rowDate = selection.key.includes("|") ? selection.key.split("|")[1] : date;
      const body: BookingBody = { resource_type: "venue", resource_id: selection.venueId, start: `${rowDate}T${slotToHHMM(selection.from)}:00`, end: `${rowDate}T${slotToHHMM(selection.to)}:00`, event_title: title, attendees };
      const check = await api<CheckResponse>("/proposals/check", { body });
      return proposalFromCheck(check, body, venues?.find((v) => v.id === selection.venueId)?.code ?? "");
    },
    onSuccess: setProposal,
  });

  const hours = useMemo(() => Array.from({ length: SPAN / 4 + 1 }, (_, i) => FIRST_SLOT / 4 + i), []);
  const list = (venues ?? []).filter((v) => v.type === type);

  return (
    <>
      <PageHeader help={["Choose a day and a room type. Each row is a room from 07:00 to 22:00.", "Drag across a row to test a time window; the verdict appears below.", "If it is free, name it and press Book this to get a proposal."]} title="Venue Timeline" subtitle="Drag across a row to test a window. Non-admin users see 'Busy' only, never titles or purposes." />
      <Card className="mb-4">
        <div className="flex flex-wrap items-end gap-3">
          <Field label="View">
            <Select value={view} onChange={(e) => setView(e.target.value as "day" | "week")}>
              <option value="day">Day · all rooms</option>
              <option value="week">Week · one room</option>
            </Select>
          </Field>
          <Field label="Date">
            <div className="flex gap-1">
              <Button variant="outline" onClick={() => setDay(addDays(date, view === "day" ? -1 : -7))}>◀</Button>
              <Input type="date" value={date} onChange={(e) => setDay(e.target.value)} />
              <Button variant="outline" onClick={() => setDay(addDays(date, view === "day" ? 1 : 7))}>▶</Button>
            </div>
          </Field>
          <Field label="Type">
            <Select value={type} onChange={(e) => setType(e.target.value)}>
              {["classroom", "seminar_hall", "lab", "amphitheatre"].map((t) => (
                <option key={t} value={t}>{t.replace("_", " ")}</option>
              ))}
            </Select>
          </Field>
          {view === "week" && (
            <Field label="Room">
              <Select value={venueId ?? ""} onChange={(e) => setVenueId(Number(e.target.value))}>
                <option value="">Choose…</option>
                {list.map((v) => (
                  <option key={v.id} value={v.id}>{v.code}</option>
                ))}
              </Select>
            </Field>
          )}
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries({ timetable: "Class", confirmed: "Booked", held: "Held", maintenance: "Maintenance" }).map(([key, label]) => (
              <span key={key} className="flex items-center gap-1">
                <span className="h-3 w-3 rounded" style={{ background: LAYER_COLOR[key] }} /> {label}
              </span>
            ))}
            <span className="flex items-center gap-1"><span className="h-3 w-3 rounded" style={{ background: "var(--layer-released)" }} /> Released</span>
            <span className="flex items-center gap-1"><span className="h-3 w-3 rounded ring-2 ring-ghost" /> Ghost</span>
          </div>
        </div>
      </Card>
      <Card>
        <div className="overflow-x-auto">
          <div className="min-w-[900px]">
            <div className="flex border-b border-line pb-1 text-[10px] text-muted">
              <div className="w-24 shrink-0" />
              <div className="relative h-4 flex-1">
                {hours.map((hour) => (
                  <span key={hour} className="absolute -translate-x-1/2" style={{ left: `${((hour * 4 - FIRST_SLOT) / SPAN) * 100}%` }}>{hour}:00</span>
                ))}
              </div>
            </div>
            {view === "day" && dayQuery.isPending && <LoadingRows rows={8} />}
            {view === "day" && dayQuery.isError && <ErrorBox error={dayQuery.error} />}
            {view === "day" && dayQuery.data?.holiday && <p className="py-2 text-sm text-info">This is a synthetic holiday: no timetabled classes run.</p>}
            {view === "day" && dayQuery.data?.venues.map((row) => (
              <Row key={row.id} rowKey={String(row.id)} label={`${row.code} · ${row.capacity}`} venueId={row.id} segments={row.segments} released={row.released_slots} selection={selection} onSelect={setSelection} onFinish={(picked) => explain.mutate(picked)} />
            ))}
            {view === "week" && venueId === null && <p className="py-4 text-sm text-muted">Pick a room to see its week.</p>}
            {view === "week" && weekQuery.isPending && venueId !== null && <LoadingRows rows={7} />}
            {view === "week" && weekQuery.data?.days.map((row) => (
              <Row key={row.date} rowKey={`${venueId}|${row.date}`} label={new Date(`${row.date}T00:00`).toLocaleDateString("en-IN", { weekday: "short", day: "2-digit", month: "short" })} venueId={venueId as number} segments={row.segments} released={row.released_slots} selection={selection} onSelect={setSelection} onFinish={(picked) => explain.mutate(picked)} />
            ))}
          </div>
        </div>
      </Card>
      {selection && (
        <Card className="mt-4" title="Selected window">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <Badge tone="info">{venues?.find((v) => v.id === selection.venueId)?.code}</Badge>
            <span>{slotToHHMM(selection.from)} – {slotToHHMM(selection.to)}</span>
            {explain.isPending ? <span className="text-muted">Checking…</span> : feasible && <><StatusBadge state={feasible.free ? feasible.state : "BUSY"} /><span className="text-muted">{feasible.explanation}</span></>}
          </div>
          {feasible?.free && (
            <div className="mt-3 flex flex-wrap items-end gap-2">
              <Field label="Title"><Input value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
              <Field label="Attendees"><Input type="number" value={attendees} onChange={(e) => setAttendees(Number(e.target.value))} className="w-24" /></Field>
              <Button onClick={() => book.mutate()} busy={book.isPending}>Book this</Button>
            </div>
          )}
          {book.isError && <div className="mt-2"><ErrorBox error={book.error} /></div>}
        </Card>
      )}
      {proposal && <div className="mt-4"><ProposalCard proposal={proposal} onDiscard={() => setProposal(null)} /></div>}
    </>
  );
}
