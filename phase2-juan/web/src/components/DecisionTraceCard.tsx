import type { DecisionTrace } from '../types'

function scalarEntries(state: Record<string, unknown> | null): [string, number][] {
  if (!state) return []
  return Object.entries(state).filter(([, v]) => typeof v === 'number') as [string, number][]
}

function extractQValues(state: Record<string, unknown> | null): Record<string, number> | null {
  if (!state) return null
  for (const key of ['q_values', 'Q', 'q_table']) {
    const val = state[key]
    if (val && typeof val === 'object' && !Array.isArray(val)) {
      const entries = Object.entries(val as Record<string, unknown>).filter(([, v]) => typeof v === 'number')
      if (entries.length > 0) return Object.fromEntries(entries) as Record<string, number>
    }
  }
  return null
}

function formatDelta(pre: number, post: number): { text: string; color: string } {
  const delta = post - pre
  if (Math.abs(delta) < 0.005) return { text: '', color: '' }
  const sign = delta > 0 ? '+' : ''
  return { text: `${sign}${delta.toFixed(1)}`, color: delta > 0 ? '#4ade80' : '#dc2626' }
}

const FILTER_KEYS = ['q_values', 'Q', 'q_table', 'discretized_state', 'previous_state', 'previous_action', 'previous_energy']

interface Props {
  trace: DecisionTrace
}

export function DecisionTraceCard({ trace }: Props) {
  const preScalars = scalarEntries(trace.pre_state).filter(([k]) => !FILTER_KEYS.includes(k))
  const postScalars = scalarEntries(trace.post_state).filter(([k]) => !FILTER_KEYS.includes(k))
  const qValues = extractQValues(trace.pre_state)

  return (
    <div className="font-mono text-[11px] text-text-dim rounded-lg border border-border-subtle p-3.5" style={{ background: '#0f172a' }}>
      {/* Header */}
      <div className="flex justify-between items-center mb-2.5">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.5px]" style={{ color: '#4ade80' }}>
            Decision Trace
          </span>
          <span className="text-[9px] font-semibold px-1.5 py-0.5 rounded" style={{ background: '#166534', color: '#4ade80' }}>
            {trace.action_chosen.name}
          </span>
        </div>
        <span className="text-[10px] text-text-faint">{trace.agent_id} · step {trace.step}</span>
      </div>

      {/* Pre / Post columns */}
      <div className="grid grid-cols-2 gap-2.5 mb-2.5">
        <div className="rounded-md p-2.5" style={{ background: '#0a0f1a' }}>
          <div className="text-[9px] uppercase tracking-[1px] mb-1.5" style={{ color: '#fbbf24' }}>Pre-decisión</div>
          <div className="text-[10px] leading-[1.8]">
            {trace.perception && (
              <div className="text-text">pos <span className="text-text-dim">({String(trace.perception.x ?? '?')}, {String(trace.perception.y ?? '?')})</span></div>
            )}
            {preScalars.map(([key, val]) => (
              <div key={key} className="text-text">{key} <span style={{ color: '#fbbf24', fontWeight: 600 }}>{val.toFixed(2)}</span></div>
            ))}
          </div>
        </div>
        <div className="rounded-md p-2.5" style={{ background: '#0a0f1a' }}>
          <div className="text-[9px] uppercase tracking-[1px] mb-1.5" style={{ color: '#38bdf8' }}>Post-decisión</div>
          <div className="text-[10px] leading-[1.8]">
            {trace.perception && (
              <div className="text-text">pos <span className="text-text-dim">({String(trace.perception.x ?? '?')}, {String(trace.perception.y ?? '?')})</span></div>
            )}
            {postScalars.map(([key, val]) => {
              const preVal = preScalars.find(([k]) => k === key)?.[1]
              const delta = preVal != null ? formatDelta(preVal, val) : { text: '', color: '' }
              return (
                <div key={key} className="text-text">
                  {key} <span style={{ color: '#4ade80', fontWeight: 600 }}>{val.toFixed(2)}</span>
                  {delta.text && <span className="text-[9px] ml-1" style={{ color: delta.color }}>{delta.text}</span>}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Q-value pills */}
      {qValues ? (
        <div className="mb-1.5">
          <div className="text-[9px] uppercase tracking-[1px] text-text-faint mb-1.5">Alternativas (Q-values)</div>
          <div className="flex gap-1.5 flex-wrap">
            {Object.entries(qValues).sort(([, a], [, b]) => b - a).map(([action, val]) => {
              const isChosen = String(action) === trace.action_chosen.name
              return (
                <span key={action} className="text-[10px] px-2 py-0.5 rounded" style={{
                  background: isChosen ? '#166534' : '#1e293b',
                  color: isChosen ? '#4ade80' : '#94a3b8',
                  fontWeight: isChosen ? 600 : 400,
                  border: isChosen ? '1px solid #22c55e40' : '1px solid transparent',
                }}>{String(action)}: {val.toFixed(1)}</span>
              )
            })}
          </div>
        </div>
      ) : (
        <div className="text-[9px] text-text-faint italic mb-1.5">Sin Q-values (control directo)</div>
      )}

      {/* Result footer */}
      <div className="pt-2 border-t border-border-subtle text-[10px]">
        <span style={{ color: trace.outcome.reward > 0 ? '#4ade80' : '#dc2626', fontWeight: 600 }}>
          reward: {trace.outcome.reward > 0 ? '+' : ''}{trace.outcome.reward}
        </span>
        {trace.outcome.action_result?.consumed && (
          <><span className="text-text-faint mx-1">·</span><span className="text-text-dim">consumed {String((trace.outcome.action_result as Record<string,unknown>).resource_type || 'resource')}</span></>
        )}
      </div>
    </div>
  )
}
