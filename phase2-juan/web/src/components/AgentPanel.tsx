import type { AgentState, PipelineStep } from '../types'

interface Props {
  agents: AgentState[]
  pipeline: PipelineStep[]
}

const PIPELINE_LABELS: Record<string, string> = {
  arch: 'Architect',
  sim: 'Simulate',
  track: 'Track',
  anal: 'Analyze',
  repo: 'Report',
}
const PIPELINE_ALL = ['arch', 'sim', 'track', 'anal', 'repo']

export function AgentPanel({ agents, pipeline }: Props) {
  const doneSteps = new Set(pipeline.map(p => p.step))

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

      {/* Network visualization */}
      <div className="flex-1 relative flex items-center justify-center" style={{ background: '#050505' }}>
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: 'radial-gradient(circle at center, rgba(255,255,255,0.02) 0%, transparent 70%)',
          }}
        />
        <div className="relative flex flex-col items-center gap-6">
          {/* Top row: Architect + Tracker */}
          <div className="flex gap-12">
            {agents[0] && <AgentNode agent={agents[0]} label="ARCH" />}
            {agents[1] && <AgentNode agent={agents[1]} label="TRACK" />}
          </div>
          {/* Center: Orchestrator */}
          <div className="flex items-center justify-center">
            <div className="flex flex-col items-center gap-1">
              <div
                className="rounded-full flex items-center justify-center"
                style={{
                  width: 36,
                  height: 36,
                  background: 'rgba(148,163,184,0.1)',
                  border: '1.5px solid rgba(148,163,184,0.3)',
                  animation: 'bob 2s ease-in-out infinite',
                }}
              >
                <span className="text-[10px] font-bold" style={{ color: '#94a3b8' }}>O</span>
              </div>
              <span className="text-[7px] uppercase tracking-[1px]" style={{ color: 'rgba(255,255,255,0.3)' }}>Orchestrator</span>
            </div>
          </div>
          {/* Bottom row: Analyst + Reporter */}
          <div className="flex gap-12">
            {agents[2] && <AgentNode agent={agents[2]} label="ANAL" />}
            {agents[3] && <AgentNode agent={agents[3]} label="REPO" />}
          </div>
        </div>
      </div>

      {/* Pipeline */}
      <div className="px-3 py-3" style={{ borderTop: '1px solid rgba(255,255,255,0.1)' }}>
        <div className="text-[8px] uppercase tracking-[2px] mb-2" style={{ color: 'rgba(255,255,255,0.3)' }}>
          Pipeline
        </div>
        <div className="flex items-center justify-between">
          {PIPELINE_ALL.map((step, i) => {
            const done = doneSteps.has(step)
            return (
              <span key={step} className="flex items-center">
                <span
                  className={`text-[9px] uppercase tracking-[1px] px-1.5 py-0.5 transition-all duration-300 ${done ? 'pipeline-step-done' : ''}`}
                  style={{
                    color: done ? 'rgba(255,255,255,0.8)' : 'rgba(255,255,255,0.2)',
                    background: done ? 'rgba(255,255,255,0.06)' : 'transparent',
                    border: `1px solid ${done ? 'rgba(255,255,255,0.15)' : 'rgba(255,255,255,0.05)'}`,
                  }}
                >
                  {PIPELINE_LABELS[step]}
                </span>
                {i < PIPELINE_ALL.length - 1 && (
                  <span className="text-[8px] mx-1" style={{ color: done ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.08)' }}>→</span>
                )}
              </span>
            )
          })}
        </div>
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

function AgentNode({ agent, label }: { agent: AgentState; label: string }) {
  const isActive = agent.status === 'working'
  const isDone = agent.status === 'done'
  const opacity = agent.status === 'idle' ? 0.25 : isDone ? 0.5 : 1

  return (
    <div className="flex flex-col items-center gap-1.5">
      <div
        className="rounded-full flex items-center justify-center transition-all duration-300"
        style={{
          width: 28,
          height: 28,
          background: agent.color + (isActive ? '20' : '10'),
          border: `1.5px solid ${agent.color}`,
          opacity,
          boxShadow: isActive ? `0 0 16px ${agent.color}30` : 'none',
          animation: isActive ? 'bob 1.5s ease-in-out infinite' : undefined,
        }}
      >
        <span className="text-[8px] font-bold" style={{ color: agent.color, opacity: Math.min(opacity * 2, 1) }}>
          {agent.name[0]}
        </span>
      </div>
      <span className="text-[7px] uppercase tracking-[1px]" style={{ color: isActive ? agent.color : 'rgba(255,255,255,0.25)', opacity }}>
        {label}
      </span>
    </div>
  )
}
