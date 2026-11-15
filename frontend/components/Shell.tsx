"use client";

import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import { ChevronDown, LogOut, Menu, Moon, Search, Sun, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
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

function Logo() {
  return (
    <Link href="/" className="flex items-center gap-2" aria-label="CampusFlow home">
      <span className="grid h-7 w-7 grid-cols-3 gap-px border-2 border-edge bg-edge p-px" aria-hidden>
        {[1, 0, 1, 0, 1, 0, 0, 0, 1].map((filled, index) => (
          <span key={index} className={filled ? (index === 4 ? "bg-primary" : "bg-marker") : "bg-surface"} />
        ))}
      </span>
      <span className="font-display text-xl leading-none tracking-tight">
        <span className="italic">campus</span>
        <span className="font-semibold">flow</span>
      </span>
    </Link>
  );
}

function GroupMenu({ group, pathname }: { group: NavGroup; pathname: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const active = group.items.some((item) => isActive(pathname, item.href));
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
  if (group.items.length === 1) {
    const item = group.items[0];
    return (
      <Link href={item.href} className={cx("px-3 py-2 font-mono text-xs uppercase tracking-wider hover:bg-surface2", active && "bg-ink text-bg hover:bg-ink")}>
        {item.label}
      </Link>
    );
  }
  return (
    <div ref={box} className="relative">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className={cx("flex items-center gap-1 px-3 py-2 font-mono text-xs uppercase tracking-wider hover:bg-surface2", active && "bg-ink text-bg hover:bg-ink")}
      >
        {group.label}
        <ChevronDown className={cx("h-3 w-3 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div className="hard rise absolute left-0 top-full z-40 mt-1 w-72 bg-surface">
          <ul>
            {group.items.map((item) => (
              <li key={item.href}>
                <Link href={item.href} className={cx("block border-b border-line px-4 py-2.5 last:border-b-0 hover:bg-marker/40", isActive(pathname, item.href) && "bg-marker/60")}>
                  <span className="block text-sm font-semibold">{item.label}</span>
                  <span className="block text-xs text-muted">{item.note}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function StatusTicker() {
  const status = useQuery({ queryKey: ["agent-status"], queryFn: () => api<AgentStatus>("/agent/status"), refetchInterval: 30000 });
  const clock = useQuery({ queryKey: ["demo-now"], queryFn: () => api<{ now: string }>("/demo/now"), refetchInterval: 15000 });
  const { user } = useAuth();
  const data = status.data;
  const used = data && data.daily_limit ? Math.min(100, Math.round((data.calls_today / data.daily_limit) * 100)) : 0;
  return (
    <footer className="sticky bottom-0 z-30 border-t-2 border-edge bg-surface">
      <div className="hazard h-1.5" aria-hidden />
      <div className="mx-auto flex max-w-[1500px] flex-wrap items-center gap-x-6 gap-y-1 px-4 py-1.5 font-mono text-[11px] uppercase tracking-wider">
        <span className="flex items-center gap-2" title={data?.model ? `Model ${data.model}` : "No Gemini key: deterministic offline mode"}>
          <span className={cx("h-2 w-2 rounded-full", data?.mode === "live" ? "bg-good" : data?.mode === "degraded" ? "bg-warn" : "bg-muted")} aria-hidden />
          AI {data?.mode ?? "…"}
          {data && data.mode !== "offline" && (
            <span className="inline-block h-1.5 w-14 bg-surface2" aria-label={`${used}% of daily AI quota used`}>
              <span className={cx("block h-full", used > 80 ? "bg-bad" : "bg-primary")} style={{ width: `${used}%` }} />
            </span>
          )}
        </span>
        <span title="Every time-based rule uses this clock instead of the real time">
          Demo clock <strong className="text-primary">{clock.data ? fmtDateTime(clock.data.now) : "…"}</strong>
        </span>
        <span className="text-muted">{user?.name} · {user?.role}</span>
        <span className="ml-auto text-muted">Synthetic data · the assistant only proposes</span>
      </div>
    </footer>
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
    <Command.Dialog open={open} onOpenChange={setOpen} label="Go to page" className="hard fixed left-1/2 top-24 z-50 w-[min(34rem,92vw)] -translate-x-1/2 overflow-hidden bg-surface">
      <Command.Input placeholder="Jump to a page…" className="w-full border-b-2 border-edge bg-transparent px-4 py-3 font-mono text-sm outline-none" />
      <Command.List className="max-h-80 overflow-y-auto p-2">
        <Command.Empty className="p-3 text-sm text-muted">No page matches</Command.Empty>
        {groups.map((group) => (
          <Command.Group key={group.label} heading={group.label} className="[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest [&_[cmdk-group-heading]]:text-muted">
            {group.items.map((item) => (
              <Command.Item
                key={item.href}
                value={`${group.label} ${item.label}`}
                onSelect={() => {
                  router.push(item.href);
                  setOpen(false);
                }}
                className="flex cursor-pointer items-baseline justify-between gap-3 px-3 py-2 text-sm data-[selected=true]:bg-marker/60"
              >
                <span className="font-semibold">{item.label}</span>
                <span className="text-xs text-muted">{item.note}</span>
              </Command.Item>
            ))}
          </Command.Group>
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
  const [mobile, setMobile] = useState(false);
  const groups = visibleGroups(user?.role);
  useEffect(() => {
    setMobile(false);
  }, [pathname]);
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b-2 border-edge bg-bg/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1500px] items-center gap-4 px-4 py-2">
          <Logo />
          <nav className="ml-4 hidden items-center gap-1 lg:flex" aria-label="Main">
            {groups.map((group) => (
              <GroupMenu key={group.label} group={group} pathname={pathname} />
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <button onClick={() => setPaletteOpen(true)} className="chip hidden sm:inline-flex">
              <Search className="h-3 w-3" aria-hidden /> Jump <kbd className="opacity-60">Ctrl K</kbd>
            </button>
            <button onClick={toggleTheme} aria-label="Toggle theme" className="hard-sm bg-surface p-1.5 hover:bg-marker/50">
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <button
              onClick={() => {
                logout();
                router.push("/login");
              }}
              aria-label="Sign out"
              className="hard-sm bg-surface p-1.5 hover:bg-marker/50"
            >
              <LogOut className="h-4 w-4" />
            </button>
            <button onClick={() => setMobile(!mobile)} aria-label="Menu" aria-expanded={mobile} className="hard-sm bg-surface p-1.5 lg:hidden">
              {mobile ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
          </div>
        </div>
        {mobile && (
          <nav className="max-h-[70vh] overflow-y-auto border-t-2 border-edge bg-surface px-4 py-3 lg:hidden" aria-label="Mobile">
            {groups.map((group) => (
              <div key={group.label} className="mb-3">
                <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-muted">{group.label}</p>
                <div className="flex flex-wrap gap-2">
                  {group.items.map((item) => (
                    <Link key={item.href} href={item.href} className={cx("chip", isActive(pathname, item.href) && "bg-marker")}>
                      {item.label}
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </nav>
        )}
      </header>
      <main className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-8">{children}</main>
      <StatusTicker />
      <Palette groups={groups} open={paletteOpen} setOpen={setPaletteOpen} />
      <Toasts />
    </div>
  );
}
