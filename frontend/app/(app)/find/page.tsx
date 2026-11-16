"use client";

import { useMutation } from "@tanstack/react-query";
import { Footprints, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { CampusMap } from "@/components/CampusMap";
import { ProposalCard } from "@/components/ProposalCard";
import { Badge, Button, Card, Drawer, Empty, ErrorBox, Field, Input, LoadingRows, PageHeader, Select, StatusBadge, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { addDays } from "@/lib/format";
import { useBuildings, useNow } from "@/lib/hooks";
import { proposalFromCheck, type BookingBody, type CheckResponse } from "@/lib/proposal";
import { useAuth } from "@/lib/store";
import type { Proposal, RoomHit, SearchResult } from "@/lib/types";

const TYPES = [["classroom", "Classroom"], ["seminar_hall", "Seminar hall"], ["lab", "Lab"], ["amphitheatre", "Amphitheatre"]];
const FEATURES = ["projector", "ac", "smartboard", "mic", "pcs", "recording"];
const DURATIONS = [[30, "30 min"], [60, "1 h"], [120, "2 h"], [180, "3 h"]] as const;
const SIZES = [20, 40, 60, 100, 200];

function plusMinutes(time: string, minutes: number): string {
  const [h, m] = time.split(":").map(Number);
  const total = Math.min(23 * 60 + 59, h * 60 + m + minutes);
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function Choice({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick} aria-pressed={active} className={cx("chip", active && "!border-primary !bg-tint !text-link")}>
      {children}
    </button>
  );
}

export default function FindPage() {
  const { data: now } = useNow();
  const { data: buildings } = useBuildings();
  const user = useAuth((state) => state.user);
  const today = (now?.now ?? "").slice(0, 10);
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
  const date = day || (today ? addDays(today, 1) : "");
  const proposalBox = useRef<HTMLDivElement>(null);
  const firstRun = useRef(true);

  const search = useMutation({
    mutationFn: () =>
      api<SearchResult>("/availability/search", {
        params: { start: `${date}T${start}:00`, end: `${date}T${end}:00`, attendees, types: types.join(","), optional: features.join(","), building_id: building, accessible, repeat_weeks: repeat },
      }),
  });

  useEffect(() => {
    if (date && firstRun.current) {
      firstRun.current = false;
      search.mutate();
    }
  }, [date]);

  const book = useMutation({
    mutationFn: async (hit: RoomHit) => {
      const body: BookingBody = { resource_type: "venue", resource_id: hit.venue_id, start: `${date}T${start}:00`, end: `${date}T${end}:00`, event_title: title, attendees };
      const check = await api<CheckResponse>("/proposals/check", { body });
      return proposalFromCheck(check, body, hit.code);
    },
    onSuccess: (value) => {
      setProposal(value);
      setTimeout(() => proposalBox.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    },
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
  const duration = (Number(end.slice(0, 2)) * 60 + Number(end.slice(3))) - (Number(start.slice(0, 2)) * 60 + Number(start.slice(3)));
  const whenLabel = date ? new Date(`${date}T00:00`).toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long" }) : "";

  return (
    <>
      <PageHeader
        kicker="Spaces"
        title="Find a free room"
        subtitle="A room counts as free only when no class, booking, hold or maintenance touches the window. Rooms freed by a cancelled class are marked so."
        help={["Pick a day, a start time and how long you need it. Results update when you press Find.", "Open a room card for the reasons it fits. Press Propose to check the rules.", "Wondering about a room that is missing? Use 'Why not the others?' to see the first thing blocking each."]}
      />
      <div className="grid gap-6 xl:grid-cols-[380px_1fr]">
        <Card title="What do you need?">
          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              search.mutate();
            }}
          >
            <div>
              <p className="mb-1.5 font-display text-[13px] font-semibold text-muted">Day</p>
              <div className="mb-2 flex flex-wrap gap-2">
                {today && ([["Today", today], ["Tomorrow", addDays(today, 1)], ["In 2 days", addDays(today, 2)], ["Next week", addDays(today, 7)]] as const).map(([label, value]) => (
                  <Choice key={label} active={date === value} onClick={() => setDay(value)}>{label}</Choice>
                ))}
              </div>
              <Input type="date" value={date} onChange={(e) => setDay(e.target.value)} aria-label="Date" />
              {whenLabel && <p className="mt-1 text-sm text-muted">{whenLabel}</p>}
            </div>
            <div>
              <p className="mb-1.5 font-display text-[13px] font-semibold text-muted">Time</p>
              <div className="grid grid-cols-2 gap-2">
                <Input type="time" value={start} onChange={(e) => setStart(e.target.value)} aria-label="Start time" />
                <Input type="time" value={end} onChange={(e) => setEnd(e.target.value)} aria-label="End time" />
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {DURATIONS.map(([minutes, label]) => (
                  <Choice key={label} active={duration === minutes} onClick={() => setEnd(plusMinutes(start, minutes))}>{label}</Choice>
                ))}
              </div>
            </div>
            <div>
              <p className="mb-1.5 font-display text-[13px] font-semibold text-muted">How many people?</p>
              <div className="flex flex-wrap items-center gap-2">
                {SIZES.map((size) => (
                  <Choice key={size} active={attendees === size} onClick={() => setAttendees(size)}>{size}</Choice>
                ))}
                <Input type="number" min={0} value={attendees} onChange={(e) => setAttendees(Number(e.target.value))} aria-label="Attendees" className="w-24" />
              </div>
            </div>
            <fieldset>
              <legend className="mb-1.5 font-display text-[13px] font-semibold text-muted">What kind of room?</legend>
              <div className="flex flex-wrap gap-2">
                {TYPES.map(([value, label]) => (
                  <Choice key={value} active={types.includes(value)} onClick={() => toggle(types, value, setTypes)}>{label}</Choice>
                ))}
              </div>
            </fieldset>
            <details className="border border-line p-3">
              <summary className="cursor-pointer font-display text-[15px] font-semibold">More options</summary>
              <div className="mt-3 space-y-3">
                <fieldset>
                  <legend className="mb-1.5 text-sm text-muted">Nice to have</legend>
                  <div className="flex flex-wrap gap-2">
                    {FEATURES.map((feature) => (
                      <Choice key={feature} active={features.includes(feature)} onClick={() => toggle(features, feature, setFeatures)}>{feature}</Choice>
                    ))}
                  </div>
                </fieldset>
                <Field label="Close to building">
                  <Select value={building} onChange={(e) => setBuilding(e.target.value)}>
                    <option value="">Anywhere</option>
                    {buildings?.map((b) => (
                      <option key={b.id} value={b.id}>{b.name}</option>
                    ))}
                  </Select>
                </Field>
                <Field label="Repeat weekly for">
                  <Select value={repeat} onChange={(e) => setRepeat(Number(e.target.value))}>
                    {[1, 2, 4, 8].map((n) => (
                      <option key={n} value={n}>{n === 1 ? "just this date" : `${n} weeks`}</option>
                    ))}
                  </Select>
                </Field>
                <label className="flex items-center gap-2 text-[15px]">
                  <input type="checkbox" checked={accessible} onChange={(e) => setAccessible(e.target.checked)} className="h-4 w-4" /> Step-free access needed
                </label>
              </div>
            </details>
            <Button type="submit" busy={search.isPending} className="w-full py-2.5 text-lg">
              <Search className="h-5 w-5" /> Find rooms
            </Button>
          </form>
          <div className="mt-5">
            <CampusMap highlight={byBuilding} selected={building ? Number(building) : null} onSelect={(id) => setBuilding(String(id))} />
          </div>
        </Card>

        <div className="space-y-5">
          {search.isPending && <LoadingRows rows={5} />}
          {search.isError && <ErrorBox error={search.error} />}
          {search.data && (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3 border-l-8 border-primary bg-surface p-3">
                <p className="text-lg">
                  <strong className="font-display text-3xl font-bold">{search.data.hits.length}</strong> of {search.data.considered} rooms are free
                  {search.data.windows.length > 1 ? ` on all ${search.data.windows.length} dates` : ""} · {start}–{end}
                </p>
                <Button variant="outline" onClick={() => setDrawer(true)}>Why not the others?</Button>
              </div>
              {canBook && search.data.hits.length > 0 && (
                <Field label="Name for the booking (used when you press Propose)">
                  <Input value={title} onChange={(e) => setTitle(e.target.value)} />
                </Field>
              )}
              {search.data.hits.length === 0 && (
                <Empty>
                  Nothing is free for the whole window. Try a shorter slot, another time or day, or a different room type, or open "Why not the others?".
                </Empty>
              )}
              <div className="grid gap-4 md:grid-cols-2">
                {search.data.hits.map((hit, index) => (
                  <Card key={hit.venue_id} className={index === 0 ? "ring-2 ring-primary" : ""}>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        {index === 0 && <p className="mb-1 font-display text-xs font-semibold text-muted">Best match</p>}
                        <div className="font-display text-4xl font-bold leading-none">{hit.code}</div>
                        <div className="mt-1 text-[15px] text-muted">{hit.name} · seats {hit.capacity}</div>
                      </div>
                      <StatusBadge state={hit.state} />
                    </div>
                    <ul className="mt-3 space-y-1 text-[15px]">
                      {hit.reasons.map((reason) => (
                        <li key={reason} className="flex gap-2"><span aria-hidden>✓</span>{reason}</li>
                      ))}
                    </ul>
                    <div className="mt-3 flex flex-wrap items-center gap-1.5">
                      {hit.features.map((feature) => (
                        <Badge key={feature}>{feature}</Badge>
                      ))}
                      {hit.walking_min !== null && (
                        <Badge tone="info">
                          <Footprints className="h-3 w-3" /> {hit.walking_min} min walk
                        </Badge>
                      )}
                    </div>
                    {canBook && (
                      <Button className="mt-4 w-full" variant={index === 0 ? "primary" : "outline"} onClick={() => book.mutate(hit)} busy={book.isPending && book.variables?.venue_id === hit.venue_id}>
                        Propose this room
                      </Button>
                    )}
                  </Card>
                ))}
              </div>
            </>
          )}
          {book.isError && <ErrorBox error={book.error} />}
          <div ref={proposalBox} className="scroll-mt-32">
            {proposal && <ProposalCard proposal={proposal} onDiscard={() => setProposal(null)} />}
          </div>
        </div>
      </div>
      <Drawer open={drawer} onClose={() => setDrawer(false)} title="Why not the others?">
        <Input placeholder="Filter, e.g. A-1 or timetable" value={filter} onChange={(e) => setFilter(e.target.value)} className="mb-3" />
        <ul className="space-y-2 text-[15px]">
          {rejected.map((row) => (
            <li key={row.venue + row.reason} className="border border-line p-2">
              {row.reason}
              {row.ghost && <Badge tone="ghost"> ghost candidate</Badge>}
            </li>
          ))}
        </ul>
      </Drawer>
    </>
  );
}
