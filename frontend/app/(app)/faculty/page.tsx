"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { Badge, Button, Card, Empty, LoadingRows, PageHeader, StatusBadge, QuickTiles } from "@/components/ui";
import { api } from "@/lib/api";
import { WEEKDAYS, addDays, fmtDateTime, minToHHMM, weekdayOf } from "@/lib/format";
import { useNow } from "@/lib/hooks";
import { useAuth, useToasts } from "@/lib/store";
import type { Booking } from "@/lib/types";

interface Row {
  entry_id: number;
  weekday: number;
  date: string;
  start_min: number;
  end_min: number;
  course_code: string;
  kind: string;
  venue_code: string;
  faculty: string;
  exception: string | null;
}

interface Section {
  id: number;
  dept: string;
  semester: number;
  name: string;
}

export default function FacultyPage() {
  const user = useAuth((state) => state.user);
  const push = useToasts((state) => state.push);
  const { data: now } = useNow();
  const today = (now?.now ?? "2026-11-16").slice(0, 10);
  const sections = useQuery({ queryKey: ["sections-faculty"], queryFn: () => api<Section[]>("/sections") });
  const mine = useQuery({
    queryKey: ["my-classes", user?.ref_id, sections.data?.length],
    enabled: !!sections.data,
    queryFn: async () => {
      const results = await Promise.all((sections.data ?? []).filter((s) => s.dept === user?.dept).map((s) => api<{ entries: Row[]; section: Section }>(`/timetable/sections/${s.id}`)));
      return results.flatMap((r) => r.entries.filter((e) => e.faculty === user?.name).map((e) => ({ ...e, section: `${r.section.dept} Sem ${r.section.semester}-${r.section.name}` })));
    },
  });
  const bookings = useQuery({ queryKey: ["bookings-mine"], queryFn: () => api<Booking[]>("/bookings") });
  const release = useMutation({
    mutationFn: (row: Row) => {
      let day = today;
      while (weekdayOf(day) !== row.weekday || day <= today) day = addDays(day, 1);
      return api("/exceptions/propose-release", { body: { entry_id: row.entry_id, date: day, reason: "Class will not be held" } });
    },
    onSuccess: () => push("good", "Release proposed; the head of department must approve it"),
    onError: (e) => push("bad", e instanceof Error ? e.message : "Could not propose"),
  });
  const weekday = weekdayOf(today);
  const todays = (mine.data ?? []).filter((c) => c.weekday === weekday).sort((a, b) => a.start_min - b.start_min);
  const owned = (bookings.data ?? []).filter((b) => b.requester_id === user?.id);

  return (
    <>
      <PageHeader title={`Hello, ${user?.name ?? ""}`} subtitle="Today's classes, release proposals for slots you will not use, and your own booking requests." actions={<Link href="/find" className="text-sm text-primary underline">Quick room finder</Link>} />
      <QuickTiles items={[
        { href: "/", title: "Ask the planner", text: "Plan a workshop, quiz or event in one sentence." },
        { href: "/find", title: "Find a room", text: "See what is free right now, with reasons." },
        { href: "/cohort", title: "Common slot", text: "Find a time when all your sections are free." },
        { href: "/labs", title: "Book a lab", text: "Eligibility and safety rules are checked for you." },
      ]} />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={`Today (${WEEKDAYS[weekday]} ${today})`}>
          {mine.isPending ? <LoadingRows rows={3} /> : todays.length === 0 ? <Empty>No classes today.</Empty> : (
            <ul className="space-y-2">{todays.map((c) => <li key={c.entry_id} className="flex items-center justify-between rounded-lg border border-line p-2 text-sm"><span><strong>{c.course_code}</strong> · {minToHHMM(c.start_min)}–{minToHHMM(c.end_min)} · {c.venue_code}<div className="text-xs text-muted">{(c as unknown as { section: string }).section}</div></span><Badge>{c.kind}</Badge></li>)}</ul>
          )}
        </Card>
        <Card title="Release one of my class slots (proposal)">
          {mine.isPending ? <LoadingRows rows={3} /> : (
            <ul className="max-h-72 space-y-1 overflow-y-auto">{(mine.data ?? []).filter((c) => c.kind === "lecture").slice(0, 14).map((c) => <li key={c.entry_id} className="flex items-center justify-between text-sm"><span>{c.course_code} · {WEEKDAYS[c.weekday]} {minToHHMM(c.start_min)} · {c.venue_code}</span><Button variant="outline" onClick={() => release.mutate(c)}>Release next</Button></li>)}</ul>
          )}
        </Card>
        <Card title="My requests" className="lg:col-span-2">
          {owned.length === 0 ? <Empty>No requests yet. Ask the Concierge to plan one.</Empty> : (
            <ul className="space-y-1 text-sm">{owned.map((b) => <li key={b.id} className="flex flex-wrap items-center justify-between gap-2 border-b border-line py-1"><span>#{b.id} {b.event_title} · {fmtDateTime(b.start)}</span><span className="flex items-center gap-2">{b.bundle_id && <Link className="text-xs text-primary underline" href={`/bundles/${b.bundle_id}`}>bundle</Link>}<StatusBadge state={b.status} /></span></li>)}</ul>
          )}
        </Card>
      </div>
    </>
  );
}
