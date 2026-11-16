"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { BookOpenCheck, Search, ShieldAlert } from "lucide-react";
import { useMemo, useState } from "react";

import { Badge, Button, Card, CitationList, Empty, ErrorBox, Input, LoadingRows, Notice, PageHeader, cx } from "@/components/ui";
import { api } from "@/lib/api";

interface Answer {
  answer: string;
  citations: string[];
  refused: boolean;
  mode: string;
}

interface Section {
  id: string;
  title: string;
  rules: { id: string; text: string }[];
}

const SAMPLES = ["What is the lead time for an amphitheatre?", "How many nights can a guest stay?", "Who approves lab bookings?", "What is the hostel fee?"];

export default function PoliciesPage() {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<{ question: string; answer: Answer }[]>([]);
  const [filter, setFilter] = useState("");
  const [only, setOnly] = useState<string | null>(null);
  const sections = useQuery({ queryKey: ["policies"], queryFn: () => api<Section[]>("/agent/policies"), staleTime: Infinity });
  const ask = useMutation({
    mutationFn: (text: string) => api<Answer>("/agent/policies/ask", { body: { question: text } }),
    onSuccess: (answer, text) => setHistory((current) => [{ question: text, answer }, ...current]),
  });
  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return (sections.data ?? [])
      .filter((section) => !only || section.id === only)
      .map((section) => ({ ...section, rules: section.rules.filter((rule) => !needle || `${rule.id} ${rule.text}`.toLowerCase().includes(needle)) }))
      .filter((section) => section.rules.length > 0);
  }, [sections.data, filter, only]);
  const total = (sections.data ?? []).reduce((sum, section) => sum + section.rules.length, 0);

  function submit(text: string) {
    if (!text.trim()) return;
    setQuestion("");
    ask.mutate(text);
  }

  return (
    <>
      <PageHeader title="Booking rules" subtitle="Every rule the planner applies is listed below. Ask a question to get a cited answer. Answers come only from the approved policy file." />
      <Card title="Ask about a rule">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); submit(question); }}>
          <Input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="For example: how long can a guest stay?" aria-label="Policy question" />
          <Button type="submit" busy={ask.isPending}>Ask</Button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">{SAMPLES.map((s) => <button key={s} onClick={() => submit(s)} className="chip">{s}</button>)}</div>
        {ask.isError && <div className="mt-3"><ErrorBox error={ask.error} /></div>}
        <div className="mt-3 space-y-3">
          {history.map((item, index) => (
            <div key={index} className="slide rounded-xl border border-line bg-surface2 p-4">
              <p className="mb-2 text-sm font-semibold">{item.question}</p>
              {item.answer.refused ? (
                <Notice tone="warn"><span className="flex items-center gap-2"><ShieldAlert className="h-4 w-4" /> {item.answer.answer}</span></Notice>
              ) : (
                <div className="flex items-start gap-2 text-[15px]"><BookOpenCheck className="mt-0.5 h-4 w-4 shrink-0 text-good" aria-hidden /><div><p>{item.answer.answer}</p><div className="mt-2 flex items-center gap-2"><CitationList citations={item.answer.citations} /><Badge>{item.answer.mode}</Badge></div></div></div>
              )}
            </div>
          ))}
        </div>
      </Card>

      <div className="mb-3 mt-8 flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-2xl font-semibold tracking-tight">All booking rules <span className="text-base font-normal text-muted">({total})</span></h2>
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" aria-hidden />
          <Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter rules, e.g. lab or 24 hours" aria-label="Filter rules" className="pl-9" />
        </div>
      </div>
      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Rule sections">
        <button onClick={() => setOnly(null)} aria-pressed={only === null} className={cx("chip", only === null && "!border-primary !bg-tint !text-link")}>All</button>
        {(sections.data ?? []).map((section) => (
          <button key={section.id} onClick={() => setOnly(only === section.id ? null : section.id)} aria-pressed={only === section.id} className={cx("chip", only === section.id && "!border-primary !bg-tint !text-link")}>
            {section.title}
          </button>
        ))}
      </div>

      {sections.isPending ? <LoadingRows rows={5} /> : sections.isError ? <ErrorBox error={sections.error} /> : shown.length === 0 ? <Empty>No rule matches that filter.</Empty> : (
        <div className="stagger grid gap-4 xl:grid-cols-2">
          {shown.map((section) => (
            <Card key={section.id} title={<span className="flex items-center gap-2"><Badge tone="primary">{section.id}</Badge>{section.title}</span>}>
              <ul className="divide-y divide-line">
                {section.rules.map((rule) => (
                  <li key={rule.id} className="flex gap-3 py-2.5 first:pt-0 last:pb-0">
                    <span className="mt-0.5 h-fit shrink-0 rounded-md bg-tint px-2 py-0.5 font-mono text-xs font-semibold text-link">{rule.id}</span>
                    <p className="text-[15px] leading-snug">{rule.text}</p>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
