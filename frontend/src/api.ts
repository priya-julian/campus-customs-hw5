/** Thin client for the FastAPI backend on :8000.
 *
 * Every call goes to the backend, which in turn goes to the MCP server. The
 * dashboard never touches the shop database, so the guardrails behind those
 * tools apply to a click here exactly as they apply to an agent.
 */
import type {
  Approval, ApproveResponse, Cash, EventsResponse, RunResponse, TicketsResponse,
} from './types'

const BASE = 'http://localhost:8000'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(detail.detail ?? `${res.status}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  tickets: () => get<TicketsResponse>('/tickets'),
  cash: () => get<Cash>('/cash'),
  approvals: (status = 'all') => get<{ approvals: Approval[] }>(`/approvals?status=${status}`),
  events: (ticketId: number, afterId: number) =>
    get<EventsResponse>(`/events?ticket_id=${ticketId}&after_id=${afterId}&limit=200`),
  runTicket: (id: number) => post<RunResponse>(`/tickets/${id}/run`),
  approve: (id: number, decidedBy: string, decision: 'approved' | 'rejected' = 'approved') =>
    post<ApproveResponse>(`/approvals/${id}/approve`, { decided_by: decidedBy, decision }),
  reset: () => post<{ reset: boolean; balance: number }>('/reset'),
}
