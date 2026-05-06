import { useState, useRef, useEffect } from 'react'
import type { ReactNode } from 'react'
import { Facehash } from 'facehash'
import ReactMarkdown from 'react-markdown'
import { Send, FlaskConical } from 'lucide-react'
import type { AgentState, ChatMessage } from '../types'
import { SimulationGrid } from './SimulationGrid'
import { ChartCard } from './ChartCard'
import { DecisionTraceCard } from './DecisionTraceCard'
import { FROM_COLORS, getFromColor } from '../constants'

function getAgentColor(text: string): string | null {
  for (const [name, color] of Object.entries(FROM_COLORS)) {
    if (text.includes(name)) return color
  }
  return null
}

function StrongWithColor(props: { children?: ReactNode }) {
  const text = String(props.children)
  const agentColor = getAgentColor(text)
  return <strong style={agentColor ? { color: agentColor } : undefined}>{props.children}</strong>
}

const mdComponents = { strong: StrongWithColor }

const EXAMPLE_PROMPTS = [
  'Simula el dilema del prisionero con 3 agentes',
  'Compara Q-Learning vs Random en entorno de supervivencia',
  'Crea un entorno de recolección de recursos 10x10',
]

interface Props {
  messages: ChatMessage[]
  thinking: boolean
  onSend: (text: string) => void
  agents: AgentState[]
}

