"use client";

import { AlertTriangle, ArrowRight, CheckCircle2, ChevronDown, HelpCircle, Info, Loader2, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type ButtonHTMLAttributes, type ComponentType, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";

import { useToasts } from "@/lib/store";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

type Tone = "neutral" | "good" | "warn" | "bad" | "info" | "ghost" | "primary";

const TONES: Record<Tone, string> = {
  neutral: "bg-surface2 text-muted",
  good: "bg-goodbg text-good",
  warn: "bg-warnbg text-warn",
  bad: "bg-badbg text-bad",
  info: "bg-infobg text-info",
  ghost: "bg-ghostbg text-ghost",
  primary: "bg-primary text-primaryink",
};

const DOT: Record<Tone, string> = {
  neutral: "bg-muted",
  good: "bg-good",
  warn: "bg-warn",
  bad: "bg-bad",
  info: "bg-info",
  ghost: "bg-ghost",
  primary: "bg-primaryink",
};

export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={cx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-[13px] font-medium", TONES[tone])}>
      <span className={cx("h-1.5 w-1.5 rounded-full", DOT[tone], tone === "warn" && "dot-beat")} aria-hidden />
      {children}
    </span>
  );
}

export function stateTone(state: string): Tone {
  if (["FREE", "CONFIRMED", "VALID", "APPROVED", "ACTIVE", "live", "OPTIMAL", "IMPORTED"].includes(state)) return "good";
  if (["FREE_RELEASED", "PARTIAL", "WAITLISTED", "info"].includes(state)) return "info";
  if (["HELD", "PENDING", "ESCALATED", "SUBMITTED", "degraded", "PROPOSED", "NEEDS_ATTENTION", "FEASIBLE"].includes(state)) return "warn";
  if (["REJECTED", "EXPIRED", "CANCELLED", "NO_SHOW", "WRONG_LOT", "NOT_FOUND", "offline", "BUSY", "INFEASIBLE"].includes(state)) return "bad";
  if (state === "GHOST_CANDIDATE") return "ghost";
  return "neutral";
}

const STATE_LABEL: Record<string, string> = {
  FREE: "Free",
  FREE_RELEASED: "Free (class cancelled)",
  BUSY: "Busy",
  HELD: "On hold",
  PENDING: "Waiting",
  ESCALATED: "Escalated",
  SUBMITTED: "Submitted",
  CONFIRMED: "Confirmed",
  PARTIAL: "Partly done",
  WAITLISTED: "Waitlisted",
  EXPIRED: "Expired",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
  NO_SHOW: "No-show",
  PROPOSED: "Proposed",
  APPROVED: "Approved",
  ACTIVE: "In use",
  ARCHIVED: "Older version",
  VALID: "Valid",
  WRONG_LOT: "Wrong lot",
  NOT_FOUND: "Not found",
  GHOST_CANDIDATE: "Rarely used",
  NEEDS_ATTENTION: "Needs attention",
  READY: "Ready",
  IMPORTED: "Imported",
  OPTIMAL: "Best possible",
  FEASIBLE: "Good",
  INFEASIBLE: "No solution",
};

const STATE_HELP: Record<string, string> = {
  FREE: "Nothing is scheduled in this room at that time.",
  FREE_RELEASED: "A timetabled class was cancelled or released, so the room is open and bookable.",
  BUSY: "Something is already scheduled here.",
  HELD: "Reserved while approvals are pending. It expires if nobody approves in time.",
  PENDING: "Waiting for an approver to decide.",
  ESCALATED: "Waited too long, so it was passed to the administrator.",
  SUBMITTED: "Sent in. All parts are on hold together.",
  CONFIRMED: "Approved and booked.",
  PARTIAL: "Some parts of this bundle failed. You choose to accept what is approved, replace a part, or cancel everything.",
  WAITLISTED: "No room was free, so the request is queued by priority.",
  EXPIRED: "The hold ran out before everyone approved.",
  REJECTED: "An approver said no, with a written reason.",
  CANCELLED: "Cancelled; everything it held was released.",
  NO_SHOW: "Nobody arrived, so the slots were released.",
  PROPOSED: "Waiting for a person to approve it.",
  APPROVED: "A person approved this step.",
  ACTIVE: "This is the timetable version currently in use.",
  ARCHIVED: "An older version you can roll back to.",
  VALID: "The pass is good for this time and place.",
  WRONG_LOT: "The pass is for a different parking lot.",
  GHOST_CANDIDATE: "Timetabled, but attendance suggests nobody comes.",
  NEEDS_ATTENTION: "Questions or errors must be fixed before this can be imported.",
  READY: "Everything checks out and it can be imported.",
  IMPORTED: "Already imported.",
};

