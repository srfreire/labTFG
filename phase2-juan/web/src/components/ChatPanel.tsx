import { useState, useRef, useEffect } from 'react'
import type { ChatMessage } from '../types'

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
          <div className="mt-3 border p-2.5" style={{ background: '#000', borderColor: 'rgba(255,255,255,0.1)' }}>
            <div className="text-[8px] uppercase tracking-[1px] mb-2" style={{ color: '#fbbf24' }}>
              Trayectorias
            </div>
            {Object.entries(msg.tracker.trajectories).map(([agent, data]) => (
              <div key={agent} className="flex justify-between py-1 border-b" style={{ borderColor: 'rgba(255,255,255,0.05)' }}>
                <span className="text-[9px]" style={{ color: 'rgba(255,255,255,0.4)' }}>{agent}</span>
                <span className="text-[9px]">{data.resources_consumed} eat · avg hunger {(data.steps_survived > 0 ? data.steps_survived : '?')}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
