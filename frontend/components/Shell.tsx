"use client";

import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { LogOut, Menu, Moon, Search, Sun, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import { useAuth, type User } from "@/lib/store";
import type { AgentStatus } from "@/lib/types";

import { Toasts, cx } from "./ui";

type Role = User["role"];

interface NavItem {
  href: string;
  label: string;
  note: string;
  roles: Role[];
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

const ALL: Role[] = ["admin", "approver", "faculty", "student"];
const STAFF: Role[] = ["admin", "approver", "faculty"];

const GROUPS: NavGroup[] = [
  {
    label: "Ask",
    items: [
      { href: "/", label: "Concierge", note: "One sentence becomes a plan", roles: ALL },
      { href: "/admin", label: "Command Center", note: "Clock, alerts, KPIs", roles: ["admin"] },
      { href: "/faculty", label: "My Day", note: "Classes and requests", roles: ["faculty"] },
      { href: "/student", label: "My Requests", note: "Club bookings", roles: ["student"] },
    ],
  },
  {
    label: "Spaces",
    items: [
      { href: "/find", label: "Free Rooms", note: "Search with reasons", roles: ALL },
      { href: "/timeline", label: "Timeline", note: "Drag to test a window", roles: ALL },
      { href: "/timetable", label: "Timetables", note: "All semesters, heatmap", roles: ALL },
      { href: "/cohort", label: "Cohort Slots", note: "Quizzes and extra lectures", roles: STAFF },
      { href: "/labs", label: "Labs", note: "Eligibility and safety", roles: STAFF },
      { href: "/amphitheatres", label: "Amphitheatres", note: "Large events", roles: STAFF },
    ],
  },
  {
    label: "Stay & Park",
    items: [
      { href: "/guesthouse", label: "Guest House", note: "Nights, groups, waitlist", roles: STAFF },
      { href: "/parking", label: "Parking", note: "Lots, passes, no-shows", roles: STAFF },
      { href: "/security", label: "Gate Scan", note: "Verify a pass", roles: ["admin", "security"] },
    ],
  },
  {
    label: "Decide",
    items: [
      { href: "/approvals", label: "Approvals", note: "Scoped inbox", roles: ["admin", "approver"] },
      { href: "/policies", label: "Policies", note: "Cited answers only", roles: ["admin", "approver", "faculty", "student", "security"] },
    ],
  },
  {
    label: "Admin",
    items: [
      { href: "/admin/timetables", label: "Timetable Import", note: "Preview, approve, roll back", roles: ["admin"] },
      { href: "/admin/disruptions", label: "Disruptions", note: "Closures and re-homing", roles: ["admin"] },
      { href: "/admin/reports", label: "Utilisation", note: "Ghosts and narrative", roles: ["admin"] },
      { href: "/admin/benchmark", label: "Benchmark", note: "Optimiser and race", roles: ["admin"] },
      { href: "/admin/audit", label: "Audit & Outbox", note: "Hash-chained log", roles: ["admin"] },
    ],
  },
];

const LINE_COLORS = ["#ffd100", "#00a651", "#ff7a00", "#d4007f", "#00a3ad"];

function visibleGroups(role: Role | undefined): NavGroup[] {
  if (!role) return [];
  return GROUPS.map((group) => ({ ...group, items: group.items.filter((item) => item.roles.includes(role)) })).filter((group) => group.items.length > 0);
}

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || (href !== "/admin" && pathname.startsWith(`${href}/`));
}

function useTheme(): [boolean, () => void] {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    let stored: string | null = null;
    try {
      stored = window.localStorage.getItem("campusflow-theme");
    } catch {
      stored = null;
    }
    const value = stored ? stored === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
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

function Roundel() {
  return (
    <Link href="/" className="flex items-center gap-2.5" aria-label="CampusFlow home">
      <span className="relative grid h-9 w-9 place-items-center rounded-full border-[5px] border-primary" aria-hidden>
        <span className="absolute left-[-9px] right-[-9px] top-1/2 h-3 -translate-y-1/2 bg-boardink" />
        <span className="relative font-display text-xs font-bold leading-none text-board">CF</span>
      </span>
      <span className="font-display text-2xl font-bold uppercase leading-none tracking-[0.12em] text-white">Campusflow</span>
    </Link>
  );
}

function Flaps({ text }: { text: string }) {
  return (
    <span aria-label={text} className="inline-flex text-sm">
      {text.split("").map((char, index) => (
        <span key={index} className={cx("flap flip", char === " " && "bg-transparent")} style={{ animationDelay: `${index * 25}ms`, background: char === " " ? "transparent" : undefined }} aria-hidden>
          {char === " " ? " " : char}
        </span>
      ))}
    </span>
  );
}

function BoardStrip({ dark, toggleTheme, onSearch, onMenu, menuOpen }: { dark: boolean; toggleTheme: () => void; onSearch: () => void; onMenu: () => void; menuOpen: boolean }) {
  const router = useRouter();
  const { user, logout } = useAuth();
  const status = useQuery({ queryKey: ["agent-status"], queryFn: () => api<AgentStatus>("/agent/status"), refetchInterval: 30000 });
  const clock = useQuery({ queryKey: ["demo-now"], queryFn: () => api<{ now: string }>("/demo/now"), refetchInterval: 15000 });
  const data = status.data;
  const used = data && data.daily_limit ? Math.min(100, Math.round((data.calls_today / data.daily_limit) * 100)) : 0;
  const when = clock.data ? new Date(clock.data.now) : null;
  const text = when ? `${when.toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "short" }).replace(",", "").toUpperCase()} ${when.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}` : "";
  return (
    <div className="bg-board text-white">
      <div className="mx-auto flex max-w-[1500px] flex-wrap items-center gap-x-5 gap-y-2 px-4 py-2">
        <Roundel />
        <div className="ml-auto flex flex-wrap items-center gap-x-5 gap-y-2">
          <span className="hidden items-center gap-2 font-display text-[13px] uppercase tracking-widest text-white/60 sm:flex" title="Every time-based rule uses this clock">
            Demo time <Flaps text={text || "…"} />
          </span>
          <span className="flex items-center gap-2 font-display text-[13px] uppercase tracking-widest text-white/80" title={data?.model ? `Model ${data.model}` : "No Gemini key: deterministic offline mode"}>
            <span className={cx("h-2.5 w-2.5 rounded-full", data?.mode === "live" ? "bg-accent" : data?.mode === "degraded" ? "bg-boardink" : "bg-white/40")} aria-hidden />
            AI {data?.mode ?? "…"}
            {data && data.mode !== "offline" && (
              <span className="inline-block h-1 w-12 bg-white/20" aria-label={`${used}% of daily AI quota used`}>
                <span className="block h-full bg-boardink" style={{ width: `${used}%` }} />
              </span>
            )}
          </span>
          <span className="hidden font-display text-[13px] uppercase tracking-widest text-white/60 md:inline">
            {user?.name} · <span className="text-boardink">{user?.role}</span>
          </span>
          <button onClick={onSearch} className="hidden items-center gap-1.5 border border-white/30 px-2 py-1 font-display text-[13px] uppercase tracking-wider hover:bg-white hover:text-board sm:flex">
            <Search className="h-3.5 w-3.5" aria-hidden /> Jump <kbd className="text-white/50">Ctrl K</kbd>
          </button>
          <button onClick={toggleTheme} aria-label="Toggle theme" className="border border-white/30 p-1.5 hover:bg-white hover:text-board">
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          <button
            onClick={() => {
              logout();
              router.push("/login");
            }}
            aria-label="Sign out"
            className="border border-white/30 p-1.5 hover:bg-white hover:text-board"
          >
            <LogOut className="h-4 w-4" />
          </button>
          <button onClick={onMenu} aria-label="Menu" aria-expanded={menuOpen} className="border border-white/30 p-1.5 hover:bg-white hover:text-board lg:hidden">
            {menuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </div>
    </div>
  );
}

function Station({ group, index, pathname, badge }: { group: NavGroup; index: number; pathname: string; badge?: number }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hoverOpen = () => {
    if (timer.current) clearTimeout(timer.current);
    setOpen(true);
  };
  const hoverClose = () => {
    timer.current = setTimeout(() => setOpen(false), 160);
  };
  const active = group.items.some((item) => isActive(pathname, item.href));
  const color = LINE_COLORS[index % LINE_COLORS.length];
  useEffect(() => {
    setOpen(false);
  }, [pathname]);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent && event.key === "Escape") setOpen(false);
      if (event instanceof MouseEvent && box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", close);
    window.addEventListener("keydown", close);
    return () => {
      window.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", close);
    };
  }, [open]);
  return (
    <div ref={box} className="relative" onMouseEnter={hoverOpen} onMouseLeave={hoverClose}>
      <button onClick={() => setOpen(!open)} aria-expanded={open} className="group flex items-center gap-2 py-2.5 pr-1">
        <span className={cx("grid h-5 w-5 place-items-center rounded-full border-[3px] border-edge bg-surface transition-transform group-hover:scale-110")} style={active ? { background: color } : undefined} aria-hidden>
          {active && <span className="h-1.5 w-1.5 rounded-full bg-edge" />}
        </span>
        <span className={cx("font-display text-[17px] font-semibold uppercase tracking-widest", active ? "text-ink" : "text-muted group-hover:text-ink")}>{group.label}</span>
        {badge ? <span className="grid min-w-5 place-items-center rounded-full bg-bad px-1 font-display text-xs font-bold leading-5 text-white" aria-label={`${badge} waiting`}>{badge}</span> : null}
      </button>
      {open && (
        <div className="slide absolute left-0 top-full z-40 w-72 border border-edge border-t-4 bg-surface" style={{ borderTopColor: color }}>
          <ul>
            {group.items.map((item) => (
              <li key={item.href}>
                <Link href={item.href} className={cx("flex items-start gap-3 border-b border-line px-4 py-2.5 last:border-b-0 hover:bg-surface2", isActive(pathname, item.href) && "bg-surface2")}>
                  <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full border-2 border-edge" style={isActive(pathname, item.href) ? { background: color } : undefined} aria-hidden />
                  <span>
                    <span className="block font-display text-lg font-semibold uppercase leading-tight tracking-wide">{item.label}</span>
                    <span className="block text-xs text-muted">{item.note}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function LineMap({ groups, pathname, pending }: { groups: NavGroup[]; pathname: string; pending: number }) {
  return (
    <nav className="mx-auto hidden max-w-[1500px] items-center px-4 lg:flex" aria-label="Main">
      {groups.map((group, index) => (
        <Fragment key={group.label}>
          <Station group={group} index={index} pathname={pathname} badge={group.label === "Decide" ? pending : 0} />
          {index < groups.length - 1 && <span className="mx-2 h-[5px] min-w-10 flex-1 rounded-full" style={{ background: LINE_COLORS[index % LINE_COLORS.length] }} aria-hidden />}
        </Fragment>
      ))}
    </nav>
  );
}

function Palette({ groups, open, setOpen }: { groups: NavGroup[]; open: boolean; setOpen: (value: boolean) => void }) {
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
    <Command.Dialog open={open} onOpenChange={setOpen} label="Go to page" className="fixed left-1/2 top-24 z-50 w-[min(34rem,92vw)] -translate-x-1/2 overflow-hidden border-2 border-edge bg-surface">
      <Command.Input placeholder="Where to?" className="w-full border-b-2 border-edge bg-board px-4 py-3 font-display text-xl uppercase tracking-wider text-boardink outline-none placeholder:text-white/40" />
      <Command.List className="max-h-80 overflow-y-auto p-2">
        <Command.Empty className="p-3 text-sm text-muted">No stop matches</Command.Empty>
        {groups.map((group) => (
          <Command.Group key={group.label} heading={group.label} className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:font-display [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-muted">
            {group.items.map((item) => (
              <Command.Item
                key={item.href}
                value={`${group.label} ${item.label}`}
                onSelect={() => {
                  router.push(item.href);
                  setOpen(false);
                }}
                className="flex cursor-pointer items-baseline justify-between gap-3 px-3 py-2 data-[selected=true]:bg-primary data-[selected=true]:text-primaryink"
              >
                <span className="font-display text-lg font-semibold uppercase tracking-wide">{item.label}</span>
                <span className="text-xs opacity-70">{item.note}</span>
              </Command.Item>
            ))}
          </Command.Group>
        ))}
      </Command.List>
    </Command.Dialog>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const pathname = usePathname();
  const [dark, toggleTheme] = useTheme();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [mobile, setMobile] = useState(false);
  const groups = visibleGroups(user?.role);
  const approver = user?.role === "admin" || user?.role === "approver";
  const waiting = useQuery({ queryKey: ["approvals"], queryFn: () => api<unknown[]>("/approvals"), enabled: approver, refetchInterval: 60000 });
  const pending = waiting.data?.length ?? 0;
  useEffect(() => {
    setMobile(false);
  }, [pathname]);
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30">
        <BoardStrip dark={dark} toggleTheme={toggleTheme} onSearch={() => setPaletteOpen(true)} onMenu={() => setMobile(!mobile)} menuOpen={mobile} />
        <div className="border-b-2 border-edge bg-surface">
          <LineMap groups={groups} pathname={pathname} pending={pending} />
          {mobile && (
            <nav className="max-h-[65vh] overflow-y-auto px-4 py-3 lg:hidden" aria-label="Mobile">
              {groups.map((group, index) => (
                <div key={group.label} className="mb-3">
                  <p className="mb-1 flex items-center gap-2 font-display text-sm font-semibold uppercase tracking-widest text-muted">
                    <span className="h-3 w-3 rounded-full border-[3px] border-edge" style={{ background: LINE_COLORS[index % LINE_COLORS.length] }} aria-hidden />
                    {group.label}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {group.items.map((item) => (
                      <Link key={item.href} href={item.href} className={cx("chip", isActive(pathname, item.href) && "bg-primary text-primaryink")}>
                        {item.label}
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </nav>
          )}
        </div>
      </header>
      <main className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-8">{children}</main>
      <footer className="border-t-2 border-edge bg-board px-4 py-2 text-center font-display text-[13px] uppercase tracking-[0.18em] text-white/60">
        Synthetic data · demo campus · the assistant only proposes, people decide
      </footer>
      <Palette groups={groups} open={paletteOpen} setOpen={setPaletteOpen} />
      <Toasts />
    </div>
  );
}