export function StatusBadge({ state }: { state: string }) {
  return (
    <Badge tone={stateTone(state)} title={STATE_HELP[state]}>
      {STATE_LABEL[state] ?? state.replace(/_/g, " ").toLowerCase()}
    </Badge>
  );
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("card-in min-w-0 rounded-2xl border border-line bg-surface shadow-card", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 px-5 pt-4">
          {title && <h2 className="text-[17px] font-semibold tracking-tight">{title}</h2>}
          {actions}
        </header>
      )}
      <div className="min-w-0 overflow-x-auto p-5">{children}</div>
    </section>
  );
}

function HelpPanel({ id, steps }: { id: string; steps: string[] }) {
  const key = `campusflow-help-${id}`;
  const [open, setOpen] = useState(false);
  useEffect(() => {
    try {
      setOpen(window.localStorage.getItem(key) !== "seen");
    } catch {
      setOpen(true);
    }
  }, [key]);
  function toggle() {
    const next = !open;
    setOpen(next);
    try {
      window.localStorage.setItem(key, next ? "open" : "seen");
    } catch {
      return;
    }
  }
  return (
    <div className="mb-6">
      <button onClick={toggle} aria-expanded={open} className="flex items-center gap-1.5 rounded-lg py-1 text-[15px] font-medium text-link hover:underline">
        <HelpCircle className="h-4 w-4" aria-hidden /> {open ? "Hide quick guide" : "Show quick guide"}
      </button>
      {open && (
        <ol className="stagger mt-2 grid gap-3 sm:grid-cols-3">
          {steps.map((step, index) => (
            <li key={step} className="flex gap-3 rounded-xl border border-line bg-surface p-4 text-[15px] leading-snug shadow-card">
              <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-brand text-sm font-semibold text-primaryink">{index + 1}</span>
              {step}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, help }: { title: string; subtitle?: string; actions?: ReactNode; kicker?: string; help?: string[] }) {
  return (
    <>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-3xl">
          <span className="accent-bar mb-3 block h-1.5 w-12 rounded-full bg-bar" aria-hidden />
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
          {subtitle && <p className="mt-2 max-w-2xl text-[17px] leading-relaxed text-muted">{subtitle}</p>}
        </div>
        {actions}
      </div>
      {help && <HelpPanel id={title} steps={help} />}
    </>
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost" | "danger" | "outline";
  busy?: boolean;
}

export function Button({ variant = "primary", busy, className, children, disabled, ...rest }: ButtonProps) {
  const styles = {
    primary: "bg-brand text-primaryink shadow-card hover:-translate-y-px hover:brightness-110 hover:shadow-lift",
    outline: "border border-edge bg-surface text-ink hover:-translate-y-px hover:border-primary hover:bg-surface2",
    danger: "bg-bad text-white shadow-card hover:-translate-y-px hover:brightness-110",
    ghost: "text-ink hover:bg-surface2",
  }[variant];
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      className={cx("inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-[15px] font-medium transition duration-150 active:translate-y-0 active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-45 disabled:hover:translate-y-0", styles, className)}
    >
      {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function ConfirmButton({ label, question, onConfirm, variant = "danger", busy, disabled }: { label: ReactNode; question: string; onConfirm: () => void; variant?: "primary" | "danger" | "outline"; busy?: boolean; disabled?: boolean }) {
  const [asking, setAsking] = useState(false);
  if (!asking) {
    return (
      <Button variant={variant} onClick={() => setAsking(true)} busy={busy} disabled={disabled}>
        {label}
      </Button>
    );
  }
  return (
    <span className="slide inline-flex flex-wrap items-center gap-2 rounded-xl border border-edge bg-surface px-3 py-1.5" role="alertdialog" aria-label={question}>
      <span className="text-sm font-medium">{question}</span>
      <Button
        variant={variant}
        onClick={() => {
          setAsking(false);
          onConfirm();
        }}
      >
        Yes
      </Button>
      <Button variant="outline" onClick={() => setAsking(false)}>
        No
      </Button>
    </span>
  );
}

export function QuickTiles({ items }: { items: { href: string; title: string; text: string; icon?: ComponentType<{ className?: string }>; badge?: ReactNode }[] }) {
  return (
    <div className="stagger mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((item) => (
        <Link key={item.href + item.title} href={item.href} className="group flex flex-col rounded-2xl border border-line bg-surface p-5 shadow-card transition duration-200 hover:-translate-y-1 hover:border-primary hover:shadow-lift">
          {item.icon && (
            <span className="mb-3 grid h-11 w-11 place-items-center rounded-xl bg-tint text-link transition duration-200 group-hover:rotate-[-6deg] group-hover:scale-110 group-hover:bg-primary group-hover:text-primaryink">
              <item.icon className="h-5 w-5" />
            </span>
          )}
          <span className="flex items-center justify-between gap-2 text-lg font-semibold">
            {item.title}
            <ArrowRight className="h-4 w-4 shrink-0 text-muted transition-transform group-hover:translate-x-1 group-hover:text-link" aria-hidden />
          </span>
          <span className="mt-1 text-[15px] leading-snug text-muted">{item.text}</span>
          {item.badge && <span className="mt-2">{item.badge}</span>}
        </Link>
      ))}
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="flex flex-col gap-1.5 text-sm font-medium text-ink">
      {label}
      {children}
      {hint && <span className="text-[13px] font-normal text-muted">{hint}</span>}
    </label>
  );
}

const INPUT = "w-full rounded-lg border border-edge bg-surface px-3 py-2 text-[15px] font-normal text-ink outline-none transition duration-150 placeholder:text-muted/70 hover:border-primary/60 focus:border-primary focus:ring-4 focus:ring-primary/15";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(INPUT, props.className)} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <span className="relative block">
      <select {...props} className={cx(INPUT, "appearance-none pr-9", props.className)} />
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton h-6 w-full", className)} aria-hidden />;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-dashed border-edge p-6 text-center text-[15px] text-muted">{children}</div>;
}

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="flex items-start gap-2 rounded-xl bg-badbg p-3.5 text-[15px] text-bad">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>{message}</span>
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "good" | "warn" | "bad"; children: ReactNode }) {
  const Icon = tone === "good" ? CheckCircle2 : tone === "info" ? Info : AlertTriangle;
  return (
    <div className={cx("flex items-start gap-2.5 rounded-xl p-3.5 text-[15px]", TONES[tone])}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

export function Toasts() {
  const { toasts, dismiss } = useToasts();
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={cx("toast-in pointer-events-auto flex items-start justify-between gap-2 rounded-xl border border-line bg-surface p-3.5 text-[15px] shadow-lg", toast.tone === "bad" ? "border-l-4 border-l-bad" : toast.tone === "good" ? "border-l-4 border-l-good" : "border-l-4 border-l-info")}>
          <span>{toast.text}</span>
          <button onClick={() => dismiss(toast.id)} aria-label="Dismiss" className="shrink-0 text-muted hover:text-ink">
            <X className="h-4 w-4" />
          </button>
        </div>
      ))}
    </div>
  );
}

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  if (!open) return null;
  return (
    <div className="fade-in fixed inset-0 z-40 flex justify-end bg-[var(--shade)] backdrop-blur-[2px]" onClick={onClose}>
      <aside className="drawer-in h-full w-full max-w-md overflow-y-auto bg-surface p-6 shadow-2xl" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={title}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-1.5 hover:bg-surface2">
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
      </aside>
    </div>
  );
}

