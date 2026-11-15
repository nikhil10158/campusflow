"use client";

import { MapPin } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button, ErrorBox, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth, type User } from "@/lib/store";

const CHIPS = [
  ["admin", "Admin"], ["hod.cse", "HoD CSE"], ["labincharge.cse", "Lab in-charge"], ["dean", "Dean"], ["estate", "Estate"],
  ["guesthouse.mgr", "Guest house"], ["parking.officer", "Parking"], ["faculty01", "Faculty"], ["student01", "Student (club lead)"], ["security01", "Security"],
];

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
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-6 shadow-lg">
        <div className="mb-1 flex items-center gap-2 text-xl font-semibold">
          <MapPin className="h-5 w-5 text-primary" aria-hidden /> CampusFlow
        </div>
        <p className="mb-4 text-sm text-muted">Agentic space planning for a synthetic JKLU-like campus. Pick a demo role or sign in.</p>
        <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Demo accounts">
          {CHIPS.map(([name, label]) => (
            <button key={name} disabled={busy} onClick={() => submit(`${name}@jklu.demo`)} className="rounded-full border border-line px-3 py-1 text-xs hover:bg-surface2 disabled:opacity-50">
              {label}
            </button>
          ))}
        </div>
        <form onSubmit={onSubmit} className="space-y-3">
          <Field label="Email">
            <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="admin@jklu.demo" autoComplete="username" />
          </Field>
          <Field label="Password" hint="Demo accounts all use Demo@1234">
            <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </Field>
          {error ? <ErrorBox error={error} /> : null}
          <Button type="submit" busy={busy} className="w-full">
            Sign in
          </Button>
        </form>
        <p className="mt-4 text-center text-xs text-muted">SYNTHETIC DATA — no real people, systems or payments.</p>
      </div>
    </div>
  );
}
