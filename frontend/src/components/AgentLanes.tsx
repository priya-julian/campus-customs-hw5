import { ROLES, ROLE_ORDER } from '../roles'
import type { AgentEvent, Role } from '../types'

/** Five lanes, one per agent, always visible.
 *
 * Showing all five even when four are idle is the point: the board should make
 * it obvious *who was not needed*, because a ticket that pulls every specialist
 * is a routing failure worth seeing.
 */
export function AgentLanes({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const lastAgent = events.length ? events[events.length - 1].agent : null

  return (
    <div className="lanes">
      {ROLE_ORDER.map((role: Role) => {
        const style = ROLES[role]
        const mine = events.filter((e) => e.agent === role)
        const toolCount = mine.reduce((n, e) => n + e.tools_used.filter((t) => t.tool !== 'final_result').length, 0)
        const active = running && lastAgent === role
        const touched = mine.length > 0
        const cls = active ? 'active' : touched ? 'done' : 'idle'

        return (
          <div key={role} className={`lane ${cls}`} style={{ color: style.hue }}>
            <div className="cap" />
            <div className="top">
              <div className="mono-badge" style={{ background: style.hue }}>{style.mono}</div>
              <div className="nm">{style.label}</div>
              {active && <span className="pulse" />}
            </div>
            <div className="job">{style.job}</div>
            <div className="counts">
              <span><b>{mine.length}</b> steps</span>
              <span><b>{toolCount}</b> tools</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}
