"use client";

import { ArrowRight, CheckCircle2, Loader2, Mic, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ProposalCard } from "@/components/ProposalCard";
import { Badge, Button, Card, Notice, PageHeader, cx } from "@/components/ui";
import { streamAgent } from "@/lib/agent";
import { useToasts } from "@/lib/store";
import type { AgentEvent, Proposal } from "@/lib/types";

interface Message {
  role: "user" | "assistant";
  text: string;
}

interface ToolStep {
  id: number;
  name: string;
  args: Record<string, unknown>;
  rationale: string;
  summary?: string;
  latency?: number;
  error?: boolean;
}

interface Clarify {
  question: string;
  options: string[];
  field: string;
  original: string;
}

const EXAMPLES = [
  "Host a 2-day AI workshop on 3–4 Dec for 80 people, 2 external speakers staying 2 nights, 12 cars",
  "Find a free classroom tomorrow 2–4 pm for 60",
  "Find a common slot for Sem 5 CSE A and B for a 1 hour quiz next week",
  "Book lab L-3 on 20 Nov 10 to 1",
  "What is the lead time for an amphitheatre?",
  "Lab Complex 1 closed Wed–Thu for repairs",
];

interface SpeechRecognitionLike {
  lang: string;
  start: () => void;
  onresult: ((event: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onend: (() => void) | null;
}

function speechConstructor(): (new () => SpeechRecognitionLike) | null {
  const scope = window as unknown as { SpeechRecognition?: new () => SpeechRecognitionLike; webkitSpeechRecognition?: new () => SpeechRecognitionLike };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

export default function Concierge() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [plan, setPlan] = useState<string[]>([]);
  const [done, setDone] = useState(0);
  const [steps, setSteps] = useState<ToolStep[]>([]);
  const [verify, setVerify] = useState<Extract<AgentEvent, { type: "verify" }> | null>(null);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [clarify, setClarify] = useState<Clarify | null>(null);
  const [finished, setFinished] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const push = useToasts((state) => state.push);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, steps]);

  async function run(text: string, clarification: Clarify | null = null, answer = "") {
    const shown = clarification ? answer : text;
    setMessages((current) => [...current, { role: "user", text: shown }, { role: "assistant", text: "" }]);
    setBusy(true);
    setPlan([]);
    setDone(0);
    setSteps([]);
    setVerify(null);
    setProposals([]);
    setClarify(null);
    setFinished(false);
    const original = clarification ? clarification.original : text;
    try {
      await streamAgent(original, clarification ? { original, answer, field: clarification.field } : null, (event) => {
        if (event.type === "plan") setPlan(event.steps);
        else if (event.type === "plan_progress") setDone(event.done);
        else if (event.type === "tool_call") setSteps((current) => [...current, { id: event.id, name: event.name, args: event.args, rationale: event.rationale }]);
        else if (event.type === "tool_result") setSteps((current) => current.map((step) => (step.id === event.id ? { ...step, summary: event.summary, latency: event.latency_ms, error: event.error } : step)));
        else if (event.type === "verify") setVerify(event);
        else if (event.type === "proposal") setProposals((current) => [...current, event.proposal]);
        else if (event.type === "clarify") setClarify({ question: event.question, options: event.options, field: event.field, original });
        else if (event.type === "answer_delta") setMessages((current) => current.map((m, i) => (i === current.length - 1 ? { ...m, text: m.text + event.text } : m)));
        else if (event.type === "done") setFinished(true);
      });
    } catch (problem) {
      push("bad", problem instanceof Error ? problem.message.slice(0, 160) : "The assistant failed");
      setMessages((current) => current.map((m, i) => (i === current.length - 1 && !m.text ? { ...m, text: "Something went wrong talking to the planner." } : m)));
    } finally {
      setBusy(false);
    }
  }

