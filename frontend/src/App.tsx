import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import { AgentLanes } from './components/AgentLanes'
import { EventStream } from './components/EventStream'
import { Ledger } from './components/Ledger'
import { TicketRail } from './components/TicketRail'
import { VerdictCard } from './components/VerdictCard'
import type { AgentEvent, Approval, ApproveResponse, Cash, RunResponse, Ticket } from './types'

/** Append only events we have not already shown.
 *  Two pollers can overlap — React StrictMode mounts effects twice in dev, and
 *  the final sweep after a run can race the last interval tick — so merging has
 *  to be idempotent or the per-agent step counts double. */
function mergeEvents(prev: AgentEvent[], incoming: AgentEvent[]): AgentEvent[] {
  if (!incoming.length) return prev
  const seen = new Set(prev.map((e) => e.id))
  const fresh = incoming.filter((e) => !seen.has(e.id))
  return fresh.length ? [...prev, ...fresh] : prev
}

const money = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 0 })

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [shopDate, setShopDate] = useState('')
  const [selected, setSelected] = useState<number | null>(null)
  const [runningId, setRunningId] = useState<number | null>(null)
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [run, setRun] = useState<RunResponse | null>(null)
  const [cash, setCash] = useState<Cash | null>(null)
  const [approvals, setApprovals] = useState<Approval[]>([])
  const [approver, setApprover] = useState('')
  const [busyId, setBusyId] = useState<number | null>(null)
  const [lastResult, setLastResult] = useState<ApproveResponse | null>(null)
  const [dropped, setDropped] = useState(false)
  const [toast, setToast] = useState<{ text: string; bad?: boolean } | null>(null)

  const lastEventId = useRef(-1)
  const prevBalance = useRef<number | null>(null)
  // Mirrors runningId for effects that must not re-fire when a run ends.
  const runningRef = useRef<number | null>(null)

  const say = useCallback((text: string, bad = false) => {
    setToast({ text, bad })
    setTimeout(() => setToast(null), 5200)
  }, [])

  const loadBoard = useCallback(async () => {
    const [t, c, a] = await Promise.all([api.tickets(), api.cash(), api.approvals('all')])
    setTickets(t.tickets)
    setShopDate(t.shop_date)
    setApprovals(a.approvals)
    // Flash the balance only when it actually fell.
    if (prevBalance.current !== null && c.balance < prevBalance.current) {
      setDropped(true)
      setTimeout(() => setDropped(false), 950)
    }
    prevBalance.current = c.balance
    setCash(c)
  }, [])

  useEffect(() => {
    loadBoard().catch((e) => say(`Can't reach the backend on :8000 — ${e.message}`, true))
  }, [loadBoard, say])

  // Select the first ticket once the board arrives.
  useEffect(() => {
    if (selected === null && tickets.length) setSelected(tickets[tickets.length - 1].id)
  }, [tickets, selected])

  // Show the history of whichever ticket is selected, even before a new run.
  // Keyed on `selected` alone: when a run finishes, runningId drops back to null
  // and this must not fire, or it would wipe the verdict the run just produced.
  useEffect(() => {
    if (selected === null || runningRef.current !== null) return
    lastEventId.current = -1
    setRun(null)
    api.events(selected, -1)
      .then((r) => {
        // The trail holds every run this ticket has ever had. Show only the most
        // recent one, or the lanes would count steps from runs long since reset.
        const latest = r.events.length ? r.events[r.events.length - 1].run_id : null
        setEvents(latest ? r.events.filter((e) => e.run_id === latest) : [])
        lastEventId.current = r.last_id
      })
      .catch(() => setEvents([]))
  }, [selected])

  // While a run is in flight, poll for new steps so the floor fills in live.
  useEffect(() => {
    if (runningId === null) return
    const timer = setInterval(async () => {
      try {
        const r = await api.events(runningId, lastEventId.current)
        if (r.events.length) {
          lastEventId.current = Math.max(lastEventId.current, r.last_id)
          setEvents((prev) => mergeEvents(prev, r.events))
        }
      } catch { /* the run itself will report a real failure */ }
    }, 1200)
    return () => clearInterval(timer)
  }, [runningId])

  async function startRun() {
    if (selected === null) return
    setEvents([])
    setRun(null)
    lastEventId.current = -1
    runningRef.current = selected
    setRunningId(selected)
    try {
      const result = await api.runTicket(selected)
      setRun(result)
      say(`Ticket #${selected}: ${result.verdict.disposition.replace(/_/g, ' ')}`)
    } catch (e) {
      say(`Run failed — ${(e as Error).message}`, true)
    } finally {
      runningRef.current = null
      setRunningId(null)
      // Final sweep so no trailing step is missed, then refresh the board.
      if (selected !== null) {
        try {
          const r = await api.events(selected, lastEventId.current)
          setEvents((prev) => mergeEvents(prev, r.events))
        } catch { /* ignore */ }
      }
      await loadBoard()
    }
  }

  async function decide(id: number, decision: 'approved' | 'rejected') {
    setBusyId(id)
    try {
      const result = await api.approve(id, approver.trim(), decision)
      setLastResult(result)
      if (decision === 'rejected') say(`Approval #${id} rejected.`)
      else if (result.money_moved) {
        say(`Paid. Checking is now ${money(result.balance_after)}.`)
      } else {
        say(result.payment?.message ?? 'Approved, but no money moved.', true)
      }
      await loadBoard()
    } catch (e) {
      say((e as Error).message, true)
    } finally {
      setBusyId(null)
    }
  }

  async function resetShop() {
    try {
      await api.reset()
      setEvents([]); setRun(null); setLastResult(null)
      lastEventId.current = -1
      prevBalance.current = null
      await loadBoard()
      say('Shop reset to its original values. The audit trail was kept.')
    } catch (e) {
      say((e as Error).message, true)
    }
  }

  const ticket = tickets.find((t) => t.id === selected) ?? null
  const pending = approvals.filter((a) => a.status === 'pending').length

  return (
    <div className="desk">
      <header className="topbar">
        <div className="brand">
          <h1>Campus Customs</h1>
          <span className="tag">Operations Desk</span>
        </div>
        <div className="spacer" />
        <div className="stat"><div className="k">Shop date</div><div className="v">{shopDate || '—'}</div></div>
        <div className="stat"><div className="k">Checking</div><div className="v">{cash ? money(cash.balance) : '—'}</div></div>
        <div className="stat"><div className="k">Awaiting you</div><div className="v">{pending}</div></div>
        <button className="ghost" onClick={resetShop} disabled={runningId !== null}>Reset shop</button>
      </header>

      <div className="columns">
        <TicketRail tickets={tickets} selected={selected} runningId={runningId} onSelect={setSelected} />

        <main className="floor">
          <div className="floor-head">
            <div>
              <h2>{ticket ? ticket.subject : 'Pick a ticket'}</h2>
              <div className="meta">
                {ticket
                  ? <>#{ticket.id} · {ticket.type.replace(/_/g, ' ')} · {ticket.requester}{ticket.notes ? ` — ${ticket.notes.split('\n')[0]}` : ''}</>
                  : 'Choose one from the board on the left.'}
              </div>
            </div>
            <div className="spacer" />
            <button className="run-btn" onClick={startRun} disabled={runningId !== null || selected === null}>
              {runningId !== null ? 'Team at work…' : 'Send the team in'}
            </button>
          </div>

          <AgentLanes events={events} running={runningId !== null} />

          {run && <VerdictCard run={run} events={events} />}

          <div className="stream-head">
            <h3>The floor</h3>
            {runningId !== null && <span className="live"><span className="dot" />live</span>}
          </div>
          <EventStream events={events} running={runningId !== null} />
        </main>

        <Ledger
          cash={cash}
          approvals={approvals}
          approver={approver}
          dropped={dropped}
          busyId={busyId}
          lastResult={lastResult}
          onApprover={setApprover}
          onDecide={decide}
        />
      </div>

      {toast && <div className={`toast${toast.bad ? ' bad' : ''}`}>{toast.text}</div>}
    </div>
  )
}
