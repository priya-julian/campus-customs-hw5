/** Shapes returned by the Campus Customs backend (see backend/main.py). */

export type Role = 'boss' | 'inventory' | 'accounting' | 'facilities' | 'customer_service'

export interface Ticket {
  id: number
  type: string
  requester: string
  subject: string
  sku: string | null
  size: string | null
  qty: number | null
  lease_id: number | null
  invoice_id: number | null
  status: string
  notes: string | null
  created_at: string
  is_open: boolean
  is_resolved: boolean
}

export interface TicketsResponse {
  shop_date: string
  count: number
  open_count: number
  resolved_count: number
  tickets: Ticket[]
}

export interface ToolUse {
  tool: string
  args: Record<string, unknown>
}

export interface AgentEvent {
  id: number
  run_id: string
  ts: string
  shop_date: string | null
  ticket_id: number | null
  agent: Role
  parent_agent: Role | null
  depth: number
  kind: string
  said: string
  tools_used: ToolUse[]
  tool_results: { tool: string; result: string }[]
  usage: Record<string, number>
  note: string
}

export interface EventsResponse {
  count: number
  total_events: number
  last_id: number
  events: AgentEvent[]
}

export interface Verdict {
  ticket_id: number
  disposition: 'resolved' | 'waiting_approval' | 'blocked' | 'needs_human'
  reasoning: string
  consulted: Role[]
  actions_taken: string[]
  approvals_requested: number[]
  customer_message_drafted: boolean
  next_step_for_human: string
}

export interface Delegation {
  from_role: Role
  to_role: Role
  question: string
  depth: number
  answer_summary: string
}

export interface RunResponse {
  run_id: string
  ticket_id: number
  verdict: Verdict
  delegations: Delegation[]
  usage: Record<string, number>
}

export interface Approval {
  id: number
  ticket_id: number | null
  kind: 'invoice_payment' | 'rent_payment' | 'purchase_order' | 'price_override'
  subject: string
  amount: number | null
  account: string | null
  ref_table: string | null
  ref_id: number | null
  rationale: string
  requested_by: Role
  requested_at: string
  status: 'pending' | 'approved' | 'rejected' | 'executed'
  decided_by: string | null
  decided_at: string | null
  decision_note: string | null
}

export interface Cash {
  account: string
  balance: number
  as_of: string
  shop_today: string
  total_requested_not_yet_paid: number
  balance_if_all_paid: number
  payments_made: number
  total_paid: number
}

export interface ApproveResponse {
  approval_id: number
  kind: string
  money_moved: boolean
  balance_after: number
  payment: {
    ok: boolean
    refused?: string
    message?: string
    amount?: number
    approved_by?: string
    balance_after?: number
    vendor_unblocked?: string | null
  } | null
}

/** An agent's report, as recorded at the end of its loop. */
export interface AgentReport {
  summary: string
  findings: string[]
  actions_taken: string[]
  approvals_requested: number[]
  open_questions: string[]
}
