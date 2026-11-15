"use client";

import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import {
  Activity, BarChart3, Bell, Building2, CalendarClock, Car, ClipboardCheck, FlaskConical, Gauge, Hotel, LayoutDashboard, LogOut, MapPin, Moon, ScrollText,
  Search, ShieldCheck, Sparkles, Sun, Timer, Upload, Users, Wrench, Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ComponentType, type ReactNode } from "react";

import { api } from "@/lib/api";
import { useAuth, type User } from "@/lib/store";
import type { AgentStatus } from "@/lib/types";
import { fmtDateTime } from "@/lib/format";

import { Badge, Toasts, cx } from "./ui";

interface NavItem {
  href: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
  roles: User["role"][];
}

const ALL: User["role"][] = ["admin", "approver", "faculty", "student"];
const STAFF: User["role"][] = ["admin", "approver", "faculty"];

const NAV: NavItem[] = [
  { href: "/", label: "Concierge", icon: Sparkles, roles: ALL },
  { href: "/admin", label: "Command Center", icon: LayoutDashboard, roles: ["admin"] },
  { href: "/faculty", label: "My Day", icon: Users, roles: ["faculty"] },
  { href: "/student", label: "My Requests", icon: Users, roles: ["student"] },
  { href: "/find", label: "Free Rooms", icon: Search, roles: ALL },
  { href: "/timeline", label: "Venue Timeline", icon: Activity, roles: ALL },
  { href: "/timetable", label: "Timetables", icon: CalendarClock, roles: ALL },
  { href: "/cohort", label: "Cohort Slots", icon: Timer, roles: STAFF },
  { href: "/labs", label: "Labs", icon: FlaskConical, roles: STAFF },
  { href: "/amphitheatres", label: "Amphitheatres", icon: Building2, roles: STAFF },
  { href: "/guesthouse", label: "Guest House", icon: Hotel, roles: STAFF },
  { href: "/parking", label: "Parking", icon: Car, roles: STAFF },
  { href: "/approvals", label: "Approvals", icon: ClipboardCheck, roles: ["admin", "approver"] },
  { href: "/policies", label: "Policies", icon: ScrollText, roles: ["admin", "approver", "faculty", "student", "security"] },
  { href: "/security", label: "Gate Scan", icon: ShieldCheck, roles: ["admin", "security"] },
  { href: "/admin/timetables", label: "Timetable Import", icon: Upload, roles: ["admin"] },
  { href: "/admin/disruptions", label: "Disruptions", icon: Wrench, roles: ["admin"] },
  { href: "/admin/reports", label: "Utilisation", icon: BarChart3, roles: ["admin"] },
  { href: "/admin/benchmark", label: "Benchmark", icon: Gauge, roles: ["admin"] },
  { href: "/admin/audit", label: "Audit & Outbox", icon: Bell, roles: ["admin"] },
];

function useTheme(): [boolean, () => void] {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem("campusflow-theme");
    } catch {
      stored = null;
    }
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const value = stored ? stored === "dark" : prefersDark;
    setDark(value);
    document.documentElement.classList.toggle("dark", value);
  }, []);
  const toggle = () => {
    const value = !dark;
    setDark(value);
    document.documentElement.classList.toggle("dark", value);
    try {
      window.localStorage.setItem("campusflow-theme", value ? "dark" : "light");
    } catch {
      return;
    }
  };
  return [dark, toggle];
}

function AiBadge() {
  const { data } = useQuery({ queryKey: ["agent-status"], queryFn: () => api<AgentStatus>("/agent/status"), refetchInterval: 30000 });
  if (!data) return null;
  const used = data.daily_limit ? Math.min(100, Math.round((data.calls_today / data.daily_limit) * 100)) : 0;
  return (
    <div className="flex items-center gap-2" title={data.model ? `Model ${data.model}` : "No Gemini key: deterministic offline mode"}>
      <Badge tone={data.mode === "live" ? "good" : data.mode === "degraded" ? "warn" : "neutral"}>
        <Zap className="h-3 w-3" aria-hidden /> AI: {data.mode}
      </Badge>
      {data.mode !== "offline" && (
        <div className="hidden h-1.5 w-16 overflow-hidden rounded bg-surface2 sm:block" aria-label={`${used}% of daily AI quota used`}>
          <div className={cx("h-full", used > 80 ? "bg-bad" : "bg-primary")} style={{ width: `${used}%` }} />
        </div>
      )}
    </div>
  );
}

