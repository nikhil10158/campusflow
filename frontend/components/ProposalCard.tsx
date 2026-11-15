"use client";

import { AlertTriangle, ArrowRight, CheckCircle2, ShieldCheck, XCircle } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { api, ApiError } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { useToasts } from "@/lib/store";
import type { Alternative, Proposal, ProposalComponent } from "@/lib/types";

import { Badge, Button, Card, CitationList, Notice, cx } from "./ui";

const KIND_LABEL: Record<string, string> = { venue: "Venue", guest_room: "Guest room", parking: "Parking" };

function applyAlternative(proposal: Proposal, alternative: Alternative): Proposal["submit"] {
  const body = { ...proposal.submit.body } as Record<string, unknown>;
  if (alternative.components && Array.isArray(body.components)) {
    const original = body.components as Record<string, unknown>[];
    body.components = alternative.components.map((component, index) => ({ ...original[index], ...component }));
  } else if (alternative.parts && alternative.parts.length) {
    const part = alternative.parts[0];
    body.resource_id = part.resource_id;
    body.start = part.start;
    body.end = part.end;
    if (part.attendees) body.attendees = part.attendees;
  }
  return { endpoint: proposal.submit.endpoint, body };
}

function ComponentRow({ component }: { component: ProposalComponent }) {
  return (
    <li className="rounded-lg border border-line p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          {component.ok ? <CheckCircle2 className="h-4 w-4 text-good" aria-hidden /> : <XCircle className="h-4 w-4 text-bad" aria-hidden />}
          {KIND_LABEL[component.resource_type] ?? component.resource_type}: {component.label || "—"}
        </div>
        <span className="text-xs text-muted">
          {fmtDateTime(component.start)} → {fmtDateTime(component.end)}
        </span>
      </div>
      {component.violations.map((violation) => (
        <p key={violation.code + violation.message} className={cx("mt-1 text-xs", violation.severity === "hard" ? "text-bad" : "text-warn")}>
          {violation.message} <Badge tone="info">{violation.rule_id}</Badge>
        </p>
      ))}
      {component.conflicts?.map((conflict) => (
        <p key={conflict} className="mt-1 text-xs text-bad">
          {conflict}
        </p>
      ))}
      {component.approval_chain?.length > 0 && (
        <p className="mt-2 flex flex-wrap items-center gap-1 text-xs text-muted">
          Approvals:
          {component.approval_chain.map((scope, index) => (
            <span key={scope} className="inline-flex items-center gap-1">
              <Badge>{scope}</Badge>
              {index < component.approval_chain.length - 1 && <ArrowRight className="h-3 w-3" aria-hidden />}
            </span>
          ))}
        </p>
      )}
    </li>
  );
}

