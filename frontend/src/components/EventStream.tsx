import { useEffect, useRef } from 'react'
import { ROLES, prettyTool } from '../roles'
import type { AgentEvent, AgentReport } from '../types'

/** Tools that change the shop get a different chip from tools that only read. */
const WRITE_TOOLS = ['update_ticket', 'adjust_inventory', 'save_draft_message', 'request_approval']
const MONEY_TOOLS = ['pay_invoice', 'pay_rent', 'record_human_decision']

function chipClass(tool: string) {
  const bare = tool.replace(/^campus-customs_/, '')
  if (MONEY_TOOLS.includes(bare)) return 'tool-chip money'
  if (WRITE_TOOLS.includes(bare)) return 'tool-chip write'
  return 'tool-chip'
}

/** An agent's closing report is stored as JSON; show its summary, not the blob. */
function readSummary(said: string): string {
  try {
    const parsed = JSON.parse(said) as Partial<AgentReport> & { reasoning?: string }
    return parsed.summary ?? parsed.reasoning ?? said
  } catch {
    const match = said.match(/summary='([^']*)'/) ?? said.match(/reasoning='([^']*)'/)
    return match ? match[1] : said
  }
}

/** Only the steps a person would want to watch. The model-request bookkeeping
 *  nodes are real loop steps but say nothing a human needs. */
const SHOWN = ['model_response', 'delegation', 'end', 'run_started', 'run_finished', 'error']

export function EventStream({ events, running }: { events: AgentEvent[]; running: boolean }) {
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (running) endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [events.length, running])

  const shown = events.filter(
    (e) => SHOWN.includes(e.kind) && (e.said?.trim() || e.tools_used.length || e.kind === 'delegation'),
  )

  if (!shown.length) {
    return (
      <div className="empty">
        Nothing yet. Pick a ticket and send the team in — every step they take shows up here.
      </div>
    )
  }

  return (
    <div className="stream">
      {shown.map((e) => {
        const style = ROLES[e.agent] ?? ROLES.boss
        const tools = e.tools_used.filter((t) => t.tool !== 'final_result')
        const isHandoff = e.kind === 'delegation'
        const text =
          e.kind === 'end' ? readSummary(e.said)
          : e.kind === 'run_finished' ? readSummary(e.said)
          : e.said

        if (e.kind === 'model_response' && !text.trim() && !tools.length) return null

        return (
          <div
            key={e.id}
            className={`ev${isHandoff ? ' handoff' : ''}${e.depth === 1 ? ' indent' : e.depth >= 2 ? ' indent2' : ''}`}
            style={{ color: style.hue }}
          >
            <div className="av" style={{ background: style.hue }}>{style.mono}</div>
            <div>
              <div className="hd">
                <span className="who">{style.label}</span>
                <span className="kind">
                  {e.kind === 'end' ? 'reported back'
                    : e.kind === 'delegation' ? 'hand-off'
                    : e.kind === 'run_started' ? 'run started'
                    : e.kind === 'run_finished' ? 'final call'
                    : e.kind === 'error' ? 'error'
                    : 'working'}
                </span>
                {e.parent_agent && e.kind !== 'delegation' && (
                  <span className="hop">asked by {ROLES[e.parent_agent]?.label ?? e.parent_agent}</span>
                )}
              </div>
              {text?.trim() && <div className="txt">{text}</div>}
              {tools.length > 0 && (
                <div className="tools">
                  {tools.map((t, i) => (
                    <span key={i} className={chipClass(t.tool)} title={JSON.stringify(t.args)}>
                      {prettyTool(t.tool)}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        )
      })}
      <div ref={endRef} />
    </div>
  )
}
