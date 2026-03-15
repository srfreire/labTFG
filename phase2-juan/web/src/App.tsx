import { AgentPanel } from './components/AgentPanel'
import { ChatPanel } from './components/ChatPanel'
import { useWebSocket } from './hooks/useWebSocket'
import './index.css'

export default function App() {
  const { connected, agents, pipeline, messages, thinking, send } = useWebSocket()

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <div className="flex justify-between items-center px-6 py-3 border-b" style={{ borderColor: 'rgba(255,255,255,0.2)' }}>
        <div>
          <h1 className="text-[14px] font-bold uppercase tracking-[2px]">DecisionLab</h1>
          <p className="text-[11px] mt-0.5" style={{ color: 'rgba(255,255,255,0.5)' }}>
            Laboratorio Virtual de Simulación
          </p>
        </div>
        <div className="text-[9px]" style={{ color: 'rgba(255,255,255,0.3)' }}>
          <span style={{ color: connected ? '#4ade80' : '#ef4444' }}>●</span>
          {' '}{connected ? 'conectado' : 'desconectado'}
        </div>
      </div>

      {/* Main */}
      <div className="flex flex-1 overflow-hidden">
        <div className="hidden md:block w-[340px] flex-shrink-0">
          <AgentPanel agents={agents} pipeline={pipeline} />
        </div>
        <ChatPanel messages={messages} thinking={thinking} onSend={send} />
      </div>

      {/* Mobile agent bar */}
      <div className="md:hidden flex items-center gap-2 px-4 py-2 border-t overflow-x-auto" style={{ borderColor: 'rgba(255,255,255,0.1)' }}>
        {agents.map(a => (
          <div key={a.name} className="flex items-center gap-1 flex-shrink-0">
            <div className="w-1.5 h-1.5 rounded-full" style={{
              background: a.color,
              opacity: a.status === 'idle' ? 0.3 : 1,
            }} />
            <span className="text-[8px] uppercase" style={{ color: 'rgba(255,255,255,0.4)' }}>{a.name}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
