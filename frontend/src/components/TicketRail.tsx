import type { Ticket } from '../types'

/** Status words from the backend, mapped to the badge that reads fastest. */
function badgeFor(status: string) {
  if (status === 'resolved') return { cls: 'resolved', text: 'Resolved' }
  if (status === 'waiting_approval') return { cls: 'waiting', text: 'Awaiting you' }
  if (status === 'blocked') return { cls: 'blocked', text: 'Blocked' }
  if (status === 'needs_human') return { cls: 'human', text: 'Needs a person' }
  return { cls: 'open', text: 'Open' }
}

interface Props {
  tickets: Ticket[]
  selected: number | null
  runningId: number | null
  onSelect: (id: number) => void
}

export function TicketRail({ tickets, selected, runningId, onSelect }: Props) {
  return (
    <aside className="rail">
      <div className="rail-title">The Board · {tickets.length} tickets</div>
      {tickets.map((t) => {
        const badge = badgeFor(t.status)
        const running = runningId === t.id
        return (
          <button
            key={t.id}
            className={`ticket${selected === t.id ? ' sel' : ''}${t.is_resolved ? ' done' : ''}`}
            onClick={() => onSelect(t.id)}
          >
            <div className="row">
              <span className="num">#{t.id}</span>
              <span className="kind">{t.type.replace(/_/g, ' ')}</span>
              <span style={{ marginLeft: 'auto' }} className={`badge ${badge.cls}`}>{badge.text}</span>
            </div>
            <div className="subj">{t.subject}</div>
            <div className="who">
              {t.requester}
              {t.sku ? ` · ${t.sku}${t.size ? ` / ${t.size}` : ''}${t.qty ? ` × ${t.qty}` : ''}` : ''}
            </div>
            {running && (
              <div className="running">
                <span className="dot" style={{ width: 7, height: 7, borderRadius: '50%', background: 'currentColor', display: 'inline-block' }} />
                team working…
              </div>
            )}
          </button>
        )
      })}
    </aside>
  )
}
