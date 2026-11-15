"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileDown } from "lucide-react";
import { useMemo, useState } from "react";

import { ProposalCard } from "@/components/ProposalCard";
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, LoadingRows, Notice, PageHeader, Select, StatusBadge, cx } from "@/components/ui";
import { api, download } from "@/lib/api";
import { addDays } from "@/lib/format";
import { useGuestRooms, useNow } from "@/lib/hooks";
import { proposalFromCheck, type BookingBody, type CheckResponse } from "@/lib/proposal";
import { useAuth, useToasts } from "@/lib/store";
import type { Proposal } from "@/lib/types";

interface CalendarCell {
  booking_id: number | null;
  room_id: number;
  start: string;
  end: string;
  status: string;
  title: string;
}

interface Availability {
  rooms: { id: number; code: string; type: string; capacity: number; accessible: boolean; tariff_per_night: number; estimate: number }[];
  nights: number;
}

interface Allocation {
  status: string;
  rooms_used: number;
  tariff_per_night: number;
  suite_misuse: number;
  assignments: { guest: string; room: string; room_type: string }[];
  violations: string[];
}

interface WaitItem {
  booking_id: number;
  title: string;
  priority_class: number;
  start: string;
  end: string;
  requested_type: string | null;
  promotion: { room_code: string } | null;
}

const CELL_COLOR: Record<string, string> = { CONFIRMED: "var(--layer-confirmed)", HELD: "var(--layer-held)", MAINTENANCE: "var(--layer-maintenance)" };
const CATEGORIES = ["vip", "official", "faculty_guest", "parent", "vendor", "other"];

