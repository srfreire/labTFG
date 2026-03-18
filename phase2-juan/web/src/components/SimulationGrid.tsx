import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import type { ReplayData } from '../types'
import { AGENT_COLORS } from '../constants'

interface Props {
  replay: ReplayData
}
const SPEEDS = [0.5, 1, 2, 4]

export function SimulationGrid({ replay }: Props) {
  const [currentStep, setCurrentStep] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speedIdx, setSpeedIdx] = useState(1)
  const [trail, setTrail] = useState<Record<string, { x: number; y: number }[]>>({})
  const intervalRef = useRef<number | null>(null)
  const TRAIL_LENGTH = 5

  // Reset state when replay changes
  useEffect(() => {
    setCurrentStep(0)
    setPlaying(false)
    setTrail({})
  }, [replay])

  const frame = replay.frames[currentStep]
  const speed = SPEEDS[speedIdx]

  // Build trail history
  useEffect(() => {
    if (!frame) return
    setTrail(prev => {
      const next = { ...prev }
      for (const agent of frame.agents) {
        const history = next[agent.id] || []
        next[agent.id] = [...history.slice(-(TRAIL_LENGTH - 1)), { x: agent.x, y: agent.y }]
      }
      return next
    })
  }, [currentStep, replay.frames])

  // Playback interval
  useEffect(() => {
    if (playing) {
      intervalRef.current = window.setInterval(() => {
        setCurrentStep(prev => {
          if (prev >= replay.total_steps - 1) {
            setPlaying(false)
            return prev
          }
          return prev + 1
        })
      }, 200 / speed)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [playing, speed, replay.total_steps])

  const togglePlay = useCallback(() => setPlaying(p => !p), [])
  const stepBack = useCallback(() => { setPlaying(false); setCurrentStep(s => Math.max(0, s - 1)) }, [])
  const stepForward = useCallback(() => { setPlaying(false); setCurrentStep(s => Math.min(replay.total_steps - 1, s + 1)) }, [replay.total_steps])
  const reset = useCallback(() => { setPlaying(false); setCurrentStep(0); setTrail({}) }, [])
  const cycleSpeed = useCallback(() => setSpeedIdx(i => (i + 1) % SPEEDS.length), [])

  if (!frame) return null

  const cellSize = Math.min(28, Math.floor(300 / Math.max(replay.grid_width, replay.grid_height)))
  const gridWidth = replay.grid_width * cellSize + (replay.grid_width - 1)
  const gridHeight = replay.grid_height * cellSize + (replay.grid_height - 1)

  // Pre-compute lookup maps — O(n) instead of O(width*height*n) find() calls
  const { resourceMap, agentMap, agentIdxMap, trailSet } = useMemo(() => {
    const rMap = new Map<string, boolean>()
    const aMap = new Map<string, typeof frame.agents[0]>()
    const aiMap = new Map<string, number>()
    const tSet = new Set<string>()

    for (const r of frame.resources) rMap.set(`${r.x},${r.y}`, true)
    for (let i = 0; i < frame.agents.length; i++) {
      const a = frame.agents[i]
      if (a.alive) { aMap.set(`${a.x},${a.y}`, a); aiMap.set(`${a.x},${a.y}`, i) }
    }
    for (const [, positions] of Object.entries(trail)) {
      for (const p of positions) {
        const key = `${p.x},${p.y}`
        if (!aMap.has(key)) tSet.add(key)
      }
    }
    return { resourceMap: rMap, agentMap: aMap, agentIdxMap: aiMap, trailSet: tSet }
  }, [frame, trail])

  return (
    <div className="mt-3 border border-border p-3 rounded-lg" style={{ background: 'var(--color-bg)' }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[8px] uppercase tracking-[1px] text-text-dim">
          Simulación
        </span>
        <span className="text-[9px] text-text-faint">
          Step {currentStep + 1} / {replay.total_steps}
        </span>
      </div>

      {/* Grid */}
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

      {/* Controls */}
      <div className="flex items-center justify-center gap-3 mt-2">
        <button onClick={reset} className="text-[9px] px-2 py-1 border border-border rounded-[var(--radius-sm)] text-text-dim hover:bg-surface-hover transition-colors duration-150 cursor-pointer">⟳</button>
        <button onClick={stepBack} className="text-[9px] px-2 py-1 border border-border rounded-[var(--radius-sm)] text-text-dim hover:bg-surface-hover transition-colors duration-150 cursor-pointer">◁</button>
        <button onClick={togglePlay} className="text-[9px] px-2.5 py-1 border border-border rounded-[var(--radius-sm)] text-text-muted hover:bg-surface-hover transition-colors duration-150 cursor-pointer">
          {playing ? '⏸' : '▶'}
        </button>
        <button onClick={stepForward} className="text-[9px] px-2 py-1 border border-border rounded-[var(--radius-sm)] text-text-dim hover:bg-surface-hover transition-colors duration-150 cursor-pointer">▷</button>
        <button onClick={cycleSpeed} className="text-[9px] px-2 py-1 border border-border rounded-[var(--radius-sm)] text-text-dim hover:bg-surface-hover transition-colors duration-150 cursor-pointer">
          {speed}×
        </button>
      </div>

      {/* Agent legend */}
      {frame.agents.length > 1 && (
        <div className="mt-2 flex gap-3 justify-center flex-wrap">
          {frame.agents.map((a, i) => (
            <span key={a.id} className="text-[8px] flex items-center gap-1 text-text-muted">
              <span style={{
                width: 6, height: 6, borderRadius: '50%', display: 'inline-block',
                background: AGENT_COLORS[i % AGENT_COLORS.length],
              }} />
              {a.id}
            </span>
          ))}
        </div>
      )}

      {/* Step actions summary */}
      {frame.actions.length > 0 && (
        <div className="mt-2 flex gap-2 justify-center flex-wrap" style={{ minHeight: 24 }}>
          {frame.actions.map((a, i) => {
            const agentIdx = frame.agents.findIndex(ag => ag.id === a.agent_id)
            return (
              <span key={i} className="text-[8px] px-1.5 py-0.5 border border-border-subtle rounded-[var(--radius-sm)]" style={{
                color: a.reward > 0 ? '#4ade80' : (AGENT_COLORS[agentIdx % AGENT_COLORS.length] + '80'),
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