function ClockChip() {
  const { data } = useQuery({ queryKey: ["demo-now"], queryFn: () => api<{ now: string }>("/demo/now"), refetchInterval: 15000 });
  if (!data) return null;
  return (
    <Badge tone="info" title="Demo clock: every time-based rule uses this instead of the real time">
      <Timer className="h-3 w-3" aria-hidden /> {fmtDateTime(data.now)}
    </Badge>
  );
}

function Palette({ items, open, setOpen }: { items: NavItem[]; open: boolean; setOpen: (value: boolean) => void }) {
  const router = useRouter();
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen(!open);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, setOpen]);
  return (
    <Command.Dialog open={open} onOpenChange={setOpen} label="Go to page" className="fixed left-1/2 top-24 z-50 w-[min(32rem,92vw)] -translate-x-1/2 overflow-hidden rounded-xl border border-line bg-surface shadow-2xl">
      <Command.Input placeholder="Jump to a page..." className="w-full border-b border-line bg-transparent px-4 py-3 text-sm outline-none" />
      <Command.List className="max-h-80 overflow-y-auto p-2">
        <Command.Empty className="p-3 text-sm text-muted">No page matches</Command.Empty>
        {items.map((item) => (
          <Command.Item
            key={item.href}
            value={item.label}
            onSelect={() => {
              router.push(item.href);
              setOpen(false);
            }}
            className="flex cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm data-[selected=true]:bg-surface2"
          >
            <item.icon className="h-4 w-4 text-muted" /> {item.label}
          </Command.Item>
        ))}
      </Command.List>
    </Command.Dialog>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [dark, toggleTheme] = useTheme();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const items = NAV.filter((item) => user && item.roles.includes(user.role));
  const active = (href: string) => (href === "/" ? pathname === "/" : pathname === href || (href !== "/admin" && pathname.startsWith(`${href}/`)));
  return (
    <div className="flex min-h-screen flex-col">
      <div className="bg-warnbg px-4 py-1 text-center text-xs font-medium text-warn">SYNTHETIC — JKLU-like demo campus. All data, calendars, emails and payments are mocks.</div>
      <div className="flex flex-1">
        <aside className="hidden w-56 shrink-0 flex-col border-r border-line bg-surface p-3 lg:flex">
          <Link href="/" className="mb-4 flex items-center gap-2 px-2 text-lg font-semibold tracking-tight">
            <MapPin className="h-5 w-5 text-primary" aria-hidden /> CampusFlow
          </Link>
          <nav className="flex-1 space-y-0.5 overflow-y-auto" aria-label="Main">
            {items.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={cx("flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm", active(item.href) ? "bg-primary/10 font-medium text-primary" : "text-muted hover:bg-surface2 hover:text-ink")}
              >
                <item.icon className="h-4 w-4" aria-hidden /> {item.label}
              </Link>
            ))}
          </nav>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface px-4 py-2">
            <div className="flex flex-wrap items-center gap-3">
              <select
                aria-label="Go to page"
                className="rounded-lg border border-line bg-surface px-2 py-1 text-sm lg:hidden"
                value={items.find((i) => active(i.href))?.href ?? ""}
                onChange={(event) => router.push(event.target.value)}
              >
                {items.map((item) => (
                  <option key={item.href} value={item.href}>
                    {item.label}
                  </option>
                ))}
              </select>
              <button onClick={() => setPaletteOpen(true)} className="hidden items-center gap-2 rounded-lg border border-line px-3 py-1 text-xs text-muted hover:bg-surface2 sm:flex">
                <Search className="h-3 w-3" /> Jump to… <kbd className="rounded bg-surface2 px-1">Ctrl K</kbd>
              </button>
              <AiBadge />
              <ClockChip />
            </div>
            <div className="flex items-center gap-2">
              <span className="hidden text-xs text-muted sm:inline">
                {user?.name} · <Badge>{user?.role}</Badge>
              </span>
              <button onClick={toggleTheme} aria-label="Toggle theme" className="rounded-lg p-2 hover:bg-surface2">
                {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </button>
              <button
                onClick={() => {
                  logout();
                  router.push("/login");
                }}
                aria-label="Sign out"
                className="rounded-lg p-2 hover:bg-surface2"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </header>
          <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-5">{children}</main>
          <footer className="border-t border-line px-4 py-2 text-center text-xs text-muted">SYNTHETIC DATA — demo only. Every state change needs a human action; the assistant only proposes.</footer>
        </div>
      </div>
      <Palette items={items} open={paletteOpen} setOpen={setPaletteOpen} />
      <Toasts />
    </div>
  );
}
