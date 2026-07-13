import { useState, useEffect, useCallback, useMemo } from 'react'
import { RotateCcw, ChevronLeft, ChevronRight, Play, Pause, Gauge } from 'lucide-react'
import type { ReplayData, DecisionTrace, CriticalEvent } from '../types'
import { AGENT_COLORS, withAlpha } from '../constants'
import { ReplayTracePopover } from './ReplayTracePopover'

interface Props {
  replay: ReplayData
}
const SPEEDS = [0.5, 1, 2, 4]

const CRITICAL_COLORS: Record<string, string> = {
  consumption: 'var(--color-accent-green)',
  starvation: 'var(--color-accent-red)',
  death: 'var(--color-accent-red)',
  energy_spike: 'var(--color-accent-amber)',
  strategy_shift: 'var(--color-analyst)',
  decision_confidence_drop: 'var(--color-accent-cyan)',
}

export function SimulationGrid({ replay }: Props) {
  const replayKey = `${replay.grid_width}x${replay.grid_height}:${replay.total_steps}:${replay.frames.length}`
  return <SimulationGridInner key={replayKey} replay={replay} />
}

function SimulationGridInner({ replay }: Props) {
  const [currentStep, setCurrentStep] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speedIdx, setSpeedIdx] = useState(1)
  const TRAIL_LENGTH = 5
  const [activeTrace, setActiveTrace] = useState<{ traces: DecisionTrace[]; criticalEvent?: CriticalEvent } | null>(null)
  const criticalByStep = useMemo(() => {
    const map = new Map<number, typeof replay.critical_events>()
    for (const ce of replay.critical_events || []) {
      const existing = map.get(ce.step) || []
      existing.push(ce)
      map.set(ce.step, existing)
    }
    return map
  }, [replay])

  const frame = replay.frames[currentStep]
  const speed = SPEEDS[speedIdx]

  const trail = useMemo(() => {
    const next: Record<string, { x: number; y: number }[]> = {}
    const start = Math.max(0, currentStep - TRAIL_LENGTH + 1)
    for (const pastFrame of replay.frames.slice(start, currentStep + 1)) {
      for (const agent of pastFrame.agents) {
        const history = next[agent.id] || []
        next[agent.id] = [...history, { x: agent.x, y: agent.y }]
      }
    }
    return next
  }, [currentStep, replay.frames])
  // Un único timer por paso, agendado desde el efecto (no dentro del updater de
  // setState). Programar el setTimeout dentro del updater lo duplicaba bajo
  // StrictMode —React invoca el updater dos veces— y los timers se multiplicaban
  // exponencialmente, acelerando y colgando el replay. Con currentStep como
  // dependencia cada render agenda exactamente un avance y el cleanup lo cancela.
  useEffect(() => {
    if (!playing || currentStep >= replay.total_steps - 1) return
    const next = currentStep + 1
    const id = window.setTimeout(() => {
      setCurrentStep(next)
      if (next >= replay.total_steps - 1) setPlaying(false) // parar al llegar al final (en el callback async, no en el cuerpo del efecto)
    }, 200 / speed)
    return () => clearTimeout(id)
  }, [playing, currentStep, speed, replay.total_steps])

  const togglePlay = useCallback(() => setPlaying(p => !p), [])
  const stepBack = useCallback(() => { setPlaying(false); setCurrentStep(s => Math.max(0, s - 1)) }, [])
  const stepForward = useCallback(() => { setPlaying(false); setCurrentStep(s => Math.min(replay.total_steps - 1, s + 1)) }, [replay.total_steps])
  const reset = useCallback(() => { setPlaying(false); setCurrentStep(0); setActiveTrace(null) }, [])
  const cycleSpeed = useCallback(() => setSpeedIdx(i => (i + 1) % SPEEDS.length), [])

  const controlBtn = 'flex items-center text-[9px] px-2 py-1.5 border border-border rounded-[var(--radius-sm)] text-text-dim hover:bg-surface-hover hover:text-text-muted transition-colors duration-150 cursor-pointer'

  const cellSize = Math.min(28, Math.floor(300 / Math.max(replay.grid_width, replay.grid_height)))
  const gridWidth = replay.grid_width * cellSize + (replay.grid_width - 1)
  const gridHeight = replay.grid_height * cellSize + (replay.grid_height - 1)
  const { resourceMap, agentMap, agentIdxMap, agentIdxById, trailSet } = useMemo(() => {
    const rMap = new Map<string, boolean>()
    const aMap = new Map<string, NonNullable<typeof frame>['agents'][0]>()
    const aiMap = new Map<string, number>()
    const aiById = new Map<string, number>()
    const tSet = new Set<string>()

    if (frame) {
      for (const r of frame.resources) rMap.set(`${r.x},${r.y}`, true)
      for (let i = 0; i < frame.agents.length; i++) {
        const a = frame.agents[i]
        aiById.set(a.id, i)
        if (a.alive) { aMap.set(`${a.x},${a.y}`, a); aiMap.set(`${a.x},${a.y}`, i) }
      }
    }
    for (const [, positions] of Object.entries(trail)) {
      for (const p of positions) {
        const key = `${p.x},${p.y}`
        if (!aMap.has(key)) tSet.add(key)
      }
    }
    return { resourceMap: rMap, agentMap: aMap, agentIdxMap: aiMap, agentIdxById: aiById, trailSet: tSet }
  }, [frame, trail])

  if (!frame) return null

  return (
    <div className="mt-3 border border-border p-3 rounded-lg" style={{ background: 'var(--color-bg)' }}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[8px] uppercase tracking-[1px] text-text-dim">
          Simulación
        </span>
        <span data-testid="replay-step" className="text-[9px] text-text-faint">
          Step {currentStep + 1} / {replay.total_steps}
        </span>
      </div>

      <div
        className="mx-auto"
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${replay.grid_width}, ${cellSize}px)`,
          gridTemplateRows: `repeat(${replay.grid_height}, ${cellSize}px)`,
          gap: '1px',
          width: gridWidth,
          height: gridHeight,
        }}
      >
        {Array.from({ length: replay.grid_height }, (_, y) =>
          Array.from({ length: replay.grid_width }, (__, x) => {
            const key = `${x},${y}`
            const hasResource = resourceMap.has(key)
            const agent = agentMap.get(key)
            const agentIdx = agentIdxMap.get(key) ?? -1
            const isTrail = !agent && trailSet.has(key)

            return (
              <div
                key={key}
                className="relative flex items-center justify-center"
                style={{
                  width: cellSize,
                  height: cellSize,
                  background: 'rgba(255,255,255,0.02)',
                }}
              >
                {hasResource && !agent && (
                  <div style={{
                    width: cellSize * 0.3,
                    height: cellSize * 0.3,
                    borderRadius: '50%',
                    background: 'var(--color-accent-green)',
                    opacity: 0.6,
                  }} />
                )}
                {agent && (
                  <div style={{
                    width: cellSize * 0.65,
                    height: cellSize * 0.65,
                    borderRadius: '50%',
                    background: AGENT_COLORS[agentIdx % AGENT_COLORS.length],
                    transition: 'all 150ms ease-out',
                    boxShadow: `0 0 ${cellSize * 0.4}px ${AGENT_COLORS[agentIdx % AGENT_COLORS.length]}40`,
                  }} />
                )}
                {isTrail && (
                  <div style={{
                    width: cellSize * 0.2,
                    height: cellSize * 0.2,
                    borderRadius: '50%',
                    background: 'var(--color-border-subtle)',
                  }} />
                )}
              </div>
            )
          })
        )}
      </div>

      <div className="flex items-center justify-center gap-2 mt-2">
        <button onClick={reset} className={controlBtn}><RotateCcw size={12} /></button>
        <button onClick={stepBack} className={controlBtn}><ChevronLeft size={14} /></button>
        <button onClick={togglePlay} className={`${controlBtn} px-2.5 text-text-muted`}>
          {playing ? <Pause size={12} /> : <Play size={12} />}
        </button>
        <button onClick={stepForward} className={controlBtn}><ChevronRight size={14} /></button>
        <button onClick={cycleSpeed} className={`${controlBtn} gap-1`}>
          <Gauge size={11} />{speed}×
        </button>
      </div>

      {replay.critical_events && replay.critical_events.length > 0 && (
        <div className="mt-2">
          <div className="text-[8px] uppercase tracking-[1px] text-text-dim mb-1">Eventos críticos</div>
          <div className="relative h-3 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
            <div
              className="absolute top-0 h-full transition-all duration-150"
              style={{
                left: `${(currentStep / Math.max(replay.total_steps - 1, 1)) * 100}%`,
                width: 2,
                background: 'var(--color-text-dim)',
              }}
            />
            {replay.critical_events.map((ce, i) => (
              <button
                key={i}
                className="absolute top-0 h-full cursor-pointer hover:opacity-100 transition-opacity"
                style={{
                  left: `${(ce.step / Math.max(replay.total_steps - 1, 1)) * 100}%`,
                  width: Math.max(3, 100 / replay.total_steps),
                  background: CRITICAL_COLORS[ce.type] || 'var(--color-accent-amber)',
                  opacity: ce.severity * 0.8 + 0.2,
                }}
                title={ce.description}
                onClick={() => {
                  setPlaying(false)
                  setCurrentStep(ce.step)
                  const stepTraces = replay.traces?.[ce.step]
                  if (stepTraces) {
                    const agentTrace = stepTraces.find(t => t.agent_id === ce.agent_id) || stepTraces[0]
                    setActiveTrace({ traces: [agentTrace], criticalEvent: ce })
                  } else {
                    setActiveTrace(null)
                  }
                }}
              />
            ))}
          </div>
          {criticalByStep.has(currentStep) && (
            <div className="flex gap-1.5 flex-wrap mt-1.5">
              {criticalByStep.get(currentStep)!.map((ce, i) => (
                <span
                  key={i}
                  className="text-[8px] px-1.5 py-0.5 rounded-[var(--radius-sm)] border"
                  style={{
                    color: CRITICAL_COLORS[ce.type] || 'var(--color-accent-amber)',
                    borderColor: `color-mix(in srgb, ${CRITICAL_COLORS[ce.type] || 'var(--color-accent-amber)'} 19%, transparent)`,
                    background: `color-mix(in srgb, ${CRITICAL_COLORS[ce.type] || 'var(--color-accent-amber)'} 6%, transparent)`,
                  }}
                >
                  {ce.description}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTrace && activeTrace.traces[0] && (
        <div className="mt-2">
          <ReplayTracePopover
            trace={activeTrace.traces[0]}
            criticalEvent={activeTrace.criticalEvent}
            onClose={() => setActiveTrace(null)}
          />
        </div>
      )}

      {frame.agents.length > 0 && (
        <div className="mt-3 flex flex-col gap-1.5">
          <div className="text-[8px] uppercase tracking-[1px] text-text-dim">Agentes</div>
          {frame.agents.map((a, i) => {
            const color = AGENT_COLORS[i % AGENT_COLORS.length]
            return (
              <div key={a.id} className="flex items-center gap-2">
                <span style={{
                  width: 10, height: 10, borderRadius: '50%', display: 'inline-block',
                  background: color,
                  boxShadow: `0 0 6px ${color}40`,
                  flexShrink: 0,
                }} />
                <span className="text-[11px] font-medium" style={{ color }}>{a.id}</span>
                <span className="text-[9px] font-mono text-text-faint">{color}</span>
                {!a.alive && <span className="text-[8px] text-text-faint">✕ muerto</span>}
              </div>
            )
          })}
        </div>
      )}

      {frame.actions.length > 0 && (
        <div className="mt-2 flex gap-2 justify-center flex-wrap" style={{ minHeight: 24 }}>
          {frame.actions.map((a, i) => {
            const agentIdx = agentIdxById.get(a.agent_id) ?? 0
            return (
              <span key={i} className="text-[8px] px-1.5 py-0.5 border border-border-subtle rounded-[var(--radius-sm)]" style={{
                color: a.reward > 0 ? 'var(--color-accent-green-light)' : withAlpha(AGENT_COLORS[agentIdx % AGENT_COLORS.length], '80'),
              }}>
                {a.agent_id}: {a.action}{a.reward > 0 ? ` +${a.reward.toFixed(1)}` : ''}
              </span>
            )
          })}
        </div>
      )}
    </div>
  )
}