export function ProposalCard({ proposal: initial, onDiscard }: { proposal: Proposal; onDiscard?: () => void }) {
  const [submit, setSubmit] = useState(initial.submit);
  const [applied, setApplied] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ link: string; text: string } | null>(null);
  const [error, setError] = useState<{ message: string; alternatives?: Alternative[] } | null>(null);
  const toast = useToasts((state) => state.push);
  const view = initial.view;
  const canSubmit = initial.kind !== "rehome" ? (initial.ok || applied !== null) : true;

  async function send() {
    setBusy(true);
    setError(null);
    try {
      const response = await api<Record<string, unknown>>(submit.endpoint, { body: submit.body });
      if (initial.kind === "bundle") setResult({ link: `/bundles/${response.id}`, text: "Bundle held — open the saga board to follow approvals." });
      else if (initial.kind === "rehome") setResult({ link: `/admin/disruptions?id=${response.disruption_id}`, text: "Assessment saved — review and submit it in the Disruption Center." });
      else if (initial.kind === "release") setResult({ link: "/faculty", text: "Release proposed. The head of department must approve it." });
      else setResult({ link: "/approvals", text: "Request submitted and held. Approvers have been notified (mock)." });
      toast("good", "Submitted for approval");
    } catch (problem) {
      const failure = problem as ApiError;
      const data = failure.data ?? {};
      const alternatives = (data.alternatives as Alternative[] | undefined) ?? [];
      setError({ message: failure.message, alternatives });
      toast("bad", failure.message);
    } finally {
      setBusy(false);
    }
  }

  const alternatives = error?.alternatives?.length ? error.alternatives : view.alternatives;
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          Proposal: {initial.title} {initial.ok ? <Badge tone="good">valid</Badge> : <Badge tone="bad">needs changes</Badge>}
        </span>
      }
    >
      {initial.kind === "rehome" || initial.kind === "release" ? (
        <pre className="max-h-48 overflow-auto rounded-lg bg-surface2 p-3 text-xs">{JSON.stringify(initial.kind === "rehome" ? { affected: view.affected, resolved: view.resolved, unresolved: view.unresolved } : view, null, 2)}</pre>
      ) : (
        <ul className="space-y-2">
          {view.components.map((component, index) => (
            <ComponentRow key={index} component={component} />
          ))}
        </ul>
      )}
      {view.bundle_violations?.map((violation) => (
        <p key={violation.message} className="mt-2 text-xs text-bad">
          {violation.message} <Badge tone="info">{violation.rule_id}</Badge>
        </p>
      ))}
      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        <Badge tone={initial.verification.policy.ok ? "good" : "bad"}>
          <ShieldCheck className="h-3 w-3" aria-hidden /> policy {initial.verification.policy.ok ? "✓" : "✗"}
        </Badge>
        <Badge tone={initial.verification.validator.ok ? "good" : "bad"}>
          <ShieldCheck className="h-3 w-3" aria-hidden /> independent validator {initial.verification.validator.ok ? "✓" : "✗"}
        </Badge>
      </div>
      {view.suggestions?.length > 0 && (
        <div className="mt-3 space-y-1">
          {view.suggestions.map((suggestion) => (
            <Notice key={suggestion.reason} tone="info">
              Suggested: {suggestion.reason} <Badge tone="info">{suggestion.rule_id}</Badge>
            </Notice>
          ))}
        </div>
      )}
      {alternatives?.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Ranked alternatives</h3>
          <ol className="space-y-2">
            {alternatives.map((alternative, index) => (
              <li key={index} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line p-2 text-sm">
                <div>
                  <div>{alternative.what_changed}</div>
                  <div className="mt-1 flex items-center gap-2 text-xs text-muted">
                    cost {alternative.cost} <CitationList citations={alternative.citations} />
                  </div>
                </div>
                <Button
                  variant={applied === alternative.what_changed ? "primary" : "outline"}
                  onClick={() => {
                    setSubmit(applyAlternative(initial, alternative));
                    setApplied(alternative.what_changed);
                    setError(null);
                  }}
                >
                  {applied === alternative.what_changed ? "Selected" : "Use this"}
                </Button>
              </li>
            ))}
          </ol>
        </div>
      )}
      {error && (
        <div className="mt-3">
          <Notice tone="bad">{error.message}</Notice>
        </div>
      )}
      {result ? (
        <div className="mt-4 flex items-center justify-between gap-2 rounded-lg bg-goodbg p-3 text-sm text-good">
          <span>{result.text}</span>
          <Link href={result.link} className="font-medium underline">
            Open
          </Link>
        </div>
      ) : (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button onClick={send} busy={busy} disabled={!canSubmit}>
            {initial.kind === "rehome" ? "Save assessment" : initial.kind === "release" ? "Propose release" : "Submit request"}
          </Button>
          <Button variant="ghost" onClick={onDiscard}>
            Discard
          </Button>
          {!canSubmit && (
            <span className="flex items-center gap-1 text-xs text-warn">
              <AlertTriangle className="h-3 w-3" aria-hidden /> Fix the problems or pick an alternative first
            </span>
          )}
          {applied && <span className="text-xs text-muted">Alternative selected; it is re-validated when you submit.</span>}
        </div>
      )}
    </Card>
  );
}
