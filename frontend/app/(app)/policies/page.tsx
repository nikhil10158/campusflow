"use client";

import { useMutation } from "@tanstack/react-query";
import { BookOpenCheck, ShieldAlert } from "lucide-react";
import { useState } from "react";

import { Badge, Button, Card, CitationList, ErrorBox, Input, Notice, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";

interface Answer {
  answer: string;
  citations: string[];
  refused: boolean;
  mode: string;
}

const SAMPLES = ["What is the lead time for an amphitheatre?", "How many nights can a guest stay?", "Who approves lab bookings?", "What is the hostel fee?", "What is the exam seating arrangement?"];

export default function PoliciesPage() {
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<{ question: string; answer: Answer }[]>([]);
  const ask = useMutation({
    mutationFn: (text: string) => api<Answer>("/agent/policies/ask", { body: { question: text } }),
    onSuccess: (answer, text) => setHistory((current) => [{ question: text, answer }, ...current]),
  });
  function submit(text: string) {
    if (!text.trim()) return;
    setQuestion("");
    ask.mutate(text);
  }
  return (
    <>
      <PageHeader title="Policy Q&A" subtitle="Answers come only from the approved policy file. If the policies do not cover a question, the answer is exactly: Not covered in the approved policies." />
      <Card>
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); submit(question); }}>
          <Input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask about booking rules…" aria-label="Policy question" />
          <Button type="submit" busy={ask.isPending}>Ask</Button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">{SAMPLES.map((s) => <button key={s} onClick={() => submit(s)} className="rounded-full border border-line px-3 py-1 text-xs hover:bg-surface2">{s}</button>)}</div>
      </Card>
      {ask.isError && <div className="mt-4"><ErrorBox error={ask.error} /></div>}
      <div className="mt-4 space-y-3">
        {history.map((item, index) => (
          <Card key={index}>
            <p className="mb-2 text-sm font-medium">{item.question}</p>
            {item.answer.refused ? (
              <Notice tone="warn"><span className="flex items-center gap-2"><ShieldAlert className="h-4 w-4" /> {item.answer.answer}</span></Notice>
            ) : (
              <div className="flex items-start gap-2 text-sm"><BookOpenCheck className="mt-0.5 h-4 w-4 shrink-0 text-good" aria-hidden /><div><p>{item.answer.answer}</p><div className="mt-2 flex items-center gap-2"><CitationList citations={item.answer.citations} /><Badge>{item.answer.mode}</Badge></div></div></div>
            )}
          </Card>
        ))}
      </div>
    </>
  );
}
