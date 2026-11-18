export interface Venue {
  id: number;
  code: string;
  name: string;
  type: "classroom" | "seminar_hall" | "lab" | "amphitheatre";
  building_id: number;
  floor: number;
  capacity: number;
  features: string[];
  lab_type: string | null;
  eligible_depts: string[];
  needs_supervisor: boolean;
  accessible: boolean;
  setup_buffer_min: number;
  teardown_buffer_min: number;
  approver_scope: string;
}

export interface Building {
  id: number;
  name: string;
  x: number;
  y: number;
  zone: string;
}

export interface Section {
  id: number;
  dept: string;
  semester: number;
  name: string;
  size: number;
}

export interface Violation {
  code: string;
  rule_id: string;
  severity: "hard" | "soft";
  message: string;
  fixable_by: string;
}

export interface RoomHit {
  venue_id: number;
  code: string;
  name: string;
  type: string;
  building_id: number;
  capacity: number;
  features: string[];
  state: "FREE" | "FREE_RELEASED";
  score: number;
  reasons: string[];
  walking_min: number | null;
  warnings: Violation[];
}

export interface WhyNot {
  venue: string;
  reason: string;
  layer: string | null;
  ghost: boolean;
}

export interface SearchResult {
  windows: string[][];
  hits: RoomHit[];
  why_not: WhyNot[];
  considered: number;
}

export interface Segment {
  start_slot: number;
  end_slot: number;
  time: string;
  layer: "timetable" | "confirmed" | "held" | "maintenance";
  label: string;
  ghost: boolean;
}

export interface DayVenue {
  id: number;
  code: string;
  type: string;
  capacity: number;
  building_id: number;
  segments: Segment[];
  released_slots: number[];
}

export interface Alternative {
  what_changed: string;
  cost: number;
  citations: string[];
  parts?: { resource_type: string; resource_id: number; resource_code: string; start: string; end: string; attendees: number }[];
  components?: { resource_type: string; resource_id: number; start: string; end: string; qty: number; attendees: number; meta: Record<string, unknown> }[];
  approval_chain?: string[];
}

export interface ProposalComponent {
  resource_type: string;
  label: string;
  title?: string;
  start: string;
  end: string;
  ok: boolean;
  state?: string;
  violations: Violation[];
  conflicts: string[];
  approval_chain: string[];
}

export interface ProposalView {
  title: string;
  ok: boolean;
  components: ProposalComponent[];
  bundle_violations: Violation[];
  suggestions: { resource: string; reason: string; rule_id: string }[];
  alternatives: Alternative[];
}

export interface Proposal {
  kind: "booking" | "bundle" | "release" | "rehome";
  title: string;
  ok: boolean;
  view: ProposalView & Record<string, unknown>;
  submit: { endpoint: string; body: Record<string, unknown> };
  verification: { policy: { ok: boolean; violations: Violation[] }; validator: { ok: boolean; violations: Violation[] } };
}

export interface Step {
  id: number;
  order: number;
  scope: string;
  status: string;
  comment: string;
  decided_at: string | null;
}

export interface Booking {
  id: number;
  bundle_id: number | null;
  resource_type: string;
  resource_id: number;
  start: string;
  end: string;
  status: string;
  event_title: string;
  attendees: number | null;
  qty: number;
  requester_id: number | null;
  hold_expires_at: string | null;
  meta: Record<string, unknown>;
  steps: Step[];
  track?: { status: string; label: string };
}

export interface ApprovalItem {
  step_id: number;
  scope: string;
  status: string;
  order: number;
  due_at: string | null;
  escalated: boolean;
  booking: Booking;
  still_valid: boolean;
  violations: Violation[];
  conflicts: string[];
  alternatives: Alternative[];
}

export interface AgentStatus {
  mode: "live" | "degraded" | "offline";
  model: string | null;
  calls_today: number;
  remaining_est: number;
  daily_limit: number;
}

export type AgentEvent =
  | { type: "start"; mode: string; role: string }
  | { type: "plan"; steps: string[]; rationale: string }
  | { type: "plan_progress"; done: number }
  | { type: "tool_call"; id: number; name: string; args: Record<string, unknown>; rationale: string }
  | { type: "tool_result"; id: number; name: string; summary: string; latency_ms: number; error: boolean }
  | { type: "verify"; policy: { ok: boolean; violations: Violation[] }; validator: { ok: boolean; violations: Violation[] } }
  | { type: "clarify"; question: string; options: string[]; field: string }
  | { type: "proposal"; proposal: Proposal }
  | { type: "refusal"; reason: string }
  | { type: "answer_delta"; text: string }
  | { type: "done"; mode: string; llm_calls: number; tool_calls: number };

export type { components } from "./schema";
