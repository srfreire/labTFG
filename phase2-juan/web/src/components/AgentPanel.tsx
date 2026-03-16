import type { AgentState, PipelineStep } from '../types'

interface Props {
  agents: AgentState[]
  pipeline: PipelineStep[]
}


// Desk positions (percentage) — one per agent corner
const DESK_POSITIONS = [
  { top: '8%', left: '8%' },      // Architect — top-left
  { top: '8%', right: '8%' },     // Tracker — top-right
  { bottom: '12%', left: '8%' },  // Analyst — bottom-left
  { bottom: '12%', right: '8%' }, // Reporter — bottom-right
]

// Idle positions — clustered around orchestrator center
const IDLE_OFFSETS = [
  { top: '42%', left: '28%' },   // Architect — left of O
  { top: '42%', right: '28%' },  // Tracker — right of O
  { top: '56%', left: '32%' },   // Analyst — below-left of O
  { top: '56%', right: '32%' },  // Reporter — below-right of O
]

export function AgentPanel({ agents, pipeline }: Props) {
  return (
    <div className="flex flex-col h-full border-r" style={{ borderColor: 'rgba(255,255,255,0.2)' }}>
      {/* Agent list */}
      <div className="p-4 border-b" style={{ borderColor: 'rgba(255,255,255,0.1)' }}>
        <div className="text-[9px] uppercase tracking-[2px] mb-3" style={{ color: 'rgba(255,255,255,0.4)' }}>
          Agentes
        </div>
        <div className="space-y-1">
          {agents.map(agent => (
            <AgentRow key={agent.name} agent={agent} />
          ))}
        </div>
      </div>

      {/* Lab floor */}
      <div className="flex-1 relative" style={{ background: '#050505' }}>
        {/* Grid background */}
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              'repeating-linear-gradient(0deg, transparent, transparent 29px, rgba(255,255,255,0.02) 29px, rgba(255,255,255,0.02) 30px),' +
              'repeating-linear-gradient(90deg, transparent, transparent 29px, rgba(255,255,255,0.02) 29px, rgba(255,255,255,0.02) 30px)',
          }}
        />

        {/* Desks — always visible in corners */}
        {DESK_POSITIONS.map((pos, i) => (
          <Desk key={i} style={pos} active={agents[i]?.status === 'working' || agents[i]?.status === 'done'} color={agents[i]?.color} />
        ))}

        {/* Orchestrator — center */}
        <div className="absolute flex flex-col items-center gap-1" style={{ top: '42%', left: '50%', transform: 'translateX(-50%)' }}>
          <div
            className="rounded-full flex items-center justify-center"
            style={{
              width: 28, height: 28,
              background: 'rgba(148,163,184,0.12)',
              border: '1.5px solid rgba(148,163,184,0.35)',
            }}
          >
            <span className="text-[10px] font-bold" style={{ color: '#94a3b8' }}>O</span>
          </div>
          <span className="text-[7px] uppercase tracking-[1px]" style={{ color: 'rgba(148,163,184,0.4)' }}>orch</span>
        </div>

        {/* Worker agents — move between idle (near O) and desk (corners) */}
        {agents.map((agent, i) => {
          const atDesk = agent.status === 'working' || agent.status === 'done'
          const pos = atDesk ? DESK_POSITIONS[i] : IDLE_OFFSETS[i]
          if (!pos) return null
          return (
            <Worker
              key={agent.name}
              agent={agent}
              style={pos}
              atDesk={atDesk}
            />
          )
        })}
      </div>

    </div>
  )
}

function AgentRow({ agent }: { agent: AgentState }) {
  const isActive = agent.status === 'working'
  const isDone = agent.status === 'done'

  return (
    <div
      className="flex items-center gap-2.5 px-3 py-2 transition-all duration-300"
      style={{
        border: `1px solid ${isActive ? agent.color + '40' : 'rgba(255,255,255,0.06)'}`,
        background: isActive ? agent.color + '08' : 'transparent',
        opacity: agent.status === 'idle' ? 0.5 : 1,
      }}
    >
      <div className="relative flex-shrink-0">
        <div
          className="w-2 h-2 rounded-full transition-all duration-300"
          style={{
            background: agent.color,
            boxShadow: isActive ? `0 0 8px ${agent.color}60` : 'none',
          }}
        />
        {isActive && (
          <div
            className="absolute -inset-1.5 rounded-full"
            style={{
              border: `1px solid ${agent.color}`,
              animation: 'ping 2s ease-in-out infinite',
              opacity: 0.3,
            }}
          />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[10px] font-semibold uppercase tracking-[1px]">{agent.name}</div>
      </div>
      <div
        className="text-[7px] uppercase tracking-[1px] px-1.5 py-0.5 transition-all duration-300"
        style={{
          color: isActive ? agent.color : isDone ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.2)',
          background: isDone ? 'rgba(255,255,255,0.04)' : 'transparent',
          border: `1px solid ${isActive ? agent.color + '30' : 'rgba(255,255,255,0.08)'}`,
        }}
      >
        {isActive ? 'working' : isDone ? 'done' : 'idle'}
      </div>
    </div>
  )
}

function Desk({ style, active, color }: { style: React.CSSProperties; active: boolean; color?: string }) {
  return (
    <div className="absolute" style={style}>
      {/* Desk surface */}
      <div
        className="transition-all duration-500"
        style={{
          width: 56,
          height: 28,
          background: active ? (color || '#fff') + '12' : 'rgba(255,255,255,0.04)',
          border: `1px solid ${active ? (color || '#fff') + '35' : 'rgba(255,255,255,0.10)'}`,
          borderRadius: 3,
        }}
      />
      {/* Monitor on desk */}
      <div
        className="mx-auto transition-all duration-500"
        style={{
          width: 20,
          height: 14,
          marginTop: -26,
          background: active ? (color || '#fff') + '20' : 'rgba(255,255,255,0.05)',
          border: `1px solid ${active ? (color || '#fff') + '40' : 'rgba(255,255,255,0.10)'}`,
          borderRadius: 2,
        }}
      />
    </div>
  )
}

function Worker({ agent, style, atDesk }: { agent: AgentState; style: React.CSSProperties; atDesk: boolean }) {
  const isActive = agent.status === 'working'

  return (
    <div
      className="absolute flex flex-col items-center z-10"
      style={{
        ...style,
        transition: 'all 0.8s cubic-bezier(0.4, 0, 0.2, 1)',
        transform: atDesk ? 'translateY(-8px)' : undefined,
      }}
    >
      {/* Head */}
      <div
        className="rounded-full transition-all duration-300"
        style={{
          width: 14,
          height: 14,
          background: agent.color,
          opacity: isActive ? 1 : agent.status === 'done' ? 0.5 : 0.25,
          boxShadow: isActive ? `0 0 12px ${agent.color}50` : 'none',
          animation: isActive ? 'bob 1.5s ease-in-out infinite' : undefined,
        }}
      />
      {/* Body */}
      <div
        className="transition-all duration-300"
        style={{
          width: 16,
          height: 9,
          background: agent.color,
          opacity: (isActive ? 1 : agent.status === 'done' ? 0.5 : 0.25) * 0.5,
          borderRadius: '0 0 4px 4px',
          marginTop: -1,
        }}
      />
      {/* Label */}
      <div
        className="text-[7px] uppercase tracking-[1px] mt-0.5 transition-all duration-300"
        style={{ color: isActive ? agent.color : 'rgba(255,255,255,0.2)' }}
      >
        {agent.name[0]}
      </div>
    </div>
  )
}