function OccupancyCalendar({ from }: { from: string }) {
  const days = 21;
  const { data, isPending } = useQuery({ queryKey: ["gh-calendar", from], queryFn: () => api<{ rooms: { id: number; code: string; type: string }[]; cells: CalendarCell[] }>("/guesthouse/calendar", { params: { date_from: from, days } }) });
  const dates = useMemo(() => Array.from({ length: days }, (_, i) => addDays(from, i)), [from]);
  if (isPending || !data) return <LoadingRows rows={6} />;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-[760px] border-separate border-spacing-0.5 text-xs">
        <thead>
          <tr>
            <th className="w-20 text-left font-medium text-muted">Room</th>
            {dates.map((d) => <th key={d} className="font-normal text-muted">{d.slice(8)}</th>)}
          </tr>
        </thead>
        <tbody>
          {data.rooms.map((room) => (
            <tr key={room.id}>
              <td className="whitespace-nowrap pr-2 text-xs font-medium">{room.code} <span className="text-muted">{room.type.slice(0, 3)}</span></td>
              {dates.map((d) => {
                const cell = data.cells.find((c) => c.room_id === room.id && c.start.slice(0, 10) <= d && c.end.slice(0, 10) > d);
                return <td key={d} title={cell ? `${cell.title} (${cell.status})` : "free"} className="h-5 rounded" style={{ background: cell ? CELL_COLOR[cell.status] : "var(--surface-2)" }} />;
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 flex gap-3 text-xs">
        {Object.entries(CELL_COLOR).map(([k, v]) => <span key={k} className="flex items-center gap-1"><span className="h-3 w-3 rounded" style={{ background: v }} />{k.toLowerCase()}</span>)}
      </div>
    </div>
  );
}

function GroupAllocator({ from, nights }: { from: string; nights: number }) {
  const [guests, setGuests] = useState([{ name: "Keynote speaker", category: "vip", accessible: false }, { name: "Co-speaker", category: "official", accessible: false }, { name: "Assistant A", category: "other", accessible: false }, { name: "Assistant B", category: "other", accessible: false }, { name: "Visitor", category: "other", accessible: true }]);
  const [share, setShare] = useState("3-4");
  const [apart, setApart] = useState("1-2");
  const parse = (text: string) => text.split(",").map((pair) => pair.trim().split("-").map((n) => Number(n) - 1)).filter((pair) => pair.length === 2 && pair.every((n) => n >= 0 && n < guests.length)) as [number, number][];
  const run = useMutation({
    mutationFn: () => api<{ optimised: Allocation; greedy: Allocation }>("/guesthouse/group-allocate", { body: { start: `${from}T14:00:00`, end: `${addDays(from, nights)}T11:00:00`, guests: guests.map((g) => ({ name: g.name, category: g.category, needs_accessible: g.accessible })), must_share: parse(share), must_not_share: parse(apart) } }),
  });
  const update = (index: number, patch: Partial<(typeof guests)[number]>) => setGuests(guests.map((g, i) => (i === index ? { ...g, ...patch } : g)));
  return (
    <div className="space-y-3">
      {guests.map((guest, index) => (
        <div key={index} className="grid grid-cols-[24px_1fr_130px_auto] items-center gap-2">
          <span className="text-xs text-muted">{index + 1}</span>
          <Input value={guest.name} onChange={(e) => update(index, { name: e.target.value })} aria-label={`Guest ${index + 1} name`} />
          <Select value={guest.category} onChange={(e) => update(index, { category: e.target.value })} aria-label="Category">{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</Select>
          <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={guest.accessible} onChange={(e) => update(index, { accessible: e.target.checked })} /> step-free</label>
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => setGuests([...guests, { name: `Guest ${guests.length + 1}`, category: "other", accessible: false }])}>Add guest</Button>
        <Field label="Must share (e.g. 3-4)"><Input value={share} onChange={(e) => setShare(e.target.value)} className="w-28" /></Field>
        <Field label="Must not share"><Input value={apart} onChange={(e) => setApart(e.target.value)} className="w-28" /></Field>
        <Button onClick={() => run.mutate()} busy={run.isPending} className="self-end">Allocate rooms</Button>
      </div>
      {run.isError && <ErrorBox error={run.error} />}
      {run.data && (
        <div className="grid gap-3 md:grid-cols-2">
          {([["Optimised (CP-SAT)", run.data.optimised], ["Greedy first-fit", run.data.greedy]] as [string, Allocation][]).map(([label, plan]) => (
            <div key={label} className="rounded-lg border border-line p-3 text-sm">
              <div className="mb-1 flex items-center justify-between font-medium">{label} <StatusBadge state={plan.status} /></div>
              <div className="mb-2 text-xs text-muted">{plan.rooms_used} rooms · Rs {plan.tariff_per_night}/night · suite misuse {plan.suite_misuse}</div>
              <ul className="space-y-0.5 text-xs">{plan.assignments.map((a) => <li key={a.guest}>{a.guest} → <strong>{a.room}</strong> ({a.room_type})</li>)}</ul>
              {plan.violations.map((v) => <p key={v} className="text-xs text-bad">{v}</p>)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function GuestHousePage() {
  const { data: now } = useNow();
  const user = useAuth((state) => state.user);
  const push = useToasts((state) => state.push);
  const client = useQueryClient();
  const today = (now?.now ?? "2026-11-16").slice(0, 10);
  const [arrival, setArrival] = useState("");
  const [nights, setNights] = useState(2);
  const [guests, setGuests] = useState(1);
  const [category, setCategory] = useState("other");
  const [accessible, setAccessible] = useState(false);
  const [host, setHost] = useState("");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const from = arrival || addDays(today, 3);
  const { data: rooms } = useGuestRooms();
  const manager = user?.role === "admin" || user?.role === "approver";

  const search = useMutation({ mutationFn: () => api<Availability>("/guesthouse/availability", { params: { start: `${from}T14:00:00`, end: `${addDays(from, nights)}T11:00:00`, guests, category, accessible } }) });
  const propose = useMutation({
    mutationFn: async (roomId: number) => {
      const body: BookingBody = { resource_type: "guest_room", resource_id: roomId, start: `${from}T14:00:00`, end: `${addDays(from, nights)}T11:00:00`, event_title: "Guest stay", attendees: guests, host_ref: host || user?.name || "Host", meta: { guests, category } };
      const check = await api<CheckResponse>("/proposals/check", { body });
      return proposalFromCheck(check, body, rooms?.find((r) => r.id === roomId)?.code ?? "");
    },
    onSuccess: setProposal,
  });
  const waitlist = useQuery({ queryKey: ["waitlist"], queryFn: () => api<{ waitlist: WaitItem[] }>("/guesthouse/waitlist"), enabled: manager });
  const promote = useMutation({
    mutationFn: (id: number) => api(`/guesthouse/waitlist/${id}/promote`, { method: "POST" }),
    onSuccess: () => { push("good", "Promoted: the manager's approval step is now pending"); client.invalidateQueries({ queryKey: ["waitlist"] }); },
    onError: (error) => push("bad", error instanceof Error ? error.message : "Could not promote"),
  });

  return (
    <>
      <PageHeader help={["The calendar shows every room for the next three weeks.", "Search for nights, then Propose a room. A host or event must be named.", "Visiting team? Use group allocation to place everyone in as few rooms as possible."]} title="MDC Guest House" subtitle="16 rooms. Nights are checked with a 60-minute turnover buffer; guest nights must be linked to a host or an event." actions={manager ? <Button variant="outline" onClick={() => download("/exports/guesthouse/checkin.pdf", "checkin.pdf", { day: from })}><FileDown className="h-4 w-4" /> Check-in sheet</Button> : null} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Occupancy · next 3 weeks"><OccupancyCalendar from={today} /></Card>
        <Card title="Find a room">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); search.mutate(); }}>
            <div className="grid grid-cols-4 gap-2">
              <Field label="Arrival"><Input type="date" value={from} onChange={(e) => setArrival(e.target.value)} /></Field>
              <Field label="Nights"><Input type="number" min={1} max={8} value={nights} onChange={(e) => setNights(Number(e.target.value))} /></Field>
              <Field label="Guests"><Input type="number" min={1} value={guests} onChange={(e) => setGuests(Number(e.target.value))} /></Field>
              <Field label="Category"><Select value={category} onChange={(e) => setCategory(e.target.value)}>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</Select></Field>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <Field label="Host or event"><Input value={host} onChange={(e) => setHost(e.target.value)} placeholder="Linked host (required)" /></Field>
              <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={accessible} onChange={(e) => setAccessible(e.target.checked)} /> Step-free room</label>
              <Button type="submit" busy={search.isPending}>Search</Button>
            </div>
          </form>
          {search.data && (
            <ul className="mt-3 space-y-2">
              {search.data.rooms.length === 0 && <Empty>No room is free. Ask the manager to waitlist the request.</Empty>}
              {search.data.rooms.map((room) => (
                <li key={room.id} className="flex items-center justify-between rounded-lg border border-line p-2 text-sm">
                  <span><strong>{room.code}</strong> {room.type} · sleeps {room.capacity} {room.accessible && <Badge tone="info">step-free</Badge>}</span>
                  <span className="flex items-center gap-2"><span className="text-xs text-muted">≈ Rs {room.estimate}</span><Button variant="outline" onClick={() => propose.mutate(room.id)} busy={propose.isPending && propose.variables === room.id}>Propose</Button></span>
                </li>
              ))}
            </ul>
          )}
          {propose.isError && <div className="mt-2"><ErrorBox error={propose.error} /></div>}
        </Card>
      </div>
      {proposal && <div className="mt-4"><ProposalCard proposal={proposal} onDiscard={() => setProposal(null)} /></div>}
      <Card className="mt-4" title="Group allocation (visiting team)"><GroupAllocator from={from} nights={nights} /></Card>
      {manager && (
        <Card className="mt-4" title="Waitlist (priority class, then request time)">
          {waitlist.isPending ? <LoadingRows rows={2} /> : waitlist.data?.waitlist.length === 0 ? <Empty>The waitlist is empty.</Empty> : (
            <ul className="space-y-2">
              {waitlist.data?.waitlist.map((item) => (
                <li key={item.booking_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line p-2 text-sm">
                  <span>#{item.booking_id} {item.title} <Badge tone="warn">priority {item.priority_class}</Badge> {item.requested_type && <Badge>{item.requested_type}</Badge>}</span>
                  {item.promotion ? <span className="flex items-center gap-2"><Notice tone="good">Room {item.promotion.room_code} is free</Notice><Button onClick={() => promote.mutate(item.booking_id)} busy={promote.isPending}>Promote (needs your approval)</Button></span> : <span className={cx("text-xs text-muted")}>No room free yet</span>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
    </>
  );
}
