"use client";

import { useMutation } from "@tanstack/react-query";
import { Footprints, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { CampusMap } from "@/components/CampusMap";
import { ProposalCard } from "@/components/ProposalCard";
import { Badge, Button, Card, Drawer, Empty, ErrorBox, Field, Input, LoadingRows, PageHeader, Select, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { addDays, fmtDateTime } from "@/lib/format";
import { useBuildings, useNow } from "@/lib/hooks";
import { proposalFromCheck, type BookingBody, type CheckResponse } from "@/lib/proposal";
import { useAuth } from "@/lib/store";
import type { Proposal, RoomHit, SearchResult } from "@/lib/types";

const TYPES = [["classroom", "Classroom"], ["seminar_hall", "Seminar hall"], ["lab", "Lab"], ["amphitheatre", "Amphitheatre"]];
const FEATURES = ["projector", "ac", "smartboard", "mic", "pcs", "recording"];

export default function FindPage() {
  const { data: now } = useNow();
  const { data: buildings } = useBuildings();
  const user = useAuth((state) => state.user);
  const tomorrow = useMemo(() => addDays((now?.now ?? new Date().toISOString()).slice(0, 10), 1), [now]);
  const [day, setDay] = useState("");
  const [start, setStart] = useState("14:00");
  const [end, setEnd] = useState("16:00");
  const [attendees, setAttendees] = useState(60);
  const [types, setTypes] = useState<string[]>(["classroom"]);
  const [features, setFeatures] = useState<string[]>([]);
  const [building, setBuilding] = useState("");
  const [accessible, setAccessible] = useState(false);
  const [repeat, setRepeat] = useState(1);
  const [drawer, setDrawer] = useState(false);
  const [filter, setFilter] = useState("");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [title, setTitle] = useState("Extra lecture");
  const date = day || tomorrow;

  const search = useMutation({
    mutationFn: () =>
      api<SearchResult>("/availability/search", {
        params: { start: `${date}T${start}:00`, end: `${date}T${end}:00`, attendees, types: types.join(","), optional: features.join(","), building_id: building, accessible, repeat_weeks: repeat },
      }),
  });

  const book = useMutation({
    mutationFn: async (hit: RoomHit) => {
      const body: BookingBody = { resource_type: "venue", resource_id: hit.venue_id, start: `${date}T${start}:00`, end: `${date}T${end}:00`, event_title: title, attendees };
      const check = await api<CheckResponse>("/proposals/check", { body });
      return proposalFromCheck(check, body, hit.code);
    },
    onSuccess: setProposal,
  });

  const byBuilding = useMemo(() => {
    const counts: Record<number, number> = {};
    search.data?.hits.forEach((hit) => {
      counts[hit.building_id] = (counts[hit.building_id] ?? 0) + 1;
    });
    return counts;
  }, [search.data]);

  const toggle = (list: string[], value: string, set: (next: string[]) => void) => set(list.includes(value) ? list.filter((item) => item !== value) : [...list, value]);
  const canBook = user?.role !== "security";
  const rejected = (search.data?.why_not ?? []).filter((row) => row.reason.toLowerCase().includes(filter.toLowerCase()));

  return (
    <>
      <PageHeader title="Free Room Finder" subtitle="Rooms are free only if no class, booking, hold or maintenance touches the window (buffers included). Cancelled or released classes show as FREE RELEASED." />
      <div className="grid gap-4 xl:grid-cols-[360px_1fr]">
        <Card title="What do you need?">
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              search.mutate();
            }}
          >
            <div className="grid grid-cols-3 gap-2">
              <Field label="Date">
                <Input type="date" value={date} onChange={(e) => setDay(e.target.value)} />
              </Field>
              <Field label="From">
                <Input type="time" value={start} onChange={(e) => setStart(e.target.value)} />
              </Field>
              <Field label="To">
                <Input type="time" value={end} onChange={(e) => setEnd(e.target.value)} />
              </Field>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Attendees">
                <Input type="number" min={0} value={attendees} onChange={(e) => setAttendees(Number(e.target.value))} />
              </Field>
              <Field label="Repeat weekly for">
                <Select value={repeat} onChange={(e) => setRepeat(Number(e.target.value))}>
                  {[1, 2, 4, 8].map((n) => (
                    <option key={n} value={n}>
                      {n === 1 ? "one date" : `${n} weeks`}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            <fieldset>
              <legend className="mb-1 text-xs font-medium text-muted">Venue types</legend>
              <div className="flex flex-wrap gap-2">
                {TYPES.map(([value, label]) => (
                  <label key={value} className="flex items-center gap-1 text-sm">
                    <input type="checkbox" checked={types.includes(value)} onChange={() => toggle(types, value, setTypes)} /> {label}
                  </label>
                ))}
              </div>
            </fieldset>
            <fieldset>
              <legend className="mb-1 text-xs font-medium text-muted">Nice to have</legend>
              <div className="flex flex-wrap gap-2">
                {FEATURES.map((feature) => (
                  <label key={feature} className="flex items-center gap-1 text-sm">
                    <input type="checkbox" checked={features.includes(feature)} onChange={() => toggle(features, feature, setFeatures)} /> {feature}
                  </label>
                ))}
              </div>
            </fieldset>
            <Field label="Close to building">
              <Select value={building} onChange={(e) => setBuilding(e.target.value)}>
                <option value="">Anywhere</option>
                {buildings?.map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </Select>
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={accessible} onChange={(e) => setAccessible(e.target.checked)} /> Step-free access needed
            </label>
            <Button type="submit" busy={search.isPending} className="w-full">
              <Search className="h-4 w-4" /> Find rooms
            </Button>
          </form>
          <div className="mt-4">
            <CampusMap highlight={byBuilding} selected={building ? Number(building) : null} onSelect={(id) => setBuilding(String(id))} />
          </div>
        </Card>

        <div className="space-y-4">
          {search.isPending && <LoadingRows rows={5} />}
          {search.isError && <ErrorBox error={search.error} />}
          {search.data && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm">
                  <strong>{search.data.hits.length}</strong> of {search.data.considered} rooms are free {search.data.windows.length > 1 ? `on all ${search.data.windows.length} dates` : ""}
                </p>
                <Button variant="outline" onClick={() => setDrawer(true)}>
                  Why not the other {search.data.why_not.length}?
                </Button>
              </div>
              {search.data.hits.length === 0 && <Empty>No room is free for the whole window. Open “Why not” to see the first blocker for each room.</Empty>}
              <div className="grid gap-3 md:grid-cols-2">
                {search.data.hits.map((hit) => (
                  <Card key={hit.venue_id}>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="text-lg font-semibold">{hit.code}</div>
                        <div className="text-xs text-muted">
                          {hit.name} · seats {hit.capacity}
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <StatusBadge state={hit.state} />
                        <span className="text-xs text-muted">score {hit.score}</span>
                      </div>
                    </div>
                    <ul className="mt-2 space-y-1 text-xs text-muted">
                      {hit.reasons.map((reason) => (
                        <li key={reason}>• {reason}</li>
                      ))}
                    </ul>
                    <div className="mt-2 flex flex-wrap items-center gap-1">
                      {hit.features.map((feature) => (
                        <Badge key={feature}>{feature}</Badge>
                      ))}
                      {hit.walking_min !== null && (
                        <Badge tone="info">
                          <Footprints className="h-3 w-3" /> {hit.walking_min} min
                        </Badge>
                      )}
                    </div>
                    {canBook && (
                      <div className="mt-3 flex gap-2">
                        <Input value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Event title" className="text-xs" />
                        <Button variant="outline" onClick={() => book.mutate(hit)} busy={book.isPending && book.variables?.venue_id === hit.venue_id}>
                          Propose
                        </Button>
                      </div>
                    )}
                  </Card>
                ))}
              </div>
              <p className="text-xs text-muted">
                Window: {fmtDateTime(search.data.windows[0][0])} → {fmtDateTime(search.data.windows[0][1])}
              </p>
            </>
          )}
          {book.isError && <ErrorBox error={book.error} />}
          {proposal && <ProposalCard proposal={proposal} onDiscard={() => setProposal(null)} />}
        </div>
      </div>
      <Drawer open={drawer} onClose={() => setDrawer(false)} title="Why these rooms were rejected">
        <Input placeholder="Filter, e.g. A-1 or timetable" value={filter} onChange={(e) => setFilter(e.target.value)} className="mb-3" />
        <ul className="space-y-2 text-sm">
          {rejected.map((row) => (
            <li key={row.venue + row.reason} className="rounded-lg border border-line p-2">
              {row.reason}
              {row.ghost && <Badge tone="ghost"> ghost candidate</Badge>}
            </li>
          ))}
        </ul>
      </Drawer>
    </>
  );
}