export function ChatPanel({ messages, thinking, onSend, agents }: Props) {
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const workingAgents = agents.filter(a => a.status === 'working')
  const busy = thinking || workingAgents.length > 0
  const isEmpty = messages.length === 0 && !thinking

  useEffect(() => {
    // Delay to let recharts measure containers before scrolling
    const id = setTimeout(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
    }, 100)
    return () => clearTimeout(id)
  }, [messages, thinking])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!input.trim() || busy) return
    onSend(input.trim())
    setInput('')
  }

  const placeholder = busy
    ? `Esperando por ${workingAgents.map(a => a.name).join(', ')}...`
    : 'Describe un paradigma de decisión...'

  const inputForm = (
    <MessageInput
      input={input}
      setInput={setInput}
      onSubmit={handleSubmit}
      placeholder={placeholder}
      busy={busy}
      compact={!isEmpty}
    />
  )

  // Empty state — centered with prompts
  if (isEmpty) {
    return (
      <div className="flex-1 min-h-0 flex flex-col items-center justify-center px-8">
        <div className="mb-8 flex flex-col items-center">
          <FlaskConical size={32} strokeWidth={1.5} className="text-text-ghost mb-4" />
          <h2 className="text-[20px] font-semibold tracking-tight text-text mb-2">DecisionLab</h2>
          <p className="text-[14px] text-text-dim text-center max-w-md">
            Describe un problema de toma de decisiones y el laboratorio simulará, observará y analizará el comportamiento de los agentes.
          </p>
        </div>

        <div className="w-full max-w-xl mb-6">{inputForm}</div>

        <div className="flex flex-wrap justify-center gap-2">
          {EXAMPLE_PROMPTS.map(prompt => (
            <button
              key={prompt}
              onClick={() => { onSend(prompt) }}
              className="text-[12px] px-3.5 py-2 border border-border-subtle rounded-lg text-text-dim hover:text-text-muted hover:border-border hover:bg-surface-hover transition-colors duration-150 cursor-pointer"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>
    )
  }

  // Active chat state
  const orchColor = getFromColor('orchestrator')

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <div ref={scrollRef} className="flex-1 min-h-0 px-8 py-8 overflow-y-auto flex flex-col">
        {messages.map((msg, i) => {
          const prev = messages[i - 1]
          const sameAuthor = prev && prev.from === msg.from && msg.from !== 'user'
          const spacing = i === 0 ? '' : sameAuthor ? 'mt-5' : 'mt-6'
          return (
            <div key={msg.id} className={spacing}>
              <MessageBubble msg={msg} hideAvatar={sameAuthor} />
            </div>
          )
        })}
        {thinking && (
          <div className="flex gap-3 max-w-[80%] mt-5">
            <div className="flex-shrink-0 pt-1">
              <div className="w-7 h-7 rounded-full overflow-hidden">
                <Facehash name="Orchestrator" size={28} variant="solid" colors={[orchColor]} showInitial={false} />
              </div>
            </div>
            <div>
              <div className="text-[11px] font-medium mb-1" style={{ color: orchColor }}>Orchestrator</div>
              <div className="px-4 py-3 rounded-2xl rounded-tl-sm text-[15px] typing-dots bg-surface-hover text-text-dim">
                Pensando<span>.</span><span>.</span><span>.</span>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="px-8 py-4 border-t border-border-subtle">
        <div className="max-w-3xl mx-auto">{inputForm}</div>
      </div>
    </div>
  )
}

function MessageInput({ input, setInput, onSubmit, placeholder, busy, compact }: {
  input: string
  setInput: (v: string) => void
  onSubmit: (e: React.FormEvent) => void
  placeholder: string
  busy: boolean
  compact: boolean
}) {
  return (
    <form onSubmit={onSubmit} className="flex items-stretch gap-3">
      <input
        type="text"
        value={input}
        onChange={e => setInput(e.target.value)}
        placeholder={placeholder}
        disabled={compact && busy}
        className={`flex-1 bg-transparent border border-text-ghost text-text text-[15px] ${compact ? 'py-3' : 'py-3.5'} px-5 outline-none rounded-xl transition-colors duration-150 focus:border-text-dim disabled:opacity-40 disabled:cursor-not-allowed`}
        autoFocus
      />
      <button
        type="submit"
        disabled={busy || !input.trim()}
        className={`flex-shrink-0 ${compact ? 'w-12' : 'w-14'} flex items-center justify-center transition-colors bg-white text-black cursor-pointer hover:bg-white/80 rounded-xl disabled:bg-text-ghost disabled:text-text-dim disabled:cursor-default`}
      >
        <Send size={compact ? 16 : 18} />
      </button>
    </form>
  )
}

function MessageBubble({ msg, hideAvatar }: { msg: ChatMessage; hideAvatar?: boolean }) {
  const isUser = msg.from === 'user'
  const dotColor = getFromColor(msg.from)

  const bubbleStyle = {
    '--msg-accent': dotColor,
    borderRadius: isUser ? '18px 18px 4px 18px' : '4px 18px 18px 18px',
    border: isUser ? 'none' : `1px solid ${dotColor}20`,
    background: isUser ? 'var(--color-border)' : 'var(--color-surface-hover)',
    color: isUser ? 'rgba(255,255,255,0.9)' : 'rgba(255,255,255,0.8)',
  } as React.CSSProperties

  return (
    <div
      className={isUser ? 'animate-msg-in flex justify-end' : 'animate-msg-in flex gap-3'}
      style={{ maxWidth: '80%', marginLeft: isUser ? 'auto' : undefined }}
    >
      {!isUser && (
        <div className="flex-shrink-0 pt-1 w-7">
          {!hideAvatar && (
            <div className="w-7 h-7 rounded-full overflow-hidden">
              <Facehash name={msg.from} size={28} variant="solid" colors={[dotColor]} showInitial={false} />
            </div>
          )}
        </div>
      )}
      <div className={isUser ? '' : 'flex-1 min-w-0'}>
        {!isUser && !hideAvatar && (
          <div className="text-[11px] font-medium mb-1 capitalize" style={{ color: dotColor }}>
            {msg.from}
          </div>
        )}
        <div className="px-4 py-3 text-[15px] leading-[1.6] msg-content" style={bubbleStyle}>
          {msg.text && renderText(msg.text, isUser)}
          {msg.card && <DataCard card={msg.card} color={dotColor} />}
          {msg.tracker && <TrackerCard tracker={msg.tracker} />}
          {msg.analyst && <AnalystCard analyst={msg.analyst} />}
          {msg.charts && msg.charts.map(chart => (
            <ChartCard key={chart.id} spec={chart} />
          ))}
          {msg.replay && <SimulationGrid replay={msg.replay} />}
          {msg.traces && msg.traces.length > 0 && (
            <div className={`mt-3 flex gap-2.5 ${msg.traces.length > 1 ? 'overflow-x-auto' : ''}`}>
              {msg.traces.map((trace, i) => (
                <div key={i} className={msg.traces!.length > 1 ? 'min-w-[280px] flex-1' : ''}>
                  <DecisionTraceCard trace={trace} />
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function renderText(text: string, isUser: boolean) {
  if (isUser) return <span>{text}</span>
  return <ReactMarkdown components={mdComponents}>{text}</ReactMarkdown>
}

function DataCard({ card, color }: { card: { title: string; data: Record<string, unknown> }; color: string }) {
  return (
    <div className="mt-3 border border-border p-3 rounded-lg shadow-xl shadow-black/20" style={{ background: 'var(--color-surface)', borderColor: color + '20' }}>
      <div className="text-[10px] uppercase tracking-[1px] mb-2.5 font-semibold" style={{ color }}>
        {card.title}
      </div>
      <div className="grid gap-2" style={{ gridTemplateColumns: '1fr 1fr' }}>
        {Object.entries(card.data).map(([k, v]) => (
          <div key={k} className="px-2.5 py-2 border border-border-subtle rounded-[var(--radius-md)] min-w-0">
            <div className="text-[10px] text-text-dim">{k}</div>
            <div className="text-[15px] font-semibold mt-0.5 truncate">{String(v)}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function TrackerCard({ tracker }: { tracker: ChatMessage['tracker'] }) {
  if (!tracker) return null
  return (
    <div className="mt-3 border p-3 rounded-lg animate-card-in shadow-xl shadow-black/20" style={{ background: 'var(--color-surface)', borderColor: 'color-mix(in srgb, var(--color-accent-amber) 20%, transparent)' }}>
      <div className="text-[10px] uppercase tracking-[1px] mb-2.5 font-semibold text-accent-amber">
        Trayectorias
      </div>
      {Object.entries(tracker.trajectories).map(([agent, data]) => {
        const agentColor = getAgentColor(agent) || '#fbbf24'
        return (
          <div key={agent} className="mb-2.5 p-2.5 border rounded-[var(--radius-md)]" style={{ borderColor: agentColor + '20' }}>
            <div className="flex justify-between items-center mb-2">
              <span className="text-[12px] font-semibold" style={{ color: agentColor }}>{agent}</span>
              <span className="text-[11px] text-text-faint">{data.steps_survived} pasos</span>
            </div>
            <div className="flex gap-2 flex-wrap">
              <span className="text-[11px] px-2.5 py-1 border rounded-[var(--radius-md)]" style={{ borderColor: agentColor + '25', color: agentColor, background: agentColor + '08' }}>
                {data.resources_consumed} consumidos
              </span>
              {Object.entries(data.actions).map(([action, count]) => (
                <span key={action} className="text-[11px] px-2.5 py-1 border border-border rounded-[var(--radius-md)] text-text-muted">
                  {action}: {String(count)}
                </span>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function AnalystCard({ analyst }: { analyst: NonNullable<ChatMessage['analyst']> }) {
  return (
    <div className="mt-3 border p-3 rounded-lg animate-card-in shadow-xl shadow-black/20" style={{ background: 'var(--color-surface)', borderColor: 'color-mix(in srgb, var(--color-analyst) 20%, transparent)', animationDelay: '100ms' }}>
      <div className="text-[10px] uppercase tracking-[1px] mb-2.5 font-semibold" style={{ color: 'var(--color-analyst)' }}>
        Análisis
      </div>
      {analyst.patterns.length > 0 && (
        <div className="mb-3">
          <div className="text-[10px] mb-1.5 text-text-faint">Patrones</div>
          {analyst.patterns.map(p => (
            <div key={p.id} className="flex items-start gap-2 py-1.5 border-b border-border-faint">
              <span className="text-[10px] px-1.5 py-0.5 flex-shrink-0 rounded-[var(--radius-sm)]" style={{
                '--badge-color': p.type === 'anomaly' ? 'var(--color-accent-red)' : 'var(--color-analyst)',
                background: 'color-mix(in srgb, var(--badge-color) 15%, transparent)',
                color: 'var(--badge-color)',
                border: '1px solid color-mix(in srgb, var(--badge-color) 20%, transparent)',
              } as React.CSSProperties}>{p.type}</span>
              <span className="text-[11px] leading-relaxed text-text-muted">{p.description}</span>
            </div>
          ))}
        </div>
      )}
      {analyst.comparisons.length > 0 && (
        <div className="mb-3">
          <div className="text-[10px] mb-1.5 text-text-faint">Comparaciones</div>
          {analyst.comparisons.map(c => (
            <ComparisonRow key={`${c.metric}-${c.agents.join('-')}`} comparison={c} />
          ))}
        </div>
      )}
    </div>
  )
}

function ComparisonRow({ comparison: c }: { comparison: { metric: string; values: Record<string, number | string>; insight: string } }) {
  const entries = Object.entries(c.values)
  const numericVals = entries.filter(([, v]) => typeof v === 'number')
  const bestAgent = numericVals.length > 1
    ? numericVals.reduce((a, b) => (b[1] as number) > (a[1] as number) ? b : a)[0]
    : null

  return (
    <div className="py-2 border-b border-border-faint">
      <div className="text-[11px] font-semibold mb-1.5" style={{ color: 'var(--color-analyst)' }}>
        {(c.metric || '').replace(/_/g, ' ')}
      </div>
      <div className="flex gap-2 mb-1.5">
        {entries.map(([agent, val]) => {
          const isBest = agent === bestAgent
          return (
            <div key={agent} className="px-2.5 py-2 border rounded-[var(--radius-md)] flex-1 min-w-0" style={{
              borderColor: isBest ? 'color-mix(in srgb, var(--color-accent-green-light) 30%, transparent)' : 'var(--color-border)',
              background: isBest ? 'color-mix(in srgb, var(--color-accent-green-light) 8%, transparent)' : 'var(--color-surface-hover)',
            }}>
              <div className="text-[9px]" style={{ color: isBest ? 'var(--color-accent-green-light)' : 'var(--color-text-faint)' }}>{agent}</div>
              <div className="text-[15px] font-bold mt-0.5" style={{ color: isBest ? 'var(--color-accent-green-light)' : 'var(--color-text-muted)' }}>
                {typeof val === 'number' ? (val % 1 === 0 ? val : val.toFixed(2)) : val}
              </div>
            </div>
          )
        })}
      </div>
      <div className="text-[10px] leading-relaxed text-text-dim">{c.insight}</div>
    </div>
  )
}
