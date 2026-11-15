"use client";

import { ArrowUp, CheckCircle2, Circle, Loader2, Mic, RotateCcw, Sparkles, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ProposalCard } from "@/components/ProposalCard";
import { Badge, Card, Notice, cx } from "@/components/ui";
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
  { title: "Plan a whole event", text: "Host a 2-day AI workshop on 3–4 Dec for 80 people, 2 external speakers staying 2 nights, 12 cars" },
  { title: "Find a free room", text: "Find a free classroom tomorrow 2–4 pm for 60" },
  { title: "Find a time for a quiz", text: "Find a common slot for Sem 5 CSE A and B for a 1 hour quiz next week" },
  { title: "Book a lab", text: "Book lab L-3 on 20 Nov 10 to 1" },
  { title: "Ask about the rules", text: "What is the lead time for an amphitheatre?" },
  { title: "Handle a closure (admin)", text: "Lab Complex 1 closed Wed–Thu for repairs" },
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
  const proposalBox = useRef<HTMLDivElement>(null);
  const askBox = useRef<HTMLInputElement>(null);
  const push = useToasts((state) => state.push);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages, steps]);

  useEffect(() => {
    if (proposals.length > 0) proposalBox.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [proposals.length]);

  useEffect(() => {
    const focusAsk = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) {
        event.preventDefault();
        askBox.current?.focus();
      }
    };
    window.addEventListener("keydown", focusAsk);
    return () => window.removeEventListener("keydown", focusAsk);
  }, []);

  function startOver() {
    setMessages([]);
    setPlan([]);
    setSteps([]);
    setProposals([]);
    setClarify(null);
    setVerify(null);
    setFinished(false);
    askBox.current?.focus();
  }

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
      <div className="mx-auto max-w-3xl pb-6 pt-2 text-center">
        <span className="drift mx-auto mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-primary text-primaryink shadow-lift">
          <Sparkles className="h-7 w-7" aria-hidden />
        </span>
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">What do you need?</h1>
        <p className="mt-3 text-lg text-muted">Describe it in your own words. The assistant finds free rooms, guest rooms and parking, checks the rules, and prepares a request for you to review.</p>
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          send();
        }}
        className="mx-auto flex max-w-3xl items-center gap-2 rounded-2xl border border-edge bg-surface p-2 shadow-lift transition duration-200 focus-within:border-primary focus-within:ring-4 focus-within:ring-primary/15"
      >
        <input
          id="ask"
          ref={askBox}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="For example: a free classroom tomorrow 2–4 pm for 60 students"
          aria-label="Your request"
          className="min-w-0 flex-1 bg-transparent px-3 py-3 text-lg outline-none placeholder:text-muted/70"
          autoComplete="off"
        />
        <button type="button" onClick={listen} aria-label="Speak your request" className={cx("grid h-11 w-11 place-items-center rounded-xl text-muted hover:bg-surface2", listening && "bg-tint text-primary")}>
          <Mic className="h-5 w-5" />
        </button>
        <button type="submit" disabled={busy || !input.trim()} aria-label="Send" className="grid h-11 w-11 place-items-center rounded-xl bg-primary text-primaryink transition duration-150 hover:scale-105 hover:brightness-110 active:scale-95 disabled:opacity-40 disabled:hover:scale-100">
          {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <ArrowUp className="h-5 w-5" />}
        </button>
      </form>
      <p className="mx-auto mt-2 max-w-3xl text-center text-sm text-muted">
        Press <kbd className="rounded bg-surface2 px-1.5">/</kbd> to start typing.
        {started && !busy && (
          <button onClick={startOver} className="ml-3 inline-flex items-center gap-1 font-medium text-primary hover:underline">
            <RotateCcw className="h-3.5 w-3.5" /> Start over
          </button>
        )}
      </p>

      {!started && (
        <div className="mx-auto mt-8 max-w-3xl">
          <p className="mb-3 text-sm font-semibold text-muted">Try one of these</p>
          <div className="stagger grid gap-3 sm:grid-cols-2">
            {EXAMPLES.map((example) => (
              <button key={example.text} onClick={() => run(example.text)} className="rounded-xl border border-line bg-surface p-4 text-left shadow-card transition duration-200 hover:-translate-y-1 hover:border-primary hover:shadow-lift active:scale-[0.98]">
                <span className="block font-semibold">{example.title}</span>
                <span className="mt-1 block text-[15px] leading-snug text-muted">{example.text}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {started && (
        <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <Card title="Conversation">
            <div className="max-h-[46vh] space-y-3 overflow-y-auto pr-1" aria-live="polite">
              {messages.map((message, index) => (
                <div key={index} className={cx("slide max-w-[92%] rounded-2xl px-4 py-2.5 leading-relaxed", message.role === "user" ? "ml-auto bg-primary text-primaryink" : "bg-surface2")}>
                  <p className="whitespace-pre-wrap">{message.text || (busy && index === messages.length - 1 ? <Loader2 className="h-4 w-4 animate-spin" aria-label="Thinking" /> : "")}</p>
                </div>
              ))}
              {clarify && (
                <div className="rounded-xl border border-primary/40 bg-tint/50 p-3.5">
                  <p className="mb-2 font-medium">{clarify.question}</p>
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

          <Card title="What the assistant is doing">
            {plan.length === 0 && steps.length === 0 ? (
              <p className="text-[15px] text-muted">The steps appear here as the assistant works, so you can see how it got to its answer.</p>
            ) : (
              <ol className="space-y-4">
                {plan.map((step, index) => {
                  const complete = finished || index < done;
                  const call = visibleSteps[index];
                  return (
                    <li key={step} className="flex gap-3">
                      {complete ? <CheckCircle2 className="tick-in mt-0.5 h-5 w-5 shrink-0 text-good" aria-hidden /> : <Circle className="mt-0.5 h-5 w-5 shrink-0 text-edge" aria-hidden />}
                      <div className="min-w-0 flex-1">
                        <p className={cx("font-medium", !complete && "text-muted")}>{step}</p>
                        {call && (
                          <details className="mt-1 rounded-lg bg-surface2 px-3 py-2 text-sm">
                            <summary className="flex cursor-pointer items-center justify-between gap-2">
                              <span className="text-muted">{call.summary ?? "Working…"}</span>
                              {call.summary === undefined ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-label="Running" /> : <Badge tone={call.error ? "bad" : "good"}>{call.latency?.toFixed(0)} ms</Badge>}
                            </summary>
                            <p className="mt-2 text-muted">{call.rationale}</p>
                            <p className="mt-1 break-all font-mono text-xs text-muted">{call.name}({JSON.stringify(call.args).slice(0, 140)})</p>
                          </details>
                        )}
                      </div>
                    </li>
                  );
                })}
                {verify && (
                  <li className="flex gap-3">
                    {verify.policy.ok && verify.validator.ok ? <CheckCircle2 className="tick-in mt-0.5 h-5 w-5 shrink-0 text-good" aria-hidden /> : <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-bad" aria-hidden />}
                    <div>
                      <p className="font-medium">Checked twice, without AI</p>
                      <div className="mt-1 flex flex-wrap gap-2">
                        <Badge tone={verify.policy.ok ? "good" : "bad"}>Rules {verify.policy.ok ? "pass" : "fail"}</Badge>
                        <Badge tone={verify.validator.ok ? "good" : "bad"}>Independent check {verify.validator.ok ? "passes" : "fails"}</Badge>
                      </div>
                    </div>
                  </li>
                )}
              </ol>
            )}
          </Card>
        </div>
      )}

      {proposals.length > 0 && (
        <div ref={proposalBox} className="mt-8 scroll-mt-24 space-y-5">
          <h2 className="text-2xl font-semibold tracking-tight">Your request is ready to review</h2>
          {proposals.map((proposal, index) => (
            <ProposalCard key={`${proposal.title}-${index}`} proposal={proposal} onDiscard={() => setProposals((current) => current.filter((_, i) => i !== index))} />
          ))}
        </div>
      )}
      {finished && proposals.length === 0 && !clarify && started && (
        <div className="mt-6">
          <Notice tone="info">Nothing was booked or changed. When a request is prepared you decide whether to submit it.</Notice>
        </div>
      )}
    </>
  );
}
