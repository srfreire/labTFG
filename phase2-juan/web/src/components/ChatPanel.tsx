import { useState, useRef, useEffect } from 'react'
import type { ChatMessage } from '../types'
import { SimulationGrid } from './SimulationGrid'

interface Props {
  messages: ChatMessage[]
  thinking: boolean
  onSend: (text: string) => void
}

const FROM_COLORS: Record<string, string> = {
  user: 'rgba(255,255,255,0.5)',
  orchestrator: '#94a3b8',
  tracker: '#fbbf24',
  analyst: '#a78bfa',
  reporter: '#f472b6',
}

export function ChatPanel({ messages, thinking, onSend }: Props) {
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, thinking])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim()) return
    onSend(input.trim())
    setInput('')
  }

  return (
    <div className="flex-1 flex flex-col">
      <div className="px-5 py-3 border-b" style={{ borderColor: 'rgba(255,255,255,0.2)' }}>
        <span className="text-[9px] uppercase tracking-[2px]" style={{ color: 'rgba(255,255,255,0.5)' }}>
          Terminal
        </span>
      </div>

      <div ref={scrollRef} className="flex-1 p-5 overflow-y-auto flex flex-col gap-4">
        {messages.map(msg => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
        {thinking && (
          <div className="self-end max-w-[85%]">
            <div className="text-[8px] uppercase tracking-[1px] mb-1" style={{ color: 'rgba(255,255,255,0.3)' }}>
              Orchestrator
            </div>
            <div className="px-3.5 py-2.5 border text-[11px]" style={{ borderColor: 'rgba(255,255,255,0.15)', background: 'rgba(255,255,255,0.02)', color: 'rgba(255,255,255,0.4)' }}>
              Pensando<span className="animate-pulse">...</span>
            </div>
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="px-5 py-3 border-t" style={{ borderColor: 'rgba(255,255,255,0.2)' }}>
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Escribe tu mensaje..."
          className="w-full bg-black border px-3.5 py-2.5 text-[11px] text-white outline-none font-mono"
          style={{ borderColor: 'rgba(255,255,255,0.2)' }}
          autoFocus
        />
      </form>
    </div>
  )
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.from === 'user'
  const dotColor = FROM_COLORS[msg.from] || '#fff'

  return (
    <div className={`max-w-[85%] ${isUser ? 'self-start' : 'self-end'}`}>
      <div className="flex items-center gap-1 mb-1">
        <div className="w-1 h-1 rounded-full" style={{ background: dotColor }} />
        <span className="text-[8px] uppercase tracking-[1px]" style={{ color: 'rgba(255,255,255,0.3)' }}>
          {msg.from === 'user' ? 'Tú' : msg.from}
        </span>
      </div>
      <div
        className="px-3.5 py-2.5 border text-[11px] leading-relaxed"
        style={{
          borderColor: isUser ? 'rgba(255,255,255,0.15)' : 'rgba(255,255,255,0.1)',
          background: isUser ? 'rgba(255,255,255,0.03)' : 'rgba(255,255,255,0.02)',
          whiteSpace: 'pre-wrap',
        }}
      >
        {msg.text}

        {/* Data card */}
        {msg.card && (
          <div className="mt-3 border p-2.5" style={{ background: '#000', borderColor: 'rgba(255,255,255,0.1)' }}>
            <div className="text-[8px] uppercase tracking-[1px] mb-2" style={{ color: 'rgba(255,255,255,0.4)' }}>
              {msg.card.title}
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {Object.entries(msg.card.data).map(([k, v]) => (
                <div key={k} className="px-2 py-1.5 border" style={{ borderColor: 'rgba(255,255,255,0.08)' }}>
                  <div className="text-[8px]" style={{ color: 'rgba(255,255,255,0.4)' }}>{k}</div>
                  <div className="text-[12px] font-semibold mt-0.5">{v}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tracker data */}
        {msg.tracker && (
          <div className="mt-3 border p-2.5 animate-card-in" style={{ background: '#000', borderColor: 'rgba(255,255,255,0.1)' }}>
            <div className="text-[8px] uppercase tracking-[1px] mb-2" style={{ color: '#fbbf24' }}>
              Trayectorias
            </div>
            {Object.entries(msg.tracker.trajectories).map(([agent, data]) => (
              <div key={agent} className="mb-2 p-2 border" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                <div className="flex justify-between items-center mb-1.5">
                  <span className="text-[10px] font-semibold" style={{ color: 'rgba(255,255,255,0.6)' }}>{agent}</span>
                  <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.3)' }}>{data.steps_survived} steps</span>
                </div>
                <div className="flex gap-2 flex-wrap">
                  <span className="text-[8px] px-1.5 py-0.5 border" style={{ borderColor: 'rgba(255,255,255,0.08)', color: '#4ade80' }}>
                    {data.resources_consumed} consumed
                  </span>
                  {Object.entries(data.actions).map(([action, count]) => (
                    <span key={action} className="text-[8px] px-1.5 py-0.5 border" style={{ borderColor: 'rgba(255,255,255,0.08)', color: 'rgba(255,255,255,0.4)' }}>
                      {action}: {count}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Analyst data */}
        {msg.analyst && (
          <div className="mt-3 border p-2.5 animate-card-in" style={{ background: '#000', borderColor: 'rgba(255,255,255,0.1)', animationDelay: '100ms' }}>
            <div className="text-[8px] uppercase tracking-[1px] mb-2" style={{ color: '#a78bfa' }}>
              Análisis
            </div>
            {msg.analyst.patterns.length > 0 && (
              <div className="mb-2">
                <div className="text-[8px] mb-1" style={{ color: 'rgba(255,255,255,0.3)' }}>Patrones</div>
                {msg.analyst.patterns.map(p => (
                  <div key={p.id} className="flex items-start gap-1.5 py-1 border-b" style={{ borderColor: 'rgba(255,255,255,0.04)' }}>
                    <span className="text-[8px] px-1 py-0.5 flex-shrink-0" style={{
                      background: p.type === 'anomaly' ? 'rgba(239,68,68,0.15)' : 'rgba(168,139,250,0.15)',
                      color: p.type === 'anomaly' ? '#ef4444' : '#a78bfa',
                      border: `1px solid ${p.type === 'anomaly' ? 'rgba(239,68,68,0.2)' : 'rgba(168,139,250,0.2)'}`,
                    }}>{p.type}</span>
                    <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.5)' }}>{p.description}</span>
                  </div>
                ))}
              </div>
            )}
            {msg.analyst.comparisons.length > 0 && (
              <div className="mb-2">
                <div className="text-[8px] mb-1" style={{ color: 'rgba(255,255,255,0.3)' }}>Comparaciones</div>
                {msg.analyst.comparisons.map((c, i) => (
                  <div key={i} className="py-1.5 border-b" style={{ borderColor: 'rgba(255,255,255,0.04)' }}>
                    <div className="flex gap-2 mb-0.5">
                      <span className="text-[8px]" style={{ color: 'rgba(255,255,255,0.4)' }}>{c.metric}</span>
                      {Object.entries(c.values).map(([agent, val]) => (
                        <span key={agent} className="text-[9px] font-semibold">{agent}: {typeof val === 'number' ? val.toFixed(1) : val}</span>
                      ))}
                    </div>
                    <div className="text-[8px]" style={{ color: 'rgba(255,255,255,0.3)' }}>{c.insight}</div>
                  </div>
                ))}
              </div>
            )}
            {Object.keys(msg.analyst.metrics).length > 0 && (
              <div>
                <div className="text-[8px] mb-1" style={{ color: 'rgba(255,255,255,0.3)' }}>Métricas</div>
                <div className="grid grid-cols-2 gap-1">
                  {Object.entries(msg.analyst.metrics).map(([agent, metrics]) => (
                    Object.entries(metrics).map(([key, val]) => (
                      <div key={`${agent}-${key}`} className="px-1.5 py-1 border" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                        <div className="text-[7px]" style={{ color: 'rgba(255,255,255,0.3)' }}>{agent} · {key}</div>
                        <div className="text-[11px] font-semibold mt-0.5">{typeof val === 'number' ? val.toFixed(2) : val}</div>
                      </div>
                    ))
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Simulation replay */}
        {msg.replay && (
          <SimulationGrid replay={msg.replay} />
        )}
      </div>
    </div>
  )
}
