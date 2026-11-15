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
    <span title={title} className={cx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap", TONES[tone])}>
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
    <section className={cx("rounded-xl border border-line bg-surface p-4 shadow-sm", className)}>
      {(title || actions) && (
        <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold tracking-tight">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-muted">{subtitle}</p>}
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
    primary: "bg-primary text-primaryink hover:opacity-90",
    ghost: "text-ink hover:bg-surface2",
    outline: "border border-line text-ink hover:bg-surface2",
    danger: "bg-bad text-primaryink hover:opacity-90",
  }[variant];
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      className={cx("inline-flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary", styles, className)}
    >
      {busy && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-muted">
      {label}
      {children}
      {hint && <span className="font-normal">{hint}</span>}
    </label>
  );
}

const INPUT = "w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink outline-none focus:border-primary focus:ring-2 focus:ring-primary/30";

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
  return <div className="rounded-lg border border-dashed border-line p-6 text-center text-sm text-muted">{children}</div>;
}

export function ErrorBox({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="flex items-start gap-2 rounded-lg bg-badbg p-3 text-sm text-bad">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <span>{message}</span>
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "good" | "warn" | "bad"; children: ReactNode }) {
  const Icon = tone === "good" ? CheckCircle2 : tone === "info" ? Info : AlertTriangle;
  return (
    <div className={cx("flex items-start gap-2 rounded-lg p-3 text-sm", TONES[tone])}>
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
        <div key={toast.id} className={cx("pointer-events-auto flex items-start justify-between gap-2 rounded-lg border border-line p-3 text-sm shadow-lg", TONES[toast.tone === "good" ? "good" : toast.tone === "bad" ? "bad" : "info"])}>
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
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={onClose}>
      <aside className="h-full w-full max-w-md overflow-y-auto border-l border-line bg-surface p-5 shadow-xl" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={title}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold">{title}</h2>
          <button onClick={onClose} aria-label="Close" className="rounded p-1 hover:bg-surface2">
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
    <div className="rounded-xl border border-line bg-surface p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className={cx("mt-1 text-2xl font-semibold tabular-nums", tone === "bad" && "text-bad", tone === "good" && "text-good", tone === "warn" && "text-warn")}>{value}</div>
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
