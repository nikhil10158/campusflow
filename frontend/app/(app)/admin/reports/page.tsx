"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { BadgeCheck, FileDown } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Badge, Button, Card, ErrorBox, LoadingRows, PageHeader, Stat } from "@/components/ui";
import { api, download } from "@/lib/api";
import { WEEKDAYS } from "@/lib/format";
import { useToasts } from "@/lib/store";

interface Kpis {
  period: { start: string; end: string };
  classroom_time_utilisation_pct: number;
  seat_utilisation_pct: number;
  peak_utilisation_pct: number;
  off_peak_utilisation_pct: number;
  by_building: Record<string, number>;
  by_type: Record<string, number>;
  hourly: { hour: number; utilisation: number }[];
  fragmentation: { unusable_gap_hours: number; fragmentation_ratio: number };
  ghost_classes: number;
  ghost_bookable_hours_per_week: number;
  guest_house: { occupancy_pct: number; revenue: number };
  parking: { peak_car_utilisation_pct: number; no_show_rate_pct: number };
}

interface Ghost {
  entry_id: number;
  course_code: string;
  section: string;
  venue_code: string;
  weekday: number;
  start_min: number;
  mean_ratio: number;
  sparkline: number[];
  weekly_hours: number;
  next_date: string;
  released_already: boolean;
}

function Spark({ values }: { values: number[] }) {
  const points = values.map((v, i) => `${(i / Math.max(1, values.length - 1)) * 60},${22 - Math.min(1, v) * 20}`).join(" ");
  return <svg viewBox="0 0 60 24" className="h-6 w-16" aria-label={`attendance ${values.join(", ")}`}><polyline points={points} fill="none" stroke="var(--ghost)" strokeWidth="2" /></svg>;
}

export default function ReportsPage() {
  const push = useToasts((state) => state.push);
  const narrative = useQuery({ queryKey: ["narrative"], queryFn: () => api<{ kpis: Kpis; text: string; verified: boolean; mode: string }>("/reports/narrative") });
  const ghosts = useQuery({ queryKey: ["ghosts"], queryFn: () => api<{ ghosts: Ghost[]; projected_uplift_hours_per_week: number; threshold: number }>("/reports/ghosts") });
  const propose = useMutation({
    mutationFn: (ghost: Ghost) => api("/exceptions/propose-release", { body: { entry_id: ghost.entry_id, date: ghost.next_date, reason: "Low attendance (ghost class)" } }),
    onSuccess: () => push("good", "Release proposed — the head of department decides"),
    onError: (e) => push("bad", e instanceof Error ? e.message : "Could not propose"),
  });
  const kpis = narrative.data?.kpis;
  const buildings = kpis ? Object.entries(kpis.by_building).map(([name, value]) => ({ name: name.replace("Academic ", "").replace(" Complex", ""), value })) : [];

  return (
    <>
      <PageHeader title="Utilisation & Ghost Classes" subtitle="Numbers are computed in code. The narrative may only use those numbers, and every figure in it is checked." actions={<div className="flex gap-2"><Button variant="outline" onClick={() => download("/reports/monthly.pdf", "monthly-report.pdf")}><FileDown className="h-4 w-4" /> PDF</Button><Button variant="outline" onClick={() => download("/reports/monthly.xlsx", "monthly-report.xlsx")}><FileDown className="h-4 w-4" /> Excel</Button></div>} />
      {narrative.isPending && <LoadingRows rows={3} />}
      {narrative.isError && <ErrorBox error={narrative.error} />}
      {kpis && narrative.data && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Stat label="Classroom time" value={`${kpis.classroom_time_utilisation_pct}%`} />
            <Stat label="Seat use" value={`${kpis.seat_utilisation_pct}%`} />
            <Stat label="Peak vs off-peak" value={`${kpis.peak_utilisation_pct}/${kpis.off_peak_utilisation_pct}%`} />
            <Stat label="Unusable gaps" value={`${kpis.fragmentation.unusable_gap_hours} h`} tone="warn" />
            <Stat label="Parking no-show" value={`${kpis.parking.no_show_rate_pct}%`} />
          </div>
          <Card className="mt-4" title={<span className="flex items-center gap-2">Monthly narrative {narrative.data.verified && <Badge tone="good"><BadgeCheck className="h-3 w-3" /> numbers verified</Badge>}<Badge>{narrative.data.mode}</Badge></span>}>
            <p className="text-sm leading-relaxed">{narrative.data.text}</p>
            <p className="mt-2 text-xs text-muted">Period {kpis.period.start} to {kpis.period.end}</p>
          </Card>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="Utilisation by hour of day">
              <div className="h-56"><ResponsiveContainer><LineChart data={kpis.hourly.map((h) => ({ hour: `${h.hour}:00`, value: Math.round(h.utilisation * 100) }))}><CartesianGrid strokeDasharray="3 3" stroke="var(--line)" /><XAxis dataKey="hour" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} unit="%" /><Tooltip /><Line dataKey="value" stroke="var(--primary)" strokeWidth={2} dot={false} /></LineChart></ResponsiveContainer></div>
            </Card>
            <Card title="Utilisation by building (%)">
              <div className="h-56"><ResponsiveContainer><BarChart data={buildings}><CartesianGrid strokeDasharray="3 3" stroke="var(--line)" /><XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-20} textAnchor="end" height={50} /><YAxis tick={{ fontSize: 10 }} /><Tooltip /><Bar dataKey="value" fill="var(--primary)" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>
            </Card>
          </div>
        </>
      )}
      <Card className="mt-4" title={`Ghost classes (mean attendance below ${Math.round((ghosts.data?.threshold ?? 0.25) * 100)}% in 3 of the last 4 sessions)`} actions={ghosts.data && <Badge tone="ghost">releasing all frees +{ghosts.data.projected_uplift_hours_per_week} bookable h/week</Badge>}>
        {ghosts.isPending ? <LoadingRows rows={3} /> : (
          <ul className="divide-y divide-line">
            {ghosts.data?.ghosts.map((g) => (
              <li key={g.entry_id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <div><strong>{g.course_code}</strong> · {g.section} · {g.venue_code} <span className="text-muted">{WEEKDAYS[g.weekday]} {String(Math.floor(g.start_min / 60)).padStart(2, "0")}:{String(g.start_min % 60).padStart(2, "0")}</span></div>
                <div className="flex items-center gap-3"><Spark values={g.sparkline} /><Badge tone="ghost">{Math.round(g.mean_ratio * 100)}% attend</Badge><Badge>+{g.weekly_hours} h/wk</Badge><Button variant="outline" onClick={() => propose.mutate(g)} disabled={g.released_already} busy={propose.isPending && propose.variables?.entry_id === g.entry_id}>{g.released_already ? "Proposed" : "Propose release"}</Button></div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}
