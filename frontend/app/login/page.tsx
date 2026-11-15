"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button, ErrorBox, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth, type User } from "@/lib/store";

const CHIPS = [
  ["admin", "Admin"], ["hod.cse", "HoD CSE"], ["labincharge.cse", "Lab in-charge"], ["dean", "Dean"], ["estate", "Estate"],
  ["guesthouse.mgr", "Guest house"], ["parking.officer", "Parking"], ["faculty01", "Faculty"], ["student01", "Student"], ["security01", "Security"],
];

const POSTER = [
  "A", "A", ".", "B", "B", "B", ".", "C",
  ".", "D", "D", ".", "A", ".", "C", "C",
  "B", ".", "A", "A", ".", "D", "D", ".",
  "C", "C", ".", "B", "B", ".", "A", ".",
];

const CELL: Record<string, string> = { A: "bg-primary", B: "bg-marker", C: "bg-accent", D: "bg-ink", ".": "bg-transparent" };

function landing(role: User["role"]): string {
  if (role === "security") return "/security";
  if (role === "admin") return "/admin";
  if (role === "student") return "/student";
  if (role === "faculty") return "/faculty";
  return "/approvals";
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
    <div className="grid min-h-screen lg:grid-cols-[1.15fr_1fr]">
      <section className="relative flex flex-col justify-between overflow-hidden border-b-2 border-edge bg-ink p-8 text-bg lg:border-b-0 lg:border-r-2 lg:p-14">
        <p className="font-mono text-xs uppercase tracking-[0.3em] opacity-70">Synthetic campus · demo only</p>
        <div className="my-10">
          <h1 className="font-display text-5xl font-semibold leading-[0.95] tracking-tight sm:text-7xl">
            Which room is <span className="italic text-marker">really</span> free right now?
          </h1>
          <p className="mt-6 max-w-md text-lg leading-relaxed opacity-80">
            Timetables, cancelled classes, ghost lectures, guest rooms and parking in one plan. The assistant proposes. People decide.
          </p>
        </div>
        <div aria-hidden>
          <div className="grid grid-cols-8 gap-1.5">
            {POSTER.map((cell, index) => (
              <span key={index} className={`h-9 border border-bg/25 ${CELL[cell]}`} />
            ))}
          </div>
          <p className="mt-3 font-mono text-[10px] uppercase tracking-widest opacity-60">Mon — Thu · periods 1–8 · one square, one class</p>
        </div>
      </section>

      <section className="flex items-center justify-center p-6 lg:p-12">
        <div className="hard w-full max-w-md bg-surface p-7">
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-primary">Sign in</p>
          <h2 className="font-display text-3xl font-semibold">
            <span className="italic">campus</span>flow
          </h2>
          <p className="mb-5 mt-1 text-sm text-muted">Pick a role to walk the demo, or type an account.</p>
          <div className="mb-5 flex flex-wrap gap-2" role="group" aria-label="Demo accounts">
            {CHIPS.map(([name, label]) => (
              <button key={name} disabled={busy} onClick={() => submit(`${name}@jklu.demo`)} className="chip disabled:opacity-50">
                {label}
              </button>
            ))}
          </div>
          <form onSubmit={onSubmit} className="space-y-4">
            <Field label="Email">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="admin@jklu.demo" autoComplete="username" />
            </Field>
            <Field label="Password" hint="Every demo account uses Demo@1234">
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
            </Field>
            {error ? <ErrorBox error={error} /> : null}
            <Button type="submit" busy={busy} className="w-full">
              Enter the control room
            </Button>
          </form>
        </div>
      </section>
    </div>
  );
}
