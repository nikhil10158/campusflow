"use client";

import { AlertTriangle, CheckCircle2, Info, Loader2, X } from "lucide-react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

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

export function Badge({ tone = "neutral", children, title }: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span
      title={title}
      className={cx("inline-flex items-center gap-1 whitespace-nowrap border border-current/40 px-1.5 py-px font-mono text-[10.5px] font-medium uppercase tracking-wider", TONES[tone])}
    >
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

export function StatusBadge({ state }: { state: string }) {
  return <Badge tone={stateTone(state)}>{state.replace(/_/g, " ")}</Badge>;
}

export function Card({ title, actions, children, className }: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("hard rise bg-surface", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b-2 border-edge bg-surface2 px-4 py-2">
          {title && (
            <h2 className="flex items-center gap-2 font-mono text-[11px] font-medium uppercase tracking-[0.14em]">
              <span className="inline-block h-2 w-2 bg-primary" aria-hidden />
              {title}
            </h2>
          )}
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, actions, kicker }: { title: string; subtitle?: string; actions?: ReactNode; kicker?: string }) {
  return (
    <div className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b-2 border-edge pb-5">
      <div className="max-w-3xl">
        <p className="mb-2 font-mono text-[11px] uppercase tracking-[0.2em] text-primary">{kicker ?? "CampusFlow · operations"}</p>
        <h1 className="font-display text-4xl font-semibold leading-none tracking-tight sm:text-5xl">
          <span className="marker">{title}</span>
        </h1>
        {subtitle && <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "ghost" | "danger" | "outline";
  busy?: boolean;
}

export function Button({ variant = "primary", busy, className, children, disabled, ...rest }: ButtonProps) {
  const styles = {
    primary: "border-2 border-edge bg-primary text-primaryink shadow-[2px_2px_0_var(--shadow)] hover:-translate-x-px hover:-translate-y-px hover:shadow-[3px_3px_0_var(--shadow)] active:translate-x-0.5 active:translate-y-0.5 active:shadow-none",
    outline: "border-2 border-edge bg-surface text-ink shadow-[2px_2px_0_var(--shadow)] hover:-translate-x-px hover:-translate-y-px hover:bg-surface2 hover:shadow-[3px_3px_0_var(--shadow)] active:translate-x-0.5 active:translate-y-0.5 active:shadow-none",
    danger: "border-2 border-edge bg-bad text-primaryink shadow-[2px_2px_0_var(--shadow)] hover:-translate-x-px hover:-translate-y-px hover:shadow-[3px_3px_0_var(--shadow)] active:translate-x-0.5 active:translate-y-0.5 active:shadow-none",
    ghost: "border-2 border-transparent text-ink underline-offset-4 hover:underline",
  }[variant];
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      className={cx("inline-flex items-center justify-center gap-2 px-3 py-1.5 text-sm font-semibold transition-all disabled:cursor-not-allowed disabled:opacity-45 disabled:shadow-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary", styles, className)}
    >
      {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="flex flex-col gap-1 font-mono text-[10.5px] font-medium uppercase tracking-wider text-muted">
      {label}
      {children}
      {hint && <span className="font-sans text-xs font-normal normal-case tracking-normal">{hint}</span>}
    </label>
  );
}

const INPUT = "w-full border-2 border-edge bg-surface px-2.5 py-1.5 font-sans text-sm normal-case tracking-normal text-ink outline-none focus:bg-bg focus:shadow-[3px_3px_0_var(--primary)]";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(INPUT, props.className)} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx(INPUT, props.className)} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton h-6 w-full", className)} aria-hidden />;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="border-2 border-dashed border-line p-6 text-center font-mono text-xs uppercase tracking-wide text-muted">{children}</div>;
}

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="flex items-start gap-2 border-2 border-bad bg-badbg p-3 text-sm text-bad">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>{message}</span>
    </div>
  );
}

const NOTICE_EDGE: Record<string, string> = { info: "border-info", good: "border-good", warn: "border-warn", bad: "border-bad" };

export function Notice({ tone = "info", children }: { tone?: "info" | "good" | "warn" | "bad"; children: ReactNode }) {
  const Icon = tone === "good" ? CheckCircle2 : tone === "info" ? Info : AlertTriangle;
  return (
    <div className={cx("flex items-start gap-2 border-l-4 p-3 text-sm", NOTICE_EDGE[tone], TONES[tone])}>
      <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

export function Toasts() {
  const { toasts, dismiss } = useToasts();
  return (
    <div className="pointer-events-none fixed bottom-14 right-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={cx("hard-sm pointer-events-auto rise flex items-start justify-between gap-2 p-3 text-sm", TONES[toast.tone === "good" ? "good" : toast.tone === "bad" ? "bad" : "info"])}>
          <span>{toast.text}</span>
          <button onClick={() => dismiss(toast.id)} aria-label="Dismiss" className="shrink-0 opacity-70 hover:opacity-100">
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
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={onClose}>
      <aside className="h-full w-full max-w-md overflow-y-auto border-l-2 border-edge bg-surface p-5 shadow-[-6px_0_0_var(--shadow)]" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={title}>
        <div className="mb-4 flex items-center justify-between border-b-2 border-edge pb-2">
          <h2 className="font-display text-xl font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="p-1 hover:bg-surface2">
            <X className="h-4 w-4" />
          </button>
        </div>
        {children}
      </aside>
    </div>
  );
}

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: Tone }) {
  return (
    <div className="hard-sm bg-surface p-4">
      <div className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-muted">{label}</div>
      <div className={cx("mt-1 font-display text-4xl font-semibold leading-none tabular-nums", tone === "bad" && "text-bad", tone === "good" && "text-good", tone === "warn" && "text-warn")}>{value}</div>
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
          {id}
        </Badge>
      ))}
    </span>
  );
}