  function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    run(text);
  }

  function listen() {
    const Recognition = speechConstructor();
    if (!Recognition) {
      push("info", "Voice input is not supported in this browser. Type your request instead.");
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "en-IN";
    recognition.onresult = (event) => setInput(event.results[0][0].transcript);
    recognition.onend = () => setListening(false);
    setListening(true);
    recognition.start();
  }

  const visibleSteps = steps.filter((step) => step.name !== "declare_plan");
  const started = messages.length > 0;

  return (
    <>
      <PageHeader kicker="Concierge" title="Say it in one sentence" subtitle="The planner turns a sentence into a venue, guest-house and parking plan, checks every rule twice, and stops at the platform edge. You press Submit; approvers decide." />

      <form
        onSubmit={(event) => {
          event.preventDefault();
          send();
        }}
        className="bg-board text-white"
      >
        <label htmlFor="ask" className="flex items-center justify-between border-b border-white/15 px-4 py-1.5 font-display text-sm uppercase tracking-[0.25em] text-boardink">
          <span>Check-in · where to?</span>
          <span className="text-white/50">{busy ? "Boarding…" : "Ready"}</span>
        </label>
        <div className="flex items-stretch">
          <input
            id="ask"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Host a 2-day AI workshop on 3–4 Dec for 80 people, 2 external speakers, 12 cars"
            className="min-w-0 flex-1 bg-transparent px-4 py-5 font-display text-2xl uppercase tracking-wide outline-none placeholder:text-white/30 sm:text-3xl"
            autoComplete="off"
          />
          <button type="button" onClick={listen} aria-label="Voice input" className={cx("border-l border-white/15 px-4 hover:bg-white/10", listening && "bg-boardink text-board")}>
            <Mic className="h-5 w-5" />
          </button>
          <button type="submit" disabled={busy || !input.trim()} aria-label="Send" className="flex items-center gap-2 bg-primary px-6 font-display text-xl font-bold uppercase tracking-widest text-primaryink hover:bg-white disabled:opacity-40">
            {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <ArrowRight className="h-5 w-5" />} Go
          </button>
        </div>
      </form>

      {!started && (
        <div className="mt-6">
          <p className="mb-2 font-display text-sm uppercase tracking-[0.25em] text-muted">Popular routes</p>
          <div className="flex flex-wrap gap-2.5">
            {EXAMPLES.map((example) => (
              <button key={example} onClick={() => run(example)} className="chip max-w-full text-left">
                {example}
              </button>
            ))}
          </div>
        </div>
      )}

      {started && (
        <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
          <Card title="Announcements">
            <div className="max-h-[46vh] space-y-3 overflow-y-auto pr-1" aria-live="polite">
              {messages.map((message, index) => (
                <div key={index} className={cx("slide", message.role === "user" ? "ml-10 bg-board px-3 py-2 text-white" : "border-l-8 border-primary bg-surface2 px-3 py-2")}>
                  <p className="font-display text-xs uppercase tracking-[0.25em] opacity-60">{message.role === "user" ? "Passenger" : "Planner"}</p>
                  <p className="whitespace-pre-wrap leading-relaxed">{message.text || (busy && index === messages.length - 1 ? <Loader2 className="h-4 w-4 animate-spin" aria-label="Thinking" /> : "")}</p>
                </div>
              ))}
              {clarify && (
                <div className="border-2 border-dashed border-edge p-3">
                  <p className="mb-2 font-display text-lg font-semibold uppercase tracking-wide">{clarify.question}</p>
                  <div className="flex flex-wrap gap-2">
                    {clarify.options.map((option) => (
                      <button key={option} onClick={() => run(clarify.original, clarify, option)} className="chip">
                        {option}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div ref={bottom} />
            </div>
          </Card>

          <Card title="Route">
            {plan.length === 0 && steps.length === 0 ? (
              <p className="text-sm text-muted">Each stop on the line is a step of the plan. Tool calls hang off the stop that needed them.</p>
            ) : (
              <ol className="relative ml-3">
                <span className="absolute bottom-3 left-[10px] top-3 w-[5px] bg-edge" aria-hidden />
                {plan.map((step, index) => {
                  const complete = finished || index < done;
                  const call = visibleSteps[index];
                  return (
                    <li key={step} className="relative pb-5 pl-9">
                      <span className={cx("absolute left-0 top-0.5 grid h-6 w-6 place-items-center rounded-full border-[4px] border-edge", complete ? "bg-accent" : "bg-surface")} aria-hidden>
                        {complete && <span className="h-1.5 w-1.5 rounded-full bg-edge" />}
                      </span>
                      <p className={cx("font-display text-xl font-semibold uppercase leading-tight tracking-wide", !complete && "text-muted")}>{step}</p>
                      {call && (
                        <div className="slide mt-1.5 border border-line border-l-4 border-l-primary bg-surface2 p-2 text-xs">
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-mono font-medium">{call.name}()</span>
                            {call.summary === undefined ? <Loader2 className="h-3 w-3 animate-spin" aria-label="Running" /> : <Badge tone={call.error ? "bad" : "good"}>{call.latency?.toFixed(0)} ms</Badge>}
                          </div>
                          <p className="mt-1 text-muted">{call.rationale}</p>
                          <p className="mt-1 break-all font-mono text-[11px] opacity-60">{JSON.stringify(call.args).slice(0, 140)}</p>
                          {call.summary && <p className={cx("mt-1 font-medium", call.error && "text-bad")}>→ {call.summary}</p>}
                        </div>
                      )}
                    </li>
                  );
                })}
                {verify && (
                  <li className="relative pl-9">
                    <span className="absolute left-0 top-0.5 grid h-6 w-6 place-items-center rounded-full border-[4px] border-edge bg-primary font-display text-[11px] font-bold" aria-hidden>
                      2×
                    </span>
                    <p className="mb-1 font-display text-xl font-semibold uppercase leading-tight tracking-wide">Terminus · checked twice</p>
                    <div className="flex flex-wrap gap-2 text-xs">
                      <Badge tone={verify.policy.ok ? "good" : "bad"}>
                        {verify.policy.ok ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />} policy engine
                      </Badge>
                      <Badge tone={verify.validator.ok ? "good" : "bad"}>
                        {verify.validator.ok ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />} independent validator
                      </Badge>
                    </div>
                  </li>
                )}
              </ol>
            )}
          </Card>
        </div>
      )}

      {proposals.length > 0 && (
        <div className="mt-8 space-y-6">
          {proposals.map((proposal, index) => (
            <ProposalCard key={`${proposal.title}-${index}`} proposal={proposal} onDiscard={() => setProposals((current) => current.filter((_, i) => i !== index))} />
          ))}
        </div>
      )}
      {finished && proposals.length === 0 && !clarify && started && (
        <div className="mt-6">
          <Notice tone="info">No state was changed. When a proposal appears you decide whether to submit it.</Notice>
        </div>
      )}
    </>
  );
}
