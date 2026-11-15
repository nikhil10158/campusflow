import type { Alternative, Proposal, ProposalComponent, Violation } from "./types";

export interface CheckResponse {
  ok: boolean;
  state: string;
  violations: Violation[];
  conflicts: string[];
  approval_chain: string[];
  alternatives: Alternative[];
}

export interface BookingBody {
  resource_type: "venue" | "guest_room" | "parking";
  resource_id: number;
  start: string;
  end: string;
  event_title: string;
  attendees: number;
  qty?: number;
  sponsor_id?: number | null;
  host_ref?: string | null;
  meta?: Record<string, unknown>;
}

export function proposalFromCheck(check: CheckResponse, body: BookingBody, label: string): Proposal {
  const component: ProposalComponent = {
    resource_type: body.resource_type,
    label,
    title: body.event_title,
    start: body.start,
    end: body.end,
    ok: check.ok,
    state: check.state,
    violations: check.violations,
    conflicts: check.conflicts,
    approval_chain: check.approval_chain,
  };
  const hard = check.violations.filter((violation) => violation.severity === "hard");
  return {
    kind: "booking",
    title: body.event_title,
    ok: check.ok,
    view: { title: body.event_title, ok: check.ok, components: [component], bundle_violations: [], suggestions: [], alternatives: check.alternatives },
    submit: { endpoint: "/bookings", body: body as unknown as Record<string, unknown> },
    verification: { policy: { ok: hard.length === 0, violations: hard }, validator: { ok: check.conflicts.length === 0, violations: [] } },
  };
}
