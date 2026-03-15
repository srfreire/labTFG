import { useState, useEffect, useRef, useCallback } from 'react'
import type { ReplayData } from '../types'

interface Props {
  replay: ReplayData
}

const AGENT_COLORS = ['#4ade80', '#fbbf24', '#a78bfa', '#f472b6', '#38bdf8', '#fb923c']
const SPEEDS = [0.5, 1, 2, 4]

export function SimulationGrid({ replay }: Props) {
  const [currentStep, setCurrentStep] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speedIdx, setSpeedIdx] = useState(1)
  const [trail, setTrail] = useState<Record<string, { x: number; y: number }[]>>({})
  const intervalRef = useRef<number | null>(null)
  const TRAIL_LENGTH = 5

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
  }, [currentStep, frame])

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

  return (
    <div className="mt-3 border p-3" style={{ background: '#000', borderColor: 'rgba(255,255,255,0.1)' }}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[8px] uppercase tracking-[1px]" style={{ color: 'rgba(255,255,255,0.4)' }}>
          Simulación
        </span>
        <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.3)' }}>
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
          width: 'fit-content',
        }}
      >
        {Array.from({ length: replay.grid_height }, (_, y) =>
          Array.from({ length: replay.grid_width }, (_, x) => {
            const resource = frame.resources.find(r => r.x === x && r.y === y)
            const agent = frame.agents.find(a => a.x === x && a.y === y && a.alive)
            const agentIdx = agent ? frame.agents.findIndex(a => a.id === agent.id) : -1
            const isTrail = !agent && Object.entries(trail).some(([id, positions]) => {
              const a = frame.agents.find(a2 => a2.id === id)
              if (a && a.x === x && a.y === y) return false
              return positions.some(p => p.x === x && p.y === y)
            })

            return (
              <div
                key={`${x}-${y}`}
                style={{
                  width: cellSize,
                  height: cellSize,
                  background: 'rgba(255,255,255,0.02)',
                  position: 'relative',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {resource && !agent && (
                  <div style={{
                    width: cellSize * 0.3,
                    height: cellSize * 0.3,
                    borderRadius: '50%',
                    background: '#22c55e',
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
                    background: 'rgba(255,255,255,0.08)',
                  }} />
                )}
              </div>
            )
          })
        )}
      </div>

      {/* Controls */}
      <div className="flex items-center justify-center gap-3 mt-2">
        <button onClick={reset} className="text-[9px] px-2 py-1 border" style={{ borderColor: 'rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.4)' }}>⟳</button>
        <button onClick={stepBack} className="text-[9px] px-2 py-1 border" style={{ borderColor: 'rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.4)' }}>◁</button>
        <button onClick={togglePlay} className="text-[9px] px-2.5 py-1 border" style={{ borderColor: 'rgba(255,255,255,0.25)', color: 'rgba(255,255,255,0.6)' }}>
          {playing ? '⏸' : '▶'}
        </button>
        <button onClick={stepForward} className="text-[9px] px-2 py-1 border" style={{ borderColor: 'rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.4)' }}>▷</button>
        <button onClick={cycleSpeed} className="text-[9px] px-2 py-1 border" style={{ borderColor: 'rgba(255,255,255,0.15)', color: 'rgba(255,255,255,0.4)' }}>
          {speed}×
        </button>
      </div>

      {/* Step actions summary */}
      {frame.actions.length > 0 && (
        <div className="mt-2 flex gap-2 justify-center flex-wrap">
          {frame.actions.map((a, i) => (
            <span key={i} className="text-[8px] px-1.5 py-0.5 border" style={{
              borderColor: 'rgba(255,255,255,0.08)',
              color: a.reward > 0 ? '#4ade80' : 'rgba(255,255,255,0.3)',
            }}>
              {a.agent_id}: {a.action}{a.reward > 0 ? ` +${a.reward.toFixed(1)}` : ''}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
