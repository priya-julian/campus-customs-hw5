import { ROLES } from '../roles'
import type { AgentEvent, AgentReport, Role, RunResponse } from '../types'

const DISPOSITION: Record<string, { cls: string; text: string }> = {
  resolved: { cls: 'resolved', text: 'Resolved' },
  waiting_approval: { cls: 'waiting', text: 'Waiting on your approval' },
  blocked: { cls: 'blocked', text: 'Blocked' },
  needs_human: { cls: 'human', text: 'Needs a person' },
}

/** One line per agent: what each of them actually contributed to this ticket. */
function recap(events: AgentEvent[]) {
  const out: { role: Role; summary: string }[] = []
  for (const e of events) {
    if (e.kind !== 'end' || e.agent === 'boss') continue
    try {
      const report = JSON.parse(e.said) as AgentReport
      out.push({ role: e.agent, summary: report.summary })
    } catch {
      const m = e.said.match(/summary='([^']*)'/)
      if (m) out.push({ role: e.agent, summary: m[1] })
    }
  }
  // Keep the last report per agent — an agent asked twice should read once.
  const seen = new Map<Role, string>()
  out.forEach((o) => seen.set(o.role, o.summary))
  return [...seen.entries()].map(([role, summary]) => ({ role, summary }))
}

export function VerdictCard({ run, events }: { run: RunResponse; events: AgentEvent[] }) {
  const v = run.verdict
  const d = DISPOSITION[v.disposition] ?? DISPOSITION.needs_human
  const perAgent = recap(events)

  return (
    <div className="verdict">
      <div className="vh">
        <h3>Ticket #{v.ticket_id} — the Boss's call</h3>
        <span className={`badge ${d.cls}`}>{d.text}</span>
        <span style={{ marginLeft: 'auto', fontSize: 12.5, opacity: .85 }}>
          {run.delegations.length} hand-off{run.delegations.length === 1 ? '' : 's'} ·{' '}
          {run.usage.requests ?? 0} model calls
        </span>
      </div>

      <div className="vb">
        <div className="reason">{v.reasoning}</div>

        {perAgent.length > 0 && (
          <>
            <h5>What each agent did</h5>
            <div className="recap">
              {perAgent.map(({ role, summary }) => (
                <div className="r" key={role}>
                  <div className="av" style={{ background: ROLES[role].hue }}>{ROLES[role].mono}</div>
                  <div>
                    <div className="nm" style={{ color: ROLES[role].hue }}>{ROLES[role].label}</div>
                    <div className="sm">{summary}</div>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        <div className="grid" style={{ marginTop: 18 }}>
          {v.actions_taken.length > 0 && (
            <div>
              <h5>Actions taken</h5>
              <ul>{v.actions_taken.map((a, i) => <li key={i}>{a}</li>)}</ul>
            </div>
          )}
          {run.delegations.length > 0 && (
            <div>
              <h5>Who asked whom</h5>
              <ul>
                {run.delegations.map((g, i) => (
                  <li key={i}>
                    <strong style={{ color: ROLES[g.from_role].hue }}>{ROLES[g.from_role].short}</strong>
                    {' → '}
                    <strong style={{ color: ROLES[g.to_role].hue }}>{ROLES[g.to_role].short}</strong>
                    {g.depth >= 2 && <span style={{ color: 'var(--ink-soft)' }}> · direct, not via Boss</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {v.approvals_requested.length > 0 && (
            <div>
              <h5>Prepared for you</h5>
              <ul>
                {v.approvals_requested.map((id) => (
                  <li key={id}>Approval #{id} — see the Ledger on the right</li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {v.next_step_for_human && (
          <div className="next"><strong>Your move:</strong> {v.next_step_for_human}</div>
        )}
      </div>
    </div>
  )
}