function CountUp({ value }: { value: number }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const started = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const progress = Math.min((now - started) / 700, 1);
      setShown(Math.round(value * (1 - Math.pow(1 - progress, 3))));
      if (progress < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return <>{shown}</>;
}

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: Tone }) {
  return (
    <div className="card-in relative overflow-hidden rounded-2xl border border-line bg-surface p-4 shadow-card transition duration-200 hover:-translate-y-0.5 hover:shadow-lift">
      <span className={cx("absolute inset-y-0 left-0 w-1", tone === "bad" ? "bg-bad" : tone === "warn" ? "bg-warn" : tone === "good" ? "bg-good" : "bg-primary")} aria-hidden />
      <div className="pl-1 text-sm text-muted">{label}</div>
      <div className={cx("mt-1 pl-1 font-display text-3xl font-semibold tabular-nums tracking-tight", tone === "bad" && "text-bad", tone === "good" && "text-good", tone === "warn" && "text-warn")}>
        {typeof value === "number" && Number.isInteger(value) ? <CountUp value={value} /> : value}
      </div>
    </div>
  );
}

export function LoadingRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className="h-10" />
      ))}
    </div>
  );
}

export function CitationList({ citations }: { citations: string[] }) {
  if (!citations?.length) return null;
  return (
    <span className="inline-flex flex-wrap gap-1">
      {citations.map((id) => (
        <Badge key={id} tone="info" title="Approved policy rule">
          Rule {id}
        </Badge>
      ))}
    </span>
  );
}
