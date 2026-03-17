import { Facehash } from 'facehash'
import type { AgentState, PipelineStep } from '../types'
import { TOOL_LABELS } from '../constants'

interface Props {
  agents: AgentState[]
  pipeline: PipelineStep[]
}

// Workers are all agents except Orchestrator
const WORKER_NAMES = ['Architect', 'Tracker', 'Analyst', 'Reporter']

function getToolLabel(tool: string): string {
  return TOOL_LABELS[tool] || tool
}

export function AgentPanel({ agents }: Props) {
  const workers = agents.filter(a => WORKER_NAMES.includes(a.name))

  return (
    <div className="flex flex-col h-full border-r" style={{ borderColor: 'rgba(255,255,255,0.2)' }}>
      {/* Agent list */}
      <div className="flex-1 p-4 border-b overflow-y-auto" style={{ borderColor: 'rgba(255,255,255,0.1)' }}>
        <div className="text-[9px] uppercase tracking-[2px] mb-3" style={{ color: 'rgba(255,255,255,0.4)' }}>
          Agentes
        </div>
        <div className="space-y-1">
          {agents.map(agent => (
            <AgentRow key={agent.name} agent={agent} />
          ))}
        </div>
      </div>

      {/* Lab floor — horizontal pipeline */}
      <div className="h-[100px] relative flex-shrink-0" style={{ background: '#050505' }}>
        {/* Pipeline track — dotted line */}
        <div
          className="absolute"
          style={{
            top: '50%', left: '12%', right: '8%',
            height: 0,
            borderTop: '1px dashed rgba(255,255,255,0.08)',
          }}
        />

        {/* Progress segments — fill between completed stations */}
        {workers.map((agent, i) => {
          if (i === 0) return null
          const prev = workers[i - 1]
          const active = (prev.status === 'done' || prev.status === 'working')
          if (!active) return null
          const fromLeft = 12 + (i - 1) * (80 / (workers.length - 1))
          const toLeft = 12 + i * (80 / (workers.length - 1))
          return (
            <div
              key={`seg-${i}`}
              className="absolute transition-all duration-700"
              style={{
                top: '50%', left: `${fromLeft}%`, width: `${toLeft - fromLeft}%`,
                height: 1,
                background: `linear-gradient(90deg, ${prev.color}40, ${agent.color}20)`,
              }}
            />
          )
        })}

        {/* Station dots */}
        {workers.map((agent, i) => {
          const left = 12 + i * (80 / (workers.length - 1))
          const active = agent.status === 'working' || agent.status === 'done'
          return (
            <div
              key={`station-${agent.name}`}
              className="absolute transition-all duration-500"
              style={{
                top: '50%', left: `${left}%`,
                transform: 'translate(-50%, -50%)',
                width: active ? 10 : 5,
                height: active ? 10 : 5,
                borderRadius: '50%',
                background: active ? agent.color + '30' : 'rgba(255,255,255,0.06)',
                border: `1px solid ${active ? agent.color + '50' : 'rgba(255,255,255,0.10)'}`,
                boxShadow: agent.status === 'working' ? `0 0 14px ${agent.color}30` : 'none',
              }}
            />
          )
        })}

        {/* Worker avatars — idle: spread evenly on the left, active: at their station */}
        {workers.map((agent, i) => {
          const stationLeft = 12 + i * (80 / (workers.length - 1))
          const atStation = agent.status === 'working' || agent.status === 'done'
          const idleLeft = 5 + i * 6
          const left = atStation ? stationLeft : idleLeft

          return (
            <div
              key={`worker-${agent.name}`}
              className="absolute z-10"
              style={{
                top: '50%', left: `${left}%`,
                transform: 'translate(-50%, -50%)',
                transition: 'all 0.8s cubic-bezier(0.4, 0, 0.2, 1)',
              }}
            >
              <div
                className="rounded-full overflow-hidden transition-all duration-300"
                style={{
                  width: 24, height: 24,
                  opacity: agent.status === 'working' ? 1 : agent.status === 'done' ? 0.6 : 0.35,
                  filter: agent.status === 'working' ? `drop-shadow(0 0 8px ${agent.color}60)` : 'none',
                  animation: agent.status === 'working' ? 'bob 1.5s ease-in-out infinite' : undefined,
                }}
              >
                <Facehash
                  name={agent.name}
                  size={24}
                  variant="solid"
                  colors={[agent.color]}
                  showInitial={false}
                  enableBlink={agent.status === 'working'}
                />
              </div>
            </div>
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
        <div className="rounded-full overflow-hidden" style={{ width: 24, height: 24 }}>
          <Facehash
            name={agent.name}
            size={24}
            variant={agent.name === 'Orchestrator' ? 'gradient' : 'solid'}
            colors={agent.name === 'Orchestrator' ? ['#94a3b8', '#64748b'] : [agent.color]}
            showInitial={false}
            enableBlink={isActive}
          />
        </div>
        {isActive && (
          <div
            className="absolute -inset-1 rounded-full"
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
        {isActive && agent.activeTool && (
          <div
            className="text-[8px] mt-0.5 truncate"
            style={{ color: agent.color + 'aa' }}
          >
            {getToolLabel(agent.activeTool)}
          </div>
        )}
      </div>
      <div
        className="text-[7px] uppercase tracking-[1px] px-1.5 py-0.5 transition-all duration-300 flex-shrink-0"
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

