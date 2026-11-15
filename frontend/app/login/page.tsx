"use client";

import { Car, ClipboardCheck, GraduationCap, KeyRound, MapPin, ShieldCheck, Shield, Hotel, Landmark, Presentation, Settings2, type LucideIcon } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button, ErrorBox, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { useAuth, type User } from "@/lib/store";

const ROLES: { account: string; title: string; text: string; icon: LucideIcon }[] = [
  { account: "admin", title: "Administrator", text: "Runs the campus: imports, closures, reports", icon: Settings2 },
  { account: "faculty01", title: "Faculty", text: "Books rooms and requests extra classes", icon: Presentation },
  { account: "student01", title: "Student club lead", text: "Requests rooms with a faculty sponsor", icon: GraduationCap },
  { account: "hod.cse", title: "Head of department", text: "Approves lab and department requests", icon: ClipboardCheck },
  { account: "labincharge.cse", title: "Lab in-charge", text: "First approver for lab bookings", icon: KeyRound },
  { account: "dean", title: "Dean", text: "Approves large events", icon: Landmark },
  { account: "estate", title: "Estate office", text: "Approves amphitheatre bookings", icon: Shield },
  { account: "guesthouse.mgr", title: "Guest house manager", text: "Approves stays and the waitlist", icon: Hotel },
  { account: "parking.officer", title: "Parking officer", text: "Approves parking and releases no-shows", icon: Car },
  { account: "security01", title: "Security", text: "Checks parking passes at the gate", icon: ShieldCheck },
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
    <div className="min-h-screen">
      <div className="mx-auto grid min-h-screen max-w-6xl content-center gap-10 px-5 py-10 lg:grid-cols-[1.35fr_1fr]">
        <section>
          <div className="card-in mb-6 flex items-center gap-3">
            <span className="drift grid h-11 w-11 place-items-center rounded-xl bg-primary text-primaryink shadow-lift">
              <MapPin className="h-6 w-6" aria-hidden />
            </span>
            <span className="font-display text-2xl font-semibold tracking-tight">CampusFlow</span>
          </div>
          <h1 className="card-in max-w-xl text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
            Find and book campus spaces without the{" "}
            <span className="relative inline-block whitespace-nowrap text-primary">
              back-and-forth
              <svg className="underline-draw absolute -bottom-2 left-0 h-3 w-full" viewBox="0 0 200 12" preserveAspectRatio="none" aria-hidden>
                <path d="M2 8 C 40 2, 90 12, 130 6 S 185 4, 198 7" fill="none" stroke="var(--accent)" strokeWidth="3.5" strokeLinecap="round" />
              </svg>
            </span>
            .
          </h1>
          <p className="card-in mt-5 max-w-xl text-lg leading-relaxed text-muted">Rooms, labs, guest rooms and parking in one place. Ask in plain words, see what is really free, and let the right people approve.</p>
          <h2 className="mb-3 mt-8 text-sm font-semibold uppercase tracking-wide text-muted">Try the demo as…</h2>
          <div className="stagger grid gap-3 sm:grid-cols-2">
            {ROLES.map((role) => (
              <button key={role.account} disabled={busy} onClick={() => submit(`${role.account}@jklu.demo`)} className="group flex items-start gap-3 rounded-xl border border-line bg-surface p-3.5 text-left shadow-card transition duration-200 hover:-translate-y-1 hover:border-primary hover:shadow-lift active:scale-[0.98] disabled:opacity-50">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-goodbg text-primary transition duration-200 group-hover:rotate-[-6deg] group-hover:scale-110 group-hover:bg-primary group-hover:text-primaryink">
                  <role.icon className="h-5 w-5" aria-hidden />
                </span>
                <span>
                  <span className="block font-semibold">{role.title}</span>
                  <span className="block text-sm leading-snug text-muted">{role.text}</span>
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="card-in self-center rounded-2xl border border-line border-t-4 border-t-primary bg-surface p-7 shadow-lift" style={{ animationDelay: "0.2s" }}>
          <h2 className="text-2xl font-semibold">Sign in</h2>
          <p className="mb-5 mt-1 text-[15px] text-muted">Pick a role on the left, or enter an account here.</p>
          <form onSubmit={onSubmit} className="space-y-4">
            <Field label="Email">
              <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="admin@jklu.demo" autoComplete="username" />
            </Field>
            <Field label="Password" hint="Every demo account uses Demo@1234">
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
            </Field>
            {error ? <ErrorBox error={error} /> : null}
            <Button type="submit" busy={busy} className="w-full py-2.5 text-base">
              Sign in
            </Button>
          </form>
          <p className="mt-5 text-center text-sm text-muted">All data here is synthetic. Nothing is real.</p>
        </section>
      </div>
    </div>
  );
}
