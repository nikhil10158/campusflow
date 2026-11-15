"use client";

import { Bot, CheckCircle2, Loader2, Mic, Send, Sparkles, User, XCircle } from "lucide-react";
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
    bottom.current?.scrollIntoView({ behavior: "smooth" });
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
      await streamAgent(clarification ? original : text, clarification ? { original, answer, field: clarification.field } : null, (event) => {
        if (event.type === "plan") setPlan(event.steps);
        else if (event.type === "plan_progress") setDone(event.done);
        else if (event.type === "tool_call") setSteps((current) => [...current, { id: event.id, name: event.name, args: event.args, rationale: event.rationale }]);
        else if (event.type === "tool_result") setSteps((current) => current.map((step) => (step.id === event.id ? { ...step, summary: event.summary, latency: event.latency_ms, error: event.error } : step)));
        else if (event.type === "verify") setVerify(event);
        else if (event.type === "proposal") setProposals((current) => [...current, event.proposal]);
        else if (event.type === "clarify") setClarify({ question: event.question, options: event.options, field: event.field, original });
        else if (event.type === "refusal") setMessages((current) => current);
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

  return (
    <>
      <PageHeader title="Concierge" subtitle="One sentence becomes a validated plan: venue, guest house and parking. The assistant only proposes; you press Submit, and approvers decide." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className="flex h-[70vh] flex-col" title={<span className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-primary" /> Ask for anything</span>}>
          <div className="flex-1 space-y-3 overflow-y-auto pr-1" aria-live="polite">
            {messages.length === 0 && (
              <div className="space-y-2">
                <p className="text-sm text-muted">Try one of these:</p>
                {EXAMPLES.map((example) => (
                  <button key={example} onClick={() => run(example)} className="block w-full rounded-lg border border-line p-2 text-left text-sm hover:bg-surface2">
                    {example}
                  </button>
                ))}
              </div>
            )}
            {messages.map((message, index) => (
              <div key={index} className={cx("flex gap-2", message.role === "user" && "justify-end")}>
                {message.role === "assistant" && <Bot className="mt-1 h-4 w-4 shrink-0 text-primary" aria-hidden />}
                <div className={cx("max-w-[85%] whitespace-pre-wrap rounded-xl px-3 py-2 text-sm", message.role === "user" ? "bg-primary text-primaryink" : "bg-surface2")}>
                  {message.text || (busy && index === messages.length - 1 ? <Loader2 className="h-4 w-4 animate-spin" aria-label="Thinking" /> : "")}
                </div>
                {message.role === "user" && <User className="mt-1 h-4 w-4 shrink-0 text-muted" aria-hidden />}
              </div>
            ))}
            {clarify && (
              <div className="rounded-xl border border-primary/40 p-3">
                <p className="mb-2 text-sm font-medium">{clarify.question}</p>
                <div className="flex flex-wrap gap-2">
                  {clarify.options.map((option) => (
                    <button key={option} onClick={() => run(clarify.original, clarify, option)} className="rounded-full border border-line px-3 py-1 text-sm hover:bg-surface2">
                      {option}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div ref={bottom} />
          </div>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              send();
            }}
            className="mt-3 flex gap-2"
          >
            <input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="e.g. free classroom tomorrow 2–4 pm for 60"
              aria-label="Your request"
              className="flex-1 rounded-lg border border-line bg-surface px-3 py-2 text-sm outline-none focus:border-primary focus:ring-2 focus:ring-primary/30"
            />
            <Button type="button" variant="outline" onClick={listen} aria-label="Voice input" className={cx(listening && "border-primary text-primary")}>
              <Mic className="h-4 w-4" />
            </Button>
            <Button type="submit" busy={busy} aria-label="Send">
              <Send className="h-4 w-4" />
            </Button>
          </form>
        </Card>

        <div className="space-y-4">
          <Card title="Agent run timeline">
            {plan.length === 0 && steps.length === 0 ? (
              <p className="text-sm text-muted">The plan, every tool call and the verification appear here live.</p>
            ) : (
              <div className="space-y-3">
                {plan.length > 0 && (
                  <ol className="space-y-1">
                    {plan.map((step, index) => (
                      <li key={step} className="flex items-center gap-2 text-sm">
                        {finished || index < done ? <CheckCircle2 className="h-4 w-4 text-good" aria-hidden /> : <span className="h-4 w-4 rounded-full border border-line" aria-hidden />}
                        <span className={cx(index < done || finished ? "text-ink" : "text-muted")}>{step}</span>
                      </li>
                    ))}
                  </ol>
                )}
                <ul className="space-y-2">
                  {steps.filter((step) => step.name !== "declare_plan").map((step) => (
                    <li key={step.id} className="rounded-lg border border-line p-2 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono font-medium">{step.name}</span>
                        {step.summary === undefined ? <Loader2 className="h-3 w-3 animate-spin" aria-label="Running" /> : <Badge tone={step.error ? "bad" : "good"}>{step.latency?.toFixed(0)} ms</Badge>}
                      </div>
                      <p className="mt-1 text-muted">{step.rationale}</p>
                      <p className="mt-1 break-all font-mono text-[11px] text-muted">{JSON.stringify(step.args).slice(0, 160)}</p>
                      {step.summary && <p className={cx("mt-1", step.error && "text-bad")}>→ {step.summary}</p>}
                    </li>
                  ))}
                </ul>
                {verify && (
                  <div className="flex flex-wrap gap-2 text-xs">
                    <Badge tone={verify.policy.ok ? "good" : "bad"}>
                      {verify.policy.ok ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />} policy engine
                    </Badge>
                    <Badge tone={verify.validator.ok ? "good" : "bad"}>
                      {verify.validator.ok ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />} independent validator
                    </Badge>
                  </div>
                )}
              </div>
            )}
          </Card>
          {proposals.map((proposal, index) => (
            <ProposalCard key={`${proposal.title}-${index}`} proposal={proposal} onDiscard={() => setProposals((current) => current.filter((_, i) => i !== index))} />
          ))}
          {finished && proposals.length === 0 && !clarify && messages.length > 0 && (
            <Notice tone="info">No state was changed. When a proposal appears you decide whether to submit it.</Notice>
          )}
        </div>
      </div>
    </>
  );
}
