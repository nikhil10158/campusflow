"use client";

import { useQuery } from "@tanstack/react-query";
import { Command } from "cmdk";
import {
  Activity, BarChart3, Bell, Building2, CalendarClock, Car, ChevronDown, ClipboardCheck, Clock, DoorOpen, FlaskConical, Gauge, Hotel, LayoutDashboard, LogOut,
  MapPin, Menu, Moon, ScrollText, Search, ShieldCheck, Sparkles, Sun, Timer, Upload, Users, Wrench, X, type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { api } from "@/lib/api";
import { useAuth, type User } from "@/lib/store";
import type { AgentStatus } from "@/lib/types";

import { NotificationBell } from "./NotificationBell";
import { ThemeToggle, useTheme } from "./ThemeToggle";
import { Toasts, cx } from "./ui";

type Role = User["role"];

interface NavItem {
  href: string;
  label: string;
  note: string;
  icon: LucideIcon;
  roles: Role[];
}

interface NavGroup {
  label: string;
  icon: LucideIcon;
  items: NavItem[];
}

const ALL: Role[] = ["admin", "approver", "faculty", "student"];
const STAFF: Role[] = ["admin", "approver", "faculty"];

const GROUPS: NavGroup[] = [
  {
    label: "Home",
    icon: LayoutDashboard,
    items: [
      { href: "/admin", label: "Dashboard", note: "Clock, alerts and numbers", icon: LayoutDashboard, roles: ["admin"] },
      { href: "/faculty", label: "My day", note: "Classes and your requests", icon: Users, roles: ["faculty"] },
      { href: "/student", label: "My requests", note: "Your club bookings", icon: Users, roles: ["student"] },
    ],
  },
  {
    label: "Assistant",
    icon: Sparkles,
    items: [{ href: "/", label: "Plan with the assistant", note: "Describe what you need in one sentence", icon: Sparkles, roles: ALL }],
  },
  {
    label: "Rooms",
    icon: DoorOpen,
    items: [
      { href: "/find", label: "Find a free room", note: "Search by time, size and type", icon: Search, roles: ALL },
      { href: "/timeline", label: "Room timeline", note: "See a day and test a time", icon: Activity, roles: ALL },
      { href: "/timetable", label: "Class timetables", note: "Every section, plus free-room heatmap", icon: CalendarClock, roles: ALL },
      { href: "/cohort", label: "Common free time", note: "For quizzes and extra lectures", icon: Timer, roles: STAFF },
      { href: "/labs", label: "Laboratories", note: "Rules, safety and requests", icon: FlaskConical, roles: STAFF },
      { href: "/amphitheatres", label: "Amphitheatres", note: "Large events", icon: Building2, roles: STAFF },
    ],
  },
  {
    label: "Guests & parking",
    icon: Hotel,
    items: [
      { href: "/guesthouse", label: "Guest house", note: "Rooms, groups and waitlist", icon: Hotel, roles: STAFF },
      { href: "/parking", label: "Parking", note: "Lots, passes and no-shows", icon: Car, roles: STAFF },
      { href: "/security", label: "Gate scan", note: "Check a parking pass", icon: ShieldCheck, roles: ["admin", "security"] },
    ],
  },
  {
    label: "Approvals",
    icon: ClipboardCheck,
    items: [{ href: "/approvals", label: "Approvals", note: "Requests waiting for you", icon: ClipboardCheck, roles: ["admin", "approver"] }],
  },
  {
    label: "Rules",
    icon: ScrollText,
    items: [{ href: "/policies", label: "Booking rules", note: "Ask a question, get a cited answer", icon: ScrollText, roles: ["admin", "approver", "faculty", "student", "security"] }],
  },
  {
    label: "Admin",
    icon: Wrench,
    items: [
      { href: "/admin/timetables", label: "Import timetable", note: "Upload, review, approve, roll back", icon: Upload, roles: ["admin"] },
      { href: "/admin/disruptions", label: "Closures", note: "Re-home classes and bookings", icon: Wrench, roles: ["admin"] },
      { href: "/admin/reports", label: "Usage reports", note: "Utilisation and unused classes", icon: BarChart3, roles: ["admin"] },
      { href: "/admin/benchmark", label: "Performance", note: "Optimiser and booking race test", icon: Gauge, roles: ["admin"] },
      { href: "/admin/audit", label: "Audit log", note: "Who did what, plus messages sent", icon: Bell, roles: ["admin"] },
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

function Logo() {
  return (
    <Link href="/" className="group flex shrink-0 items-center gap-2.5" aria-label="CampusFlow home">
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-brand text-primaryink shadow-lg transition duration-300 group-hover:rotate-[-8deg] group-hover:scale-110">
        <MapPin className="h-5 w-5" aria-hidden />
      </span>
      <span className="font-display text-xl font-semibold tracking-tight max-[400px]:hidden">CampusFlow</span>
    </Link>
  );
}

function NavLink({ group, pathname, badge, align }: { group: NavGroup; pathname: string; badge: number; align: "left" | "right" }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const active = group.items.some((item) => isActive(pathname, item.href));
  const single = group.items.length === 1;
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
  const classes = cx("flex items-center gap-1.5 whitespace-nowrap rounded-lg px-2.5 py-2 text-[15px] font-medium transition duration-150", active ? "bg-tint text-link" : "text-ink hover:bg-surface2");
  const badgeNode = badge ? (
    <span className="grid min-w-5 place-items-center rounded-full bg-accent px-1.5 text-xs font-bold leading-5 text-[#04121f]" aria-label={`${badge} waiting`}>
      {badge}
    </span>
  ) : null;
  if (single) {
    const item = group.items[0];
    return (
      <Link href={item.href} className={classes}>
        <item.icon className="h-4 w-4" aria-hidden /> {group.label}
        {badgeNode}
      </Link>
    );
  }
  return (
    <div
      ref={box}
      className="relative"
      onMouseEnter={() => {
        if (timer.current) clearTimeout(timer.current);
        setOpen(true);
      }}
      onMouseLeave={() => {
        timer.current = setTimeout(() => setOpen(false), 150);
      }}
    >
      <button onClick={() => setOpen(!open)} aria-expanded={open} className={classes}>
        <group.icon className="h-4 w-4" aria-hidden /> {group.label}
        <ChevronDown className={cx("h-3.5 w-3.5 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div className={cx("pop absolute top-full z-40 w-80 max-w-[calc(100vw-2rem)] pt-1", align === "right" ? "right-0" : "left-0")}>
          <ul className="overflow-hidden rounded-xl border border-line bg-surface p-1.5 shadow-lift">
            {group.items.map((item) => (
              <li key={item.href}>
                <Link href={item.href} className={cx("group/item flex items-start gap-3 rounded-lg px-3 py-2.5 transition duration-150 hover:translate-x-0.5 hover:bg-surface2", isActive(pathname, item.href) && "bg-tint")}>
                  <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-surface2 text-link transition duration-150 group-hover/item:scale-110">
                    <item.icon className="h-4 w-4" aria-hidden />
                  </span>
                  <span>
                    <span className="block text-[15px] font-medium">{item.label}</span>
                    <span className="block text-sm text-muted">{item.note}</span>
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

function useStatus() {
  const status = useQuery({ queryKey: ["agent-status"], queryFn: () => api<AgentStatus>("/agent/status"), refetchInterval: 30000 });
  const clock = useQuery({ queryKey: ["demo-now"], queryFn: () => api<{ now: string }>("/demo/now"), refetchInterval: 15000 });
  const when = clock.data ? new Date(clock.data.now) : null;
  const label = when ? `${when.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" })}, ${when.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}` : "...";
  const data = status.data;
  const ai = data?.mode === "live" ? "AI on" : data?.mode === "degraded" ? "AI limited" : "Offline mode";
  const dot = data?.mode === "live" ? "bg-good" : data?.mode === "degraded" ? "bg-warn" : "bg-muted";
  const hint = data?.model ? `Gemini model ${data.model}` : "No Gemini key set: the built-in rule-based assistant is answering";
  return { label, ai, dot, hint };
}

function StatusChips() {
  const { label, ai, dot, hint } = useStatus();
  return (
    <div className="hidden items-center gap-2 whitespace-nowrap min-[1760px]:flex">
      <span className="flex items-center gap-1.5 rounded-full bg-surface2 px-3 py-1 text-sm" title="All booking rules use this demo clock instead of the real time">
        <Clock className="h-3.5 w-3.5 text-muted" aria-hidden /> {label}
      </span>
      <span className="flex items-center gap-1.5 rounded-full bg-surface2 px-3 py-1 text-sm" title={hint}>
        <span className={cx("h-2 w-2 rounded-full", dot)} aria-hidden /> {ai}
      </span>
    </div>
  );
}

function StatusRows() {
  const { label, ai, dot, hint } = useStatus();
  return (
    <div className="space-y-1.5 border-b border-line px-3 py-2.5 text-sm">
      <p className="flex items-center justify-between gap-3" title="All booking rules use this demo clock instead of the real time">
        <span className="flex items-center gap-1.5 text-muted"><Clock className="h-3.5 w-3.5" aria-hidden /> Demo time</span>
        <span className="font-medium">{label}</span>
      </p>
      <p className="flex items-center justify-between gap-3" title={hint}>
        <span className="text-muted">Assistant</span>
        <span className="flex items-center gap-1.5 font-medium"><span className={cx("h-2 w-2 rounded-full", dot)} aria-hidden /> {ai}</span>
      </p>
    </div>
  );
}

function UserMenu({ dark, toggleTheme }: { dark: boolean; toggleTheme: () => void }) {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    window.addEventListener("mousedown", close);
    return () => window.removeEventListener("mousedown", close);
  }, [open]);
  const initials = (user?.name ?? "?").split(" ").map((part) => part[0]).slice(0, 2).join("").toUpperCase();
  return (
    <div ref={box} className="relative">
      <button onClick={() => setOpen(!open)} aria-expanded={open} aria-label="Account menu" className="flex items-center gap-2 rounded-full border border-line bg-surface p-0.5 transition hover:border-primary hover:bg-surface2 min-[1760px]:pr-3">
        <span className="grid h-8 w-8 place-items-center rounded-full bg-brand text-sm font-semibold text-primaryink">{initials}</span>
        <span className="hidden text-sm font-medium min-[1760px]:block">{user?.name}</span>
      </button>
      {open && (
        <div className="pop absolute right-0 top-full z-40 mt-2 w-72 max-w-[calc(100vw-2rem)] overflow-hidden rounded-xl border border-line bg-surface p-1.5 shadow-lift">
          <div className="border-b border-line px-3 pb-2 pt-1.5">
            <p className="font-medium">{user?.name}</p>
            <p className="text-sm capitalize text-muted">{user?.role}</p>
          </div>
          <StatusRows />
          <button onClick={toggleTheme} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[15px] hover:bg-surface2">
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />} {dark ? "Light mode" : "Dark mode"}
          </button>
          <button
            onClick={() => {
              logout();
              router.push("/login");
            }}
            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-[15px] hover:bg-surface2"
          >
            <LogOut className="h-4 w-4" /> Sign out
          </button>
        </div>
      )}
    </div>
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
    <Command.Dialog open={open} onOpenChange={setOpen} label="Go to page" className="fixed left-1/2 top-24 z-50 w-[min(34rem,92vw)] -translate-x-1/2 overflow-hidden rounded-2xl border border-line bg-surface shadow-lift">
      <Command.Input placeholder="Search pages…" className="w-full border-b border-line bg-transparent px-5 py-4 text-base outline-none" />
      <Command.List className="max-h-80 overflow-y-auto p-2">
        <Command.Empty className="p-3 text-sm text-muted">No page matches</Command.Empty>
        {groups.flatMap((group) => group.items).map((item) => (
          <Command.Item
            key={item.href}
            value={`${item.label} ${item.note}`}
            onSelect={() => {
              router.push(item.href);
              setOpen(false);
            }}
            className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 data-[selected=true]:bg-tint"
          >
            <item.icon className="h-4 w-4 text-link" aria-hidden />
            <span className="font-medium">{item.label}</span>
            <span className="ml-auto text-sm text-muted">{item.note}</span>
          </Command.Item>
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
      <header className="topbar sticky top-0 z-30 border-b border-line">
        <div className="mx-auto flex h-16 max-w-[1500px] items-center gap-3 px-4 lg:px-6">
          <Logo />
          <nav className="ml-3 hidden min-w-0 items-center gap-0.5 min-[1400px]:flex" aria-label="Main">
            {groups.map((group, index) => (
              <NavLink key={group.label} group={group} pathname={pathname} badge={group.label === "Approvals" ? pending : 0} align={index >= groups.length - 2 ? "right" : "left"} />
            ))}
          </nav>
          <div className="ml-auto flex shrink-0 items-center gap-2">
            <StatusChips />
            <button onClick={() => setPaletteOpen(true)} aria-label="Search pages" className="flex h-9 items-center gap-2 rounded-full border border-line bg-surface px-2.5 text-sm text-muted transition hover:border-primary hover:bg-surface2 hover:text-ink 2xl:px-3">
              <Search className="h-4 w-4" aria-hidden /> <span className="hidden 2xl:inline">Search</span> <kbd className="hidden rounded bg-surface2 px-1.5 text-xs 2xl:inline">Ctrl K</kbd>
            </button>
            <ThemeToggle />
            <NotificationBell />
            <UserMenu dark={dark} toggleTheme={toggleTheme} />
            <button onClick={() => setMobile(!mobile)} aria-label="Menu" aria-expanded={mobile} className="grid h-9 w-9 place-items-center rounded-full border border-line bg-surface transition hover:border-primary min-[1400px]:hidden">
              {mobile ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>
        {mobile && (
          <nav className="slide max-h-[calc(100vh-4rem)] overflow-y-auto border-t border-line px-4 py-4 min-[1400px]:hidden" aria-label="Mobile">
            <div className="mx-auto grid max-w-[1500px] gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
              {groups.map((group) => (
                <div key={group.label}>
                  <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
                    <group.icon className="h-3.5 w-3.5" aria-hidden /> {group.label}
                    {group.label === "Approvals" && pending > 0 && <span className="rounded-full bg-accent px-1.5 text-[11px] font-bold leading-4 text-[#04121f]">{pending}</span>}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {group.items.map((item) => (
                      <Link key={item.href} href={item.href} className={cx("chip", isActive(pathname, item.href) && "!border-primary !bg-tint !text-link")}>
                        <item.icon className="h-3.5 w-3.5" aria-hidden /> {item.label}
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </nav>
        )}
      </header>
      <main className="mx-auto w-full min-w-0 max-w-[1500px] flex-1 px-4 py-8 lg:px-6">{children}</main>
      <footer className="border-t border-line px-4 py-4 text-center text-sm text-muted">Demo with synthetic data. The assistant only suggests; people approve every booking.</footer>
      <Palette groups={groups} open={paletteOpen} setOpen={setPaletteOpen} />
      <Toasts />
    </div>
  );
}
