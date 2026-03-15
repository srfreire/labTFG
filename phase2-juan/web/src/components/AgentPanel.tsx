import type { AgentState, PipelineStep } from '../types'

interface Props {
  agents: AgentState[]
  pipeline: PipelineStep[]
}

const PIPELINE_ALL = ['arch', 'sim', 'track', 'anal', 'repo']

export function AgentPanel({ agents, pipeline }: Props) {
  const doneSteps = new Set(pipeline.map(p => p.step))

  return (
    <div className="flex flex-col h-full border-r" style={{ borderColor: 'rgba(255,255,255,0.2)' }}>
      {/* Agent list */}
      <div className="p-4 border-b" style={{ borderColor: 'rgba(255,255,255,0.1)' }}>
        <div className="text-[10px] uppercase tracking-[2px] mb-3" style={{ color: 'rgba(255,255,255,0.5)' }}>
          Agentes
        </div>
        <div className="space-y-1.5">
          {agents.map(agent => (
            <AgentRow key={agent.name} agent={agent} />
          ))}
        </div>
      </div>

      {/* Lab floor */}
      <div className="flex-1 relative" style={{ background: '#090909' }}>
        <div
          className="absolute inset-0"
          style={{
            backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 29px, rgba(255,255,255,0.03) 29px, rgba(255,255,255,0.03) 30px), repeating-linear-gradient(90deg, transparent, transparent 29px, rgba(255,255,255,0.03) 29px, rgba(255,255,255,0.03) 30px)',
          }}
        />
        {/* Mini desks */}
        <MiniDesk style={{ top: '10%', left: '10%' }} />
        <MiniDesk style={{ top: '10%', right: '10%' }} />
        <MiniDesk style={{ bottom: '10%', left: '10%' }} />
        <MiniDesk style={{ bottom: '10%', right: '10%' }} />

        {/* Mini agents */}
        {agents[0] && <MiniAgent agent={agents[0]} style={{ top: '18%', left: '16%' }} label="A" />}
        {agents[1] && <MiniAgent agent={agents[1]} style={{ top: '18%', right: '16%' }} label="T" />}
        {agents[2] && <MiniAgent agent={agents[2]} style={{ bottom: '28%', left: '32%' }} label="N" />}
        {agents[3] && <MiniAgent agent={agents[3]} style={{ bottom: '18%', right: '20%' }} label="R" />}
        {/* Orchestrator center */}
        <div className="absolute flex flex-col items-center gap-0.5" style={{ top: '44%', left: '44%' }}>
          <div
            className="rounded-full"
            style={{
              width: 12, height: 12, background: '#94a3b8',
              animation: 'bob 1.5s ease-in-out infinite',
            }}
          />
          <div className="rounded-b" style={{ width: 14, height: 8, background: '#94a3b8', opacity: 0.5, borderRadius: '0 0 3px 3px' }} />
          <div className="text-[7px] uppercase tracking-[1px]" style={{ color: 'rgba(255,255,255,0.4)' }}>O</div>
        </div>
      </div>

      {/* Pipeline */}
      <div className="flex items-center p-2.5 gap-0" style={{ borderTop: '1px solid rgba(255,255,255,0.1)' }}>
        {PIPELINE_ALL.map((step, i) => (
          <span key={step}>
            <span
              className={`text-[8px] uppercase tracking-[1px] px-1.5 py-1 transition-colors duration-400 ${doneSteps.has(step) ? 'pipeline-step-done' : ''}`}
              style={{ color: doneSteps.has(step) ? undefined : 'rgba(255,255,255,0.15)' }}
            >
              {step}
            </span>
            {i < PIPELINE_ALL.length - 1 && (
              <span className="text-[10px] mx-0.5" style={{ color: 'rgba(255,255,255,0.1)' }}>→</span>
            )}
          </span>
        ))}
      </div>
    </div>
  )
}

function AgentRow({ agent }: { agent: AgentState }) {
  const opacity = agent.status === 'idle' ? 0.25 : agent.status === 'done' ? 0.5 : 1
  const borderColor = agent.status === 'working' ? 'rgba(255,255,255,0.3)' : 'rgba(255,255,255,0.1)'

  return (
    <div
      className="flex items-center gap-2.5 px-3 py-2.5 transition-all"
      style={{ border: `1px solid ${borderColor}`, opacity, background: agent.status === 'working' ? 'rgba(255,255,255,0.03)' : 'transparent' }}
    >
      <div className="relative flex-shrink-0">
        <div className="w-2 h-2 rounded-full" style={{ background: agent.color }} />
        {agent.status === 'working' && (
          <div
            className="absolute -inset-1 rounded-full"
            style={{
              border: `1px solid ${agent.color}`,
              animation: 'ping 2s ease-in-out infinite',
              opacity: 0.4,
            }}
          />
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[11px] font-semibold uppercase tracking-[1px]">{agent.name}</div>
        <div className="text-[9px] mt-px" style={{ color: 'rgba(255,255,255,0.4)' }}>
          {agent.status === 'working' ? 'trabajando...' : agent.status === 'done' ? 'completado' : 'en espera'}
        </div>
      </div>
      <div
        className="text-[8px] uppercase tracking-[1px] px-2 py-0.5"
        style={{
          border: '1px solid rgba(255,255,255,0.15)',
          color: agent.status === 'working' ? 'rgba(255,255,255,0.7)' : 'rgba(255,255,255,0.3)',
        }}
      >
        {agent.status}
      </div>
    </div>
  )
}

function MiniDesk({ style }: { style: React.CSSProperties }) {
  return (
    <div
      className="absolute rounded-sm"
      style={{ width: 40, height: 20, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)', ...style }}
    />
  )
}

function MiniAgent({ agent, style, label }: { agent: AgentState; style: React.CSSProperties; label: string }) {
  const headOpacity = agent.status === 'idle' ? 0.15 : agent.status === 'done' ? 0.3 : 1
  return (
    <div className="absolute flex flex-col items-center gap-0.5 z-10" style={style}>
      <div
        className="rounded-full"
        style={{
          width: 10, height: 10, background: agent.color, opacity: headOpacity,
          animation: agent.status === 'working' ? 'bob 1.5s ease-in-out infinite' : undefined,
        }}
      />
      <div className="rounded-b" style={{ width: 12, height: 7, background: agent.color, opacity: headOpacity * 0.5, borderRadius: '0 0 3px 3px' }} />
      <div className="text-[7px] uppercase tracking-[1px]" style={{ color: agent.status === 'working' ? agent.color : 'rgba(255,255,255,0.2)' }}>
        {label}
      </div>
    </div>
  )
}
