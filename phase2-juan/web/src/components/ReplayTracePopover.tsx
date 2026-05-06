import type { DecisionTrace, CriticalEvent } from '../types'
import { extractQValues } from '../utils'

interface Props {
  trace: DecisionTrace
  criticalEvent?: CriticalEvent
  onClose: () => void
}

export function ReplayTracePopover({ trace, criticalEvent, onClose }: Props) {
  const qValues = extractQValues(trace.pre_state)
  const maxQ = qValues ? Math.max(...Object.values(qValues), 0.01) : 0

  const deltas: { label: string; pre: string; post: string; color: string }[] = []
  if (trace.pre_state && trace.post_state) {
    for (const key of ['energy', 'drive', 'error_signal']) {
      const pre = trace.pre_state[key]
      const post = trace.post_state[key]
      if (typeof pre === 'number' && typeof post === 'number') {
        deltas.push({ label: key, pre: pre.toFixed(1), post: post.toFixed(1), color: post >= pre ? 'var(--color-accent-green-light)' : 'var(--color-accent-red)' })
      }
    }
  }

  return (
    <div className="font-mono text-[11px] text-text-dim rounded-lg border p-3.5" style={{
      background: 'var(--color-surface)',
      borderColor: criticalEvent ? 'color-mix(in srgb, var(--color-accent-green) 25%, transparent)' : 'var(--color-border-subtle)',
      boxShadow: 'var(--shadow-popover)',
    }}>
      {/* Header */}
      <div className="flex justify-between items-center mb-2">
        <span className="text-[11px] font-semibold" style={{ color: 'var(--color-accent-green-light)' }}>{trace.agent_id}</span>
        <div className="flex items-center gap-2">
          {criticalEvent && (
            <span className="text-[9px] px-1.5 py-0.5 rounded" style={{ color: 'var(--color-accent-cyan)', background: 'color-mix(in srgb, var(--color-accent-cyan) 25%, transparent)' }}>
              {criticalEvent.type.replace(/_/g, ' ')}
            </span>
          )}
          <button onClick={onClose} className="text-text-faint hover:text-text-dim text-[14px] leading-none cursor-pointer">×</button>
        </div>
      </div>

      {/* Q-value bars */}
      {qValues ? (
        <div className="flex flex-col gap-1 mb-2.5">
          {Object.entries(qValues).sort(([, a], [, b]) => b - a).map(([action, val]) => {
            const isChosen = String(action) === trace.action_chosen.name
            const pct = maxQ > 0 ? (val / maxQ) * 100 : 0
            return (
              <div key={action} className="flex items-center gap-1">
                <span className="text-[10px] text-right" style={{ width: 48, color: isChosen ? 'var(--color-accent-green-light)' : 'var(--color-text-dim)', fontWeight: isChosen ? 600 : 400 }}>
                  {String(action)}
                </span>
                <div className="flex-1 h-4 rounded relative overflow-hidden" style={{ background: 'var(--color-surface-hover)' }}>
                  <div className="h-full rounded" style={{ width: `${Math.max(pct, 2)}%`, background: isChosen ? 'linear-gradient(90deg, var(--color-accent-green), var(--color-accent-green-light))' : 'var(--color-border)' }} />
                  <span className="absolute text-[9px]" style={{ right: 4, top: 1, color: isChosen ? '#fff' : 'var(--color-orchestrator)' }}>{val.toFixed(1)}</span>
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="text-[10px] mb-2.5 text-text-faint italic">Sin Q-values (control directo)</div>
      )}

      {/* Context row */}
      {deltas.length > 0 && (
        <div className="flex gap-2.5 flex-wrap px-2 py-1.5 rounded text-[10px]" style={{ background: 'var(--color-surface-hover)' }}>
          {deltas.map(d => (
            <span key={d.label}>{d.label} <span style={{ color: 'var(--color-accent-amber)' }}>{d.pre}</span> → <span style={{ color: d.color }}>{d.post}</span></span>
          ))}
          <span>reward <span style={{ color: trace.outcome.reward > 0 ? 'var(--color-accent-green-light)' : 'var(--color-accent-red)' }}>{trace.outcome.reward > 0 ? '+' : ''}{trace.outcome.reward}</span></span>
        </div>
      )}

      {/* Critical event detail */}
      {criticalEvent?.type === 'decision_confidence_drop' && criticalEvent.data && (
        <div className="mt-1.5 text-[9px]" style={{ color: 'var(--color-accent-cyan)' }}>
          gap Q-values: {String((criticalEvent as any).data.prev_gap)} → {String((criticalEvent as any).data.new_gap)}
        </div>
      )}
    </div>
  )
}
