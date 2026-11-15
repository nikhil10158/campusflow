"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { Badge, Card, Empty, ErrorBox, Field, LoadingRows, PageHeader, Select, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";
import { WEEKDAYS, addDays, minToHHMM, weekdayOf } from "@/lib/format";
import { useNow, useSections } from "@/lib/hooks";
import type { SearchResult } from "@/lib/types";

interface TimetableEntry {
  entry_id: number;
  weekday: number;
  date: string;
  start_min: number;
  end_min: number;
  course_code: string;
  course_name: string;
  kind: string;
  venue_code: string;
  faculty: string;
  exception: string | null;
  holiday: boolean;
}

interface Heat {
  total_rooms: number;
  periods: string[][];
  cells: { weekday: number; period: number; start: string; end: string; free_rooms: number }[];
}

const KIND_STYLE: Record<string, string> = { lecture: "bg-infobg text-info", tutorial: "bg-warnbg text-warn", lab: "bg-goodbg text-good" };

function toMinutes(text: string): number {
  const [h, m] = text.split(":").map(Number);
  return h * 60 + m;
}

function WeeklyGrid({ entries, periods }: { entries: TimetableEntry[]; periods: string[][] }) {
  const starts = periods.map((p) => toMinutes(p[0]));
  const ends = periods.map((p) => toMinutes(p[1]));
  return (
    <div className="overflow-x-auto">
      <div className="grid min-w-[760px] gap-1" style={{ gridTemplateColumns: `56px repeat(${periods.length}, minmax(0, 1fr))` }}>
        <div />
        {periods.map((period) => (
          <div key={period[0]} className="text-center text-[11px] text-muted">{period[0]}–{period[1]}</div>
        ))}
        {WEEKDAYS.slice(0, 6).map((name, weekday) => {
          const cells: React.ReactNode[] = [];
          let index = 0;
          while (index < periods.length) {
            const entry = entries.find((e) => e.weekday === weekday && e.start_min === starts[index]);
            if (entry) {
              const last = ends.findIndex((end) => end === entry.end_min);
              const span = Math.max(1, last - index + 1);
              cells.push(
                <div key={entry.entry_id} style={{ gridColumn: `span ${span}` }} className={`rounded-lg p-1.5 text-[11px] leading-tight ${KIND_STYLE[entry.kind]} ${entry.exception ? "opacity-50 line-through" : ""}`} title={`${entry.course_name} · ${entry.faculty}`}>
                  <div className="font-semibold">{entry.course_code}</div>
                  <div>{entry.venue_code}</div>
                  <div className="truncate opacity-80">{entry.faculty}</div>
                  {entry.exception && <div>{entry.exception}</div>}
                </div>,
              );
              index += span;
            } else {
              cells.push(<div key={`e${weekday}-${index}`} className="min-h-[56px] rounded-lg bg-surface2/50" />);
              index += 1;
            }
          }
          return (
            <div key={name} className="contents">
              <div className="flex items-center text-xs font-medium">{name}</div>
              {cells}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function TimetablePage() {
  const { data: sections } = useSections();
  const { data: now } = useNow();
  const [dept, setDept] = useState("CSE");
  const [semester, setSemester] = useState(5);
  const [name, setName] = useState("A");
  const today = (now?.now ?? "2026-11-16").slice(0, 10);
  const section = sections?.find((s) => s.dept === dept && s.semester === semester && s.name === name);

  const timetable = useQuery({ queryKey: ["section-timetable", section?.id], queryFn: () => api<{ section: { size: number }; entries: TimetableEntry[]; periods: string[][] }>(`/timetable/sections/${section?.id}`), enabled: !!section });
  const heat = useQuery({ queryKey: ["heatmap", today], queryFn: () => api<Heat>("/availability/heatmap", { params: { start: addDays(today, -21), end: addDays(today, 21), type: "classroom" } }) });
  const drill = useMutation({
    mutationFn: async (cell: Heat["cells"][number]) => {
      let day = addDays(today, 1);
      while (weekdayOf(day) !== cell.weekday) day = addDays(day, 1);
      const result = await api<SearchResult>("/availability/search", { params: { start: `${day}T${cell.start}:00`, end: `${day}T${cell.end}:00`, types: "classroom,seminar_hall" } });
      return { day, cell, result };
    },
  });

  const periods = timetable.data?.periods ?? heat.data?.periods ?? [];
  const max = useMemo(() => Math.max(1, ...(heat.data?.cells.map((c) => c.free_rooms) ?? [1])), [heat.data]);
  const weeks = useMemo(() => Array.from(new Set(sections?.map((s) => s.dept))), [sections]);

  return (
    <>
      <PageHeader title="Cross-Semester Explorer" subtitle="Any section's weekly timetable, plus how many classrooms are free in every weekday and period across all semesters." />
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="Section timetable">
          <div className="mb-3 flex flex-wrap gap-2">
            <Field label="Department">
              <Select value={dept} onChange={(e) => setDept(e.target.value)}>{weeks.map((d) => <option key={d}>{d}</option>)}</Select>
            </Field>
            <Field label="Semester">
              <Select value={semester} onChange={(e) => setSemester(Number(e.target.value))}>{[1, 3, 5, 7].map((s) => <option key={s} value={s}>{s}</option>)}</Select>
            </Field>
            <Field label="Section">
              <Select value={name} onChange={(e) => setName(e.target.value)}><option>A</option><option>B</option></Select>
            </Field>
            {section && <Badge tone="info">{section.size} students</Badge>}
          </div>
          {timetable.isPending && <LoadingRows rows={6} />}
          {timetable.isError && <ErrorBox error={timetable.error} />}
          {timetable.data && <WeeklyGrid entries={timetable.data.entries} periods={timetable.data.periods} />}
          <div className="mt-3 flex gap-2 text-xs">
            <span className="rounded bg-infobg px-2 py-0.5 text-info">lecture</span>
            <span className="rounded bg-warnbg px-2 py-0.5 text-warn">tutorial</span>
            <span className="rounded bg-goodbg px-2 py-0.5 text-good">lab</span>
          </div>
        </Card>
        <Card title={`Free classrooms by weekday and period (of ${heat.data?.total_rooms ?? "…"})`}>
          {heat.isPending && <LoadingRows rows={6} />}
          {heat.data && (
            <div className="overflow-x-auto">
              <div className="grid min-w-[560px] gap-1" style={{ gridTemplateColumns: `56px repeat(${periods.length}, minmax(0, 1fr))` }}>
                <div />
                {periods.map((p) => <div key={p[0]} className="text-center text-[11px] text-muted">{p[0]}</div>)}
                {WEEKDAYS.slice(0, 6).map((day, weekday) => (
                  <div key={day} className="contents">
                    <div className="flex items-center text-xs font-medium">{day}</div>
                    {periods.map((_, period) => {
                      const cell = heat.data.cells.find((c) => c.weekday === weekday && c.period === period);
                      if (!cell) return <div key={period} className="rounded bg-surface2/40" />;
                      return (
                        <button key={period} onClick={() => drill.mutate(cell)} aria-label={`${day} ${cell.start}: ${cell.free_rooms} free rooms`} className="rounded p-2 text-xs font-semibold tabular-nums text-ink hover:ring-2 hover:ring-primary" style={{ background: `color-mix(in srgb, var(--primary) ${Math.round((cell.free_rooms / max) * 70) + 8}%, var(--surface))` }}>
                          {Math.round(cell.free_rooms)}
                        </button>
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>
          )}
          <p className="mt-2 text-xs text-muted">Click a cell for the actual free rooms on the next matching date.</p>
          {drill.data && (
            <div className="mt-3 rounded-lg border border-line p-3">
              <p className="mb-2 text-sm font-medium">{drill.data.day} {drill.data.cell.start}–{drill.data.cell.end}: {drill.data.result.hits.length} free rooms</p>
              <div className="flex flex-wrap gap-2">
                {drill.data.result.hits.slice(0, 24).map((hit) => (
                  <span key={hit.code} className="inline-flex items-center gap-1 text-xs">
                    <Badge>{hit.code} · {hit.capacity}</Badge>{hit.state === "FREE_RELEASED" && <StatusBadge state="FREE_RELEASED" />}
                  </span>
                ))}
                {drill.data.result.hits.length === 0 && <Empty>No room is free then.</Empty>}
              </div>
            </div>
          )}
        </Card>
      </div>
      <p className="mt-3 text-xs text-muted">Timetable shows {minToHHMM(540)} onward; struck-through classes were cancelled or released by an approved exception.</p>
    </>
  );
}
