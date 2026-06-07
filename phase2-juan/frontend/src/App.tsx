import { useMemo, useState } from 'react'
import { Network } from 'lucide-react'
import { AgentPanel } from './components/AgentPanel'
import { ChatPanel } from './components/ChatPanel'
import { KnowledgePanel } from './components/knowledge/KnowledgePanel'
import { useWebSocket } from './hooks/useWebSocket'
import { useMockWebSocket } from './hooks/useMockWebSocket'
import type { DataCard } from './types'

const ENV_CARD_TITLE = 'Environment Spec'

function lastEnvCard(messages: { card?: DataCard }[]): DataCard | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const card = messages[i].card
    if (card?.title === ENV_CARD_TITLE) return card
  }
  return null
}

const isMock = new URLSearchParams(window.location.search).has('mock')

function MockApp() {
  return <AppShell {...useMockWebSocket()} />
}

function RealApp() {
  return <AppShell {...useWebSocket()} />
}

export default function App() {
  return isMock ? <MockApp /> : <RealApp />
}

type ShellProps = ReturnType<typeof useWebSocket>

function AppShell({ connected, agents, messages, thinking, simAgents, envCard: envCardLive, send }: ShellProps) {
  const [kgOpen, setKgOpen] = useState(false)
  const envCardFromMsgs = useMemo(() => lastEnvCard(messages), [messages])
  // Prefer the live env card from `env_card_update` events (carries seed +
  // Pasos ejecutados post-sim) and fall back to the original create_environment
  // card extracted from chat history (so the sidebar already shows something
  // before the sim runs).
  const envCard = envCardLive ?? envCardFromMsgs
  return (
    <div className="h-screen p-10 flex gap-8 overflow-hidden">
      <aside className="hidden md:flex w-[200px] flex-shrink-0 min-h-0 flex-col floating-panel">
        <div className="px-4 py-3 border-b border-border-subtle shrink-0">
          <div className="text-[17px] font-semibold tracking-tight text-text">
            DecisionLab
          </div>
          <div className="flex items-center gap-1.5 mt-1">
            <span className="text-[13px] text-text-muted">Laboratorio</span>
            <span
              className="w-2 h-2 rounded-full inline-block shrink-0"
              style={{ background: connected ? 'var(--color-accent-green-light)' : 'var(--color-accent-red)' }}
            />
            {isMock && (
              <span className="text-[9px] px-1.5 py-0.5 uppercase tracking-[1px] rounded-[var(--radius-sm)] text-accent-amber" style={{ background: 'color-mix(in srgb, var(--color-accent-amber) 15%, transparent)', border: '1px solid color-mix(in srgb, var(--color-accent-amber) 25%, transparent)' }}>
                mock
              </span>
            )}
            <button
              onClick={() => setKgOpen(v => !v)}
              className="ml-auto p-1 rounded-[var(--radius-sm)] text-text-faint hover:text-text transition-colors"
              title="Knowledge graph"
              aria-pressed={kgOpen}
            >
              <Network size={14} />
            </button>
          </div>
        </div>
        <AgentPanel agents={agents} simAgents={simAgents} envCard={envCard} />
      </aside>

      <main className="flex-1 min-h-0 flex flex-col floating-panel">
        <ChatPanel messages={messages} thinking={thinking} onSend={send} agents={agents} connected={connected} />
      </main>

      {kgOpen && (
        <aside className="hidden md:flex w-[420px] flex-shrink-0 min-h-0 flex-col floating-panel">
          <KnowledgePanel onClose={() => setKgOpen(false)} />
        </aside>
      )}

      <div className="md:hidden fixed bottom-4 left-4 right-4 flex items-center gap-2 px-4 py-2.5 floating-panel overflow-x-auto z-30">
        {agents.map(a => (
          <div key={a.name} className="flex items-center gap-1 flex-shrink-0">
            <div className="w-1.5 h-1.5 rounded-full" style={{
              background: a.color,
              opacity: a.status === 'idle' ? 0.3 : 1,
            }} />
            <span className="text-[8px] uppercase text-text-dim">{a.name}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
