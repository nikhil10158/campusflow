"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { QRCodeSVG } from "qrcode.react";
import { useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ProposalCard } from "@/components/ProposalCard";
import { Badge, Button, Card, Empty, ErrorBox, Field, Input, LoadingRows, Notice, PageHeader, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { addDays, fmtDateTime } from "@/lib/format";
import { useNow, useParkingLots, useVenues } from "@/lib/hooks";
import { proposalFromCheck, type BookingBody, type CheckResponse } from "@/lib/proposal";
import { useAuth, useToasts } from "@/lib/store";
import type { Booking, Proposal } from "@/lib/types";

interface Timeline {
  lots: { lot_id: number; name: string; capacity: number; raw_capacity: number; used: number[] }[];
}

interface Plan {
  ok: boolean;
  unmet: Record<string, number>;
  allocations: { lot_id: number; lot_name: string; vehicles: Record<string, number>; distance_m: number | null; shuttle: boolean }[];
}

interface PassRow {
  id: number;
  type: string;
  plate: string | null;
  token: string;
  valid_from: string;
  valid_to: string;
  revoked: boolean;
}

const VEHICLES = ["car", "bike", "bus", "ev", "vip"];

function LotChart({ lot }: { lot: Timeline["lots"][number] }) {
  const data = lot.used.filter((_, i) => i % 4 === 0).map((used, i) => ({ hour: `${String(i).padStart(2, "0")}:00`, used }));
  return (
    <div className="rounded-lg border border-line p-3">
      <div className="mb-1 flex items-center justify-between text-sm font-medium">{lot.name} <span className="text-xs text-muted">reservable {lot.capacity} of {lot.raw_capacity}</span></div>
      <div className="h-32">
        <ResponsiveContainer>
          <AreaChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
            <XAxis dataKey="hour" tick={{ fontSize: 10 }} interval={3} />
            <YAxis tick={{ fontSize: 10 }} width={28} allowDecimals={false} />
            <Tooltip />
            <ReferenceLine y={lot.capacity} stroke="var(--bad)" strokeDasharray="4 2" />
            <Area type="stepAfter" dataKey="used" stroke="var(--primary)" fill="var(--primary)" fillOpacity={0.25} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export default function ParkingPage() {
  const { data: now } = useNow();
  const { data: venues } = useVenues();
  const { data: lots } = useParkingLots();
  const user = useAuth((state) => state.user);
  const push = useToasts((state) => state.push);
  const client = useQueryClient();
  const today = (now?.now ?? "2026-11-16").slice(0, 10);
  const [day, setDay] = useState("");
  const [vehicle, setVehicle] = useState("car");
  const [cars, setCars] = useState(15);
  const [buses, setBuses] = useState(0);
  const [evs, setEvs] = useState(0);
  const [near, setNear] = useState("");
  const [start, setStart] = useState("09:00");
  const [end, setEnd] = useState("17:00");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [bookingId, setBookingId] = useState<number | null>(null);
  const date = day || addDays(today, 3);
  const staff = user?.role === "admin" || user?.role === "approver";

  const timeline = useQuery({ queryKey: ["parking-timeline", date, vehicle], queryFn: () => api<Timeline>("/parking/timeline", { params: { day: date, vehicle } }) });
  const plan = useMutation({ mutationFn: () => api<Plan>("/parking/availability", { params: { start: `${date}T${start}:00`, end: `${date}T${end}:00`, cars, buses, evs, near_venue_id: near } }) });
  const propose = useMutation({
    mutationFn: async (allocation: Plan["allocations"][number]) => {
      const body: BookingBody = { resource_type: "parking", resource_id: allocation.lot_id, start: `${date}T${start}:00`, end: `${date}T${end}:00`, event_title: "Visitor parking", attendees: cars + buses * 40 + evs, qty: Object.values(allocation.vehicles).reduce((a, b) => a + b, 0), meta: { vehicles: allocation.vehicles } };
      const check = await api<CheckResponse>("/proposals/check", { body });
      return proposalFromCheck(check, body, allocation.lot_name);
    },
    onSuccess: setProposal,
  });
  const bookings = useQuery({ queryKey: ["parking-bookings"], queryFn: () => api<Booking[]>("/bookings", { params: { status: "CONFIRMED" } }) });
  const parkingBookings = useMemo(() => (bookings.data ?? []).filter((b) => b.resource_type === "parking"), [bookings.data]);
  const passes = useQuery({ queryKey: ["passes", bookingId], queryFn: () => api<PassRow[]>("/passes", { params: { booking_id: bookingId } }), enabled: bookingId !== null });
  const noShows = useQuery({ queryKey: ["no-shows"], queryFn: () => api<{ booking_id: number; title: string; lot: string; start: string }[]>("/parking/no-shows"), enabled: staff });
  const release = useMutation({
    mutationFn: (id: number) => api(`/parking/no-shows/${id}/release`, { method: "POST" }),
    onSuccess: () => { push("good", "No-show released and passes revoked"); client.invalidateQueries({ queryKey: ["no-shows"] }); },
    onError: (e) => push("bad", e instanceof Error ? e.message : "Could not release"),
  });
  const frontend = typeof window === "undefined" ? "" : window.location.origin;

  return (
    <>
      <PageHeader title="Parking" subtitle="Per-lot, per-vehicle-type capacity every 15 minutes. Ten percent of every lot is a walk-in reserve and is never booked in advance." />
      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <div className="space-y-4">
          <Card title="Allocation preview">
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); plan.mutate(); }}>
              <Field label="Date"><Input type="date" value={date} onChange={(e) => setDay(e.target.value)} /></Field>
              <div className="grid grid-cols-2 gap-2"><Field label="From"><Input type="time" value={start} onChange={(e) => setStart(e.target.value)} /></Field><Field label="To"><Input type="time" value={end} onChange={(e) => setEnd(e.target.value)} /></Field></div>
              <div className="grid grid-cols-3 gap-2">
                <Field label="Cars"><Input type="number" min={0} value={cars} onChange={(e) => setCars(Number(e.target.value))} /></Field>
                <Field label="Buses"><Input type="number" min={0} value={buses} onChange={(e) => setBuses(Number(e.target.value))} /></Field>
                <Field label="EVs"><Input type="number" min={0} value={evs} onChange={(e) => setEvs(Number(e.target.value))} /></Field>
              </div>
              <Field label="Close to venue"><Select value={near} onChange={(e) => setNear(e.target.value)}><option value="">Anywhere</option>{venues?.filter((v) => ["amphitheatre", "seminar_hall"].includes(v.type)).map((v) => <option key={v.id} value={v.id}>{v.code}</option>)}</Select></Field>
              <Button type="submit" busy={plan.isPending} className="w-full">Plan parking</Button>
            </form>
            {plan.isError && <div className="mt-2"><ErrorBox error={plan.error} /></div>}
            {plan.data && (
              <div className="mt-3 space-y-2">
                {!plan.data.ok && <Notice tone="bad">Not enough space: unmet {JSON.stringify(plan.data.unmet)}</Notice>}
                {plan.data.allocations.map((a) => (
                  <div key={a.lot_id} className="rounded-lg border border-line p-2 text-sm">
                    <div className="flex items-center justify-between"><strong>{a.lot_name}</strong><Button variant="outline" onClick={() => propose.mutate(a)}>Propose</Button></div>
                    <div className="text-xs text-muted">{Object.entries(a.vehicles).map(([k, v]) => `${v} ${k}`).join(", ")}{a.distance_m !== null && ` · ${a.distance_m} m away`}</div>
                    {a.shuttle && <Badge tone="warn">shuttle note on pass</Badge>}
                  </div>
                ))}
              </div>
            )}
          </Card>
          {proposal && <ProposalCard proposal={proposal} onDiscard={() => setProposal(null)} />}
        </div>
        <div className="space-y-4">
          <Card title={`Lot capacity on ${date}`} actions={<Select value={vehicle} onChange={(e) => setVehicle(e.target.value)} className="w-28">{VEHICLES.map((v) => <option key={v}>{v}</option>)}</Select>}>
            {timeline.isPending ? <LoadingRows rows={3} /> : <div className="grid gap-3 md:grid-cols-2">{timeline.data?.lots.map((lot) => <LotChart key={lot.lot_id} lot={lot} />)}{timeline.data?.lots.length === 0 && <Empty>No lot takes {vehicle} vehicles.</Empty>}</div>}
          </Card>
          <Card title="Passes (one per plate, signed and window-limited)">
            <Select value={bookingId ?? ""} onChange={(e) => setBookingId(Number(e.target.value) || null)} aria-label="Parking booking"><option value="">Choose a confirmed parking booking…</option>{parkingBookings.map((b) => <option key={b.id} value={b.id}>#{b.id} {b.event_title} ({lots?.find((l) => l.id === b.resource_id)?.name})</option>)}</Select>
            {passes.isPending && bookingId !== null && <LoadingRows rows={2} />}
            <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {passes.data?.slice(0, 12).map((p) => (
                <div key={p.id} className="rounded-lg border border-line p-2 text-center">
                  <QRCodeSVG value={`${frontend}/pass/${p.token}`} size={96} bgColor="transparent" fgColor="currentColor" className="mx-auto" />
                  <div className="mt-1 text-sm font-medium">{p.plate ?? p.type}</div>
                  <div className="text-[11px] text-muted">{fmtDateTime(p.valid_from)} → {fmtDateTime(p.valid_to).slice(-5)}</div>
                  {p.revoked && <Badge tone="bad">revoked</Badge>}
                </div>
              ))}
            </div>
          </Card>
          {staff && (
            <Card title="No-show release proposals">
              {noShows.data?.length === 0 ? <Empty>No parking booking is past the 30-minute grace period without a scan. Advance the demo clock to see one.</Empty> : (
                <ul className="space-y-2">{noShows.data?.map((n) => <li key={n.booking_id} className="flex items-center justify-between rounded-lg border border-line p-2 text-sm"><span>#{n.booking_id} {n.title} · {n.lot} · started {fmtDateTime(n.start)}</span><Button variant="danger" onClick={() => release.mutate(n.booking_id)} busy={release.isPending}>Release slots</Button></li>)}</ul>
              )}
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
