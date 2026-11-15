"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button, ErrorBox, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth, type User } from "@/lib/store";

const DEPARTURES = [
  { account: "admin", code: "ADM", place: "Command Center", platform: "1", color: "#ffd100" },
  { account: "faculty01", code: "FAC", place: "My Day", platform: "2", color: "#00a651" },
  { account: "student01", code: "STU", place: "My Requests", platform: "3", color: "#ff7a00" },
  { account: "hod.cse", code: "HOD", place: "Approvals · CSE", platform: "4", color: "#d4007f" },
  { account: "labincharge.cse", code: "LAB", place: "Approvals · labs", platform: "4", color: "#d4007f" },
  { account: "dean", code: "DEA", place: "Approvals · events", platform: "5", color: "#d4007f" },
  { account: "estate", code: "EST", place: "Approvals · venues", platform: "5", color: "#d4007f" },
  { account: "guesthouse.mgr", code: "GST", place: "Approvals · stays", platform: "6", color: "#00a3ad" },
  { account: "parking.officer", code: "PRK", place: "Approvals · parking", platform: "6", color: "#00a3ad" },
  { account: "security01", code: "SEC", place: "Gate Scan", platform: "7", color: "#ffffff" },
];

function landing(role: User["role"]): string {
  if (role === "security") return "/security";
  if (role === "admin") return "/admin";
  if (role === "student") return "/student";
  if (role === "faculty") return "/faculty";
  return "/approvals";
}

function Flaps({ text, delay = 0 }: { text: string; delay?: number }) {
  return (
    <span aria-label={text} className="inline-flex">
      {text.split("").map((char, index) => (
        <span key={index} className="flap flip" style={{ animationDelay: `${delay + index * 30}ms`, background: char === " " ? "transparent" : undefined }} aria-hidden>
          {char === " " ? " " : char}
        </span>
      ))}
    </span>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const login = useAuth((state) => state.login);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("Demo@1234");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function submit(address: string) {
    setBusy(true);
    setError(null);
    try {
      const result = await api<{ token: string; user: User }>("/auth/login", { body: { email: address, password } });
      login(result.token, result.user);
      router.push(landing(result.user.role));
    } catch (problem) {
      setError(problem);
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    submit(email);
  }

  return (
    <div className="min-h-screen bg-board text-white">
      <div className="mx-auto grid min-h-screen max-w-6xl content-center gap-8 px-4 py-10 lg:grid-cols-[1.5fr_1fr]">
        <section aria-label="Demo accounts">
          <div className="mb-5 flex items-center gap-3">
            <span className="relative grid h-11 w-11 place-items-center rounded-full border-[6px] border-primary" aria-hidden>
              <span className="absolute left-[-10px] right-[-10px] top-1/2 h-3.5 -translate-y-1/2 bg-boardink" />
              <span className="relative font-display text-xs font-bold text-board">CF</span>
            </span>
            <div>
              <h1 className="font-display text-4xl font-bold uppercase leading-none tracking-[0.12em]">Campusflow</h1>
              <p className="font-display text-sm uppercase tracking-[0.3em] text-white/50">Departures · synthetic campus</p>
            </div>
          </div>
          <div className="grid grid-cols-[3.2rem_1fr_3.2rem] items-center gap-3 border-b border-white/20 pb-1 font-display text-xs uppercase tracking-[0.25em] text-white/40 sm:grid-cols-[4rem_1fr_auto_4rem]">
            <span>Role</span>
            <span>Destination</span>
            <span className="hidden sm:block">Account</span>
            <span className="text-right">Plat.</span>
          </div>
          <ul>
            {DEPARTURES.map((row, index) => (
              <li key={row.account}>
                <button
                  disabled={busy}
                  onClick={() => submit(`${row.account}@jklu.demo`)}
                  className="group grid w-full grid-cols-[3.2rem_1fr_3.2rem] items-center gap-3 border-b border-white/10 py-2.5 text-left transition-colors hover:bg-primary hover:text-primaryink disabled:opacity-50 sm:grid-cols-[4rem_1fr_auto_4rem]"
                >
                  <span className="flex items-center gap-2">
                    <span className="h-3 w-1.5" style={{ background: row.color }} aria-hidden />
                    <span className="font-mono text-sm font-medium text-boardink group-hover:text-primaryink">{row.code}</span>
                  </span>
                  <span className="font-display text-2xl font-semibold uppercase tracking-wide">
                    <Flaps text={row.place.toUpperCase()} delay={index * 70} />
                  </span>
                  <span className="hidden font-mono text-xs text-white/50 group-hover:text-primaryink sm:block">{row.account}</span>
                  <span className="text-right font-mono text-lg text-boardink group-hover:text-primaryink">{row.platform}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="self-center border-t-4 border-primary bg-surface p-6 text-ink">
          <h2 className="font-display text-3xl font-bold uppercase tracking-wide">Sign in</h2>
          <p className="mb-4 text-sm text-muted">Tap a departure on the board, or type an account here.</p>
          <form onSubmit={onSubmit} className="space-y-4">
            <Field label="Email">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="admin@jklu.demo" autoComplete="username" />
            </Field>
            <Field label="Password" hint="Every demo account uses Demo@1234">
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
            </Field>
            {error ? <ErrorBox error={error} /> : null}
            <Button type="submit" busy={busy} className="w-full">
              Board
            </Button>
          </form>
        </section>
      </div>
    </div>
  );
}
