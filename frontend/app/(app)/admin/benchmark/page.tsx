"use client";

import { useMutation } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { Badge, Button, Card, ErrorBox, Notice, PageHeader, Stat, StatusBadge } from "@/components/ui";
import { api } from "@/lib/api";

interface Method {
  method: string;
  accepted: number;
  weighted_satisfaction: number;
  capacity_waste: number;
  runtime_ms: number;
  status: string;
}

interface Bench {
  venues: number;
  search_latency: { days: number; p50_ms: number; p95_ms: number }[];
  batch: { events: number; greedy: Method; cp_sat: Method };
}

interface Race {
  venue: string;
  racers: number;
  winners: number;
  conflicts: number;
  other: string[];
  validator_violations: unknown[];
  elapsed_ms: number;
}

export default function BenchmarkPage() {
  const bench = useMutation({ mutationFn: () => api<Bench>("/benchmark/run", { params: { events: 25 } }) });
  const race = useMutation({ mutationFn: () => api<Race>("/simulate/race", { params: { racers: 20 }, method: "POST" }) });
  const chart = bench.data ? [
    { metric: "Accepted events", greedy: bench.data.batch.greedy.accepted, optimiser: bench.data.batch.cp_sat.accepted },
    { metric: "Weighted satisfaction / 100", greedy: Math.round(bench.data.batch.greedy.weighted_satisfaction / 100), optimiser: Math.round(bench.data.batch.cp_sat.weighted_satisfaction / 100) },
  ] : [];
  return (
    <>
      <PageHeader title="Batch Optimiser & Benchmark" subtitle="A fest-week scenario: CP-SAT versus first-come-first-served, the concurrency race, and availability-search latency." />
      <div className="mb-4 flex flex-wrap gap-2"><Button onClick={() => bench.mutate()} busy={bench.isPending}>Run optimiser and latency benchmark</Button><Button variant="outline" onClick={() => race.mutate()} busy={race.isPending}>Run 20-way race</Button></div>
      {bench.isError && <ErrorBox error={bench.error} />}
      {bench.data && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title={`Fest scenario: ${bench.data.batch.events} event requests`}>
            <div className="h-56"><ResponsiveContainer><BarChart data={chart}><CartesianGrid strokeDasharray="3 3" stroke="var(--line)" /><XAxis dataKey="metric" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} /><Tooltip /><Legend /><Bar dataKey="greedy" name="Greedy (FCFS)" fill="var(--layer-maintenance)" radius={[4, 4, 0, 0]} /><Bar dataKey="optimiser" name="CP-SAT" fill="var(--primary)" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>
            <div className="mt-2 grid grid-cols-2 gap-3 text-sm">
              {([["Greedy", bench.data.batch.greedy], ["CP-SAT", bench.data.batch.cp_sat]] as [string, Method][]).map(([name, m]) => (
                <div key={name} className="rounded-lg border border-line p-2"><div className="font-medium">{name} <StatusBadge state={m.status === "OK" ? "OPTIMAL" : m.status} /></div><div className="text-xs text-muted">accepted {m.accepted} · satisfaction {m.weighted_satisfaction} · waste {(m.capacity_waste * 100).toFixed(0)}% · {m.runtime_ms} ms</div></div>
              ))}
            </div>
          </Card>
          <Card title={`Availability search latency (${bench.data.venues} venues)`}>
            <div className="h-56"><ResponsiveContainer><BarChart data={bench.data.search_latency.map((l) => ({ range: `${l.days} day${l.days > 1 ? "s" : ""}`, p50: l.p50_ms, p95: l.p95_ms }))}><CartesianGrid strokeDasharray="3 3" stroke="var(--line)" /><XAxis dataKey="range" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} unit=" ms" /><Tooltip /><Legend /><Bar dataKey="p50" fill="var(--good)" radius={[4, 4, 0, 0]} /><Bar dataKey="p95" fill="var(--warn)" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>
            <p className="mt-2 text-xs text-muted">Target: p95 under 50 ms across every venue over a week.</p>
          </Card>
        </div>
      )}
      {race.isError && <ErrorBox error={race.error} />}
      {race.data && (
        <Card className="mt-4" title={`Concurrency race for ${race.data.venue}`}>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4"><Stat label="Racers" value={race.data.racers} /><Stat label="Winners" value={race.data.winners} tone={race.data.winners === 1 ? "good" : "bad"} /><Stat label="Conflicts with alternatives" value={race.data.conflicts} /><Stat label="Validator violations" value={race.data.validator_violations.length} tone={race.data.validator_violations.length ? "bad" : "good"} /></div>
          <div className="mt-3">{race.data.winners === 1 && race.data.validator_violations.length === 0 ? <Notice tone="good">Exactly one confirmation won, the other {race.data.conflicts} were turned away with alternatives, and the independent validator found 0 violations ({race.data.elapsed_ms} ms).</Notice> : <Notice tone="bad">Unexpected outcome: {JSON.stringify(race.data.other)}</Notice>}</div>
          <Badge tone="info">Demo state changed by one booking; use Reset demo data in the Command Center</Badge>
        </Card>
      )}
    </>
  );
}
