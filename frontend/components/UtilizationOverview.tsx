"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";

import { Badge, Card, Empty, ErrorBox, LoadingRows, Stat } from "./ui";

interface Summary {
  total_bookings: number;
  by_status: Record<string, number>;
  most_used: { venue_id: number; code: string; name: string; type: string; capacity: number; bookings: number; hours: number }[];
  resources: { rooms_total: number; rooms_available: number; guest_rooms_total: number; guest_rooms_available: number; parking_lots: number; available_by_type: Record<string, number> };
  vacant_now: { count: number; by_type: Record<string, number>; rooms: { code: string; type: string; capacity: number }[] };
  monthly: { month: string; bookings: number; hours: number; utilisation_pct: number }[];
}

const TYPE = (value: string) => value.replace("_", " ");

export function UtilizationOverview() {
  const summary = useQuery({ queryKey: ["utilization-summary"], queryFn: () => api<Summary>("/reports/utilization-summary"), refetchInterval: 30000 });
  if (summary.isPending) return <div className="mt-6"><LoadingRows rows={3} /></div>;
  if (summary.isError) return <div className="mt-6"><ErrorBox error={summary.error} /></div>;
  const data = summary.data;
  const topBookings = Math.max(1, ...data.most_used.map((row) => row.bookings));
  const topHours = Math.max(1, ...data.monthly.map((row) => row.hours));
  return (
    <section className="mt-6" aria-label="Resource utilization">
      <h2 className="mb-3 text-2xl font-semibold tracking-tight">Resource utilization</h2>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Total bookings" value={data.total_bookings} />
        <Stat label="Rooms available" value={data.resources.rooms_available} tone="good" />
        <Stat label="Vacant right now" value={data.vacant_now.count} tone={data.vacant_now.count ? "good" : "warn"} />
        <Stat label="Guest rooms available" value={data.resources.guest_rooms_available} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Booking statistics">
          <div className="flex flex-wrap gap-2">
            {Object.entries(data.by_status).sort((a, b) => b[1] - a[1]).map(([status, count]) => <Badge key={status}>{status.replace(/_/g, " ").toLowerCase()}: {count}</Badge>)}
          </div>
          <p className="mt-3 text-sm text-muted">Available resources: {data.resources.rooms_available} of {data.resources.rooms_total} rooms ({Object.entries(data.resources.available_by_type).map(([type, count]) => `${count} ${TYPE(type)}`).join(", ")}), {data.resources.guest_rooms_available} of {data.resources.guest_rooms_total} guest rooms, {data.resources.parking_lots} parking lots.</p>
        </Card>
        <Card title="Vacant right now">
          {data.vacant_now.rooms.length === 0 ? <Empty>No room is free at this moment.</Empty> : (
            <div className="flex flex-wrap gap-2">
              {data.vacant_now.rooms.map((room) => <Badge key={room.code} tone="good" title={`${TYPE(room.type)}, seats ${room.capacity}`}>{room.code}</Badge>)}
              {data.vacant_now.count > data.vacant_now.rooms.length && <Badge>+{data.vacant_now.count - data.vacant_now.rooms.length} more</Badge>}
            </div>
          )}
          <p className="mt-3 text-sm text-muted">Checked against classes, bookings, holds and maintenance at the demo time.</p>
        </Card>
        <Card title="Most frequently used rooms">
          {data.most_used.length === 0 ? <Empty>No confirmed room bookings yet.</Empty> : (
            <ul className="space-y-2">
              {data.most_used.map((row) => (
                <li key={row.venue_id} className="text-sm">
                  <div className="flex items-center justify-between"><span><strong>{row.code}</strong> <span className="text-muted">{TYPE(row.type)}, seats {row.capacity}</span></span><span className="text-muted">{row.bookings} booking{row.bookings === 1 ? "" : "s"} · {row.hours} h</span></div>
                  <div className="mt-1 h-2 rounded-full bg-surface2"><div className="h-2 rounded-full bg-brand" style={{ width: `${(100 * row.bookings) / topBookings}%` }} /></div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title="Monthly room utilization">
          {data.monthly.length === 0 ? <Empty>No confirmed room bookings yet.</Empty> : (
            <ul className="space-y-2">
              {data.monthly.map((row) => (
                <li key={row.month} className="text-sm">
                  <div className="flex items-center justify-between"><strong>{row.month}</strong><span className="text-muted">{row.bookings} bookings · {row.hours} h · {row.utilisation_pct}% of bookable hours</span></div>
                  <div className="mt-1 h-2 rounded-full bg-surface2"><div className="h-2 rounded-full bg-bar" style={{ width: `${(100 * row.hours) / topHours}%` }} /></div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </section>
  );
}
