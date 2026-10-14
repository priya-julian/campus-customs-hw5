import { useState } from 'react'
import { ROLES } from '../roles'
import type { Approval, ApproveResponse, Cash } from '../types'

const OPENING_BALANCE = 3400

const KIND_LABEL: Record<string, string> = {
  invoice_payment: 'Invoice payment',
  rent_payment: 'Rent payment',
  purchase_order: 'Purchase order',
  price_override: 'Price override',
}

const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })

interface Props {
  cash: Cash | null
  approvals: Approval[]
  approver: string
  dropped: boolean
  busyId: number | null
  lastResult: ApproveResponse | null
  onApprover: (name: string) => void
  onDecide: (id: number, decision: 'approved' | 'rejected') => void
}

export function Ledger({
  cash, approvals, approver, dropped, busyId, lastResult, onApprover, onDecide,
}: Props) {
  const [showHistory, setShowHistory] = useState(false)
  const pending = approvals.filter((a) => a.status === 'pending')
  const settled = approvals.filter((a) => a.status !== 'pending')
  const pct = cash ? Math.max(0, Math.min(100, (cash.balance / OPENING_BALANCE) * 100)) : 100

  return (
    <aside className="ledger">
      <div className="ledger-title">The Ledger</div>

      <div className="cash">
        <div className="k">Checking</div>
        <div className={`amt${dropped ? ' drop' : ''}`}>{cash ? money(cash.balance) : '—'}</div>
        <div className="sub">
          {cash ? `${cash.payments_made} payment${cash.payments_made === 1 ? '' : 's'} made · ${money(cash.total_paid)} out` : 'loading…'}
        </div>
        <div className="meter"><i style={{ width: `${pct}%` }} /></div>
        <div className="legend">
          <span>of {money(OPENING_BALANCE)} opening</span>
          <span>
            {cash && cash.total_requested_not_yet_paid > 0
              ? `${money(cash.total_requested_not_yet_paid)} requested`
              : 'nothing queued'}
          </span>
        </div>
      </div>

      <label className="who-label" htmlFor="approver">Approving as</label>
      <input
        id="approver"
        className="who-input"
        value={approver}
        placeholder="Your name"
        onChange={(e) => onApprover(e.target.value)}
      />

      <div className="ledger-title">
        Awaiting approval {pending.length > 0 && `· ${pending.length}`}
      </div>

      {pending.length === 0 && (
        <div className="empty" style={{ marginBottom: 18 }}>
          Nothing to approve. Agents can prepare payments — only you can release them.
        </div>
      )}

      {pending.map((a) => (
        <div className="appr" key={a.id}>
          <div className="t">
            <span className="amt">{a.amount != null ? money(a.amount) : '—'}</span>
            <span className="kind">{KIND_LABEL[a.kind] ?? a.kind}</span>
          </div>
          <div className="subj">{a.subject}</div>
          <div className="why">{a.rationale}</div>
          <div className="by">
            Prepared by{' '}
            <strong style={{ color: ROLES[a.requested_by]?.hue }}>
              {ROLES[a.requested_by]?.label ?? a.requested_by}
            </strong>
            {a.ticket_id ? ` · ticket #${a.ticket_id}` : ''}
          </div>
          {lastResult && lastResult.approval_id === a.id && !lastResult.money_moved && lastResult.payment && (
            <div className="refused" style={{ marginBottom: 10 }}>{lastResult.payment.message}</div>
          )}
          <div className="acts">
            <button
              className="ok"
              disabled={busyId === a.id || !approver.trim()}
              onClick={() => onDecide(a.id, 'approved')}
              title={!approver.trim() ? 'Put your name in first' : 'Approve and pay'}
            >
              {busyId === a.id ? 'Working…' : 'Approve & pay'}
            </button>
            <button className="no" disabled={busyId === a.id || !approver.trim()} onClick={() => onDecide(a.id, 'rejected')}>
              Reject
            </button>
          </div>
        </div>
      ))}

      {settled.length > 0 && (
        <>
          <div className="ledger-title" style={{ marginTop: 20, cursor: 'pointer' }} onClick={() => setShowHistory((s) => !s)}>
            Decided · {settled.length} {showHistory ? '▾' : '▸'}
          </div>
          {showHistory && settled.map((a) => (
            <div className={`appr ${a.status === 'rejected' ? 'rejected' : 'settled'}`} key={a.id}>
              <div className="t">
                <span className="amt">{a.amount != null ? money(a.amount) : '—'}</span>
                <span className="kind">{KIND_LABEL[a.kind] ?? a.kind}</span>
              </div>
              <div className="subj">{a.subject}</div>
              <div className="done-line" style={a.status === 'rejected' ? { color: 'var(--red)' } : undefined}>
                {a.status === 'executed' ? 'Paid' : a.status === 'approved' ? 'Approved, not paid' : 'Rejected'}
                {a.decided_by ? ` · ${a.decided_by}` : ''}
              </div>
            </div>
          ))}
        </>
      )}
    </aside>
  )
}
