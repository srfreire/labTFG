import { Facehash } from 'facehash'
import type { AgentState, SimAgent } from '../types'
import { TOOL_LABELS, withAlpha } from '../constants'

interface Props {
  agents: AgentState[]
  simAgents: SimAgent[]
}

function getToolLabel(tool: string): string {
  return TOOL_LABELS[tool] || tool
}

export function AgentPanel({ agents, simAgents }: Props) {
  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-5 py-3">
        <div className="text-[9px] uppercase tracking-[2px] font-semibold text-text-faint">
          Pipeline
        </div>
      </div>
      <div className="flex-1 px-5 pb-5 overflow-y-auto">
        <div className="relative pt-2.5">
          {agents.map((agent, i) => (
            <PipelineNode key={agent.name} agent={agent} isLast={i === agents.length - 1} />
          ))}
        </div>

        {/* Simulation agents */}
        {simAgents.length > 0 && (
          <div className="mt-4 pt-4 border-t border-border-subtle">
            <div className="text-[9px] uppercase tracking-[2px] font-semibold text-text-faint mb-3">
              Simulación
            </div>
            <div className="flex flex-col gap-2.5">
              {simAgents.map((sa, i) => (
                <div key={sa.id} className="flex items-center gap-2 animate-slide-up" style={{ animationDelay: `${200 + i * 200}ms` }}>
                  <div className="w-5 h-5 rounded-full overflow-hidden flex-shrink-0"
                    style={{ boxShadow: `0 0 8px ${sa.color}30` }}>
                    <Facehash
                      name={sa.id}
                      size={20}
                      variant="solid"
                      colors={[sa.color]}
                      showInitial={false}
                    />
                  </div>
                  <div className="min-w-0">
                    <div className="text-[10px] font-semibold truncate" style={{ color: sa.color }}>
                      {sa.id}
                    </div>
                    <div className="text-[8px] font-mono text-text-ghost">
                      {sa.color}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function nameColor(agent: AgentState): string {
  switch (agent.status) {
    case 'working': return agent.color
    case 'done': return 'var(--color-text-muted)'
    default: return 'var(--color-text-faint)'
  }
}

function contentMaxHeight(status: AgentState['status']): number {
  switch (status) {
    case 'working': return 50
    case 'done': return 20
    default: return 0
  }
}

function PipelineNode({ agent, isLast }: { agent: AgentState; isLast: boolean }) {
  const isActive = agent.status === 'working'
  const isDone = agent.status === 'done'
  const isIdle = agent.status === 'idle'

  const lineColor = isDone ? withAlpha(agent.color, '60') : 'var(--color-text-ghost)'

  return (
    <div className="relative flex gap-4 transition-all duration-300" style={{ paddingBottom: isLast ? 0 : 40 }}>
      {/* Vertical line */}
      {!isLast && (
        <div
          className="absolute left-[14px] top-[28px] transition-colors duration-500"
          style={{
            width: 2,
            height: 'calc(100% - 28px)',
            background: lineColor,
          }}
        />
      )}

      {/* Node dot + avatar */}
      <div className="relative flex-shrink-0 w-[28px] flex items-start justify-center pt-0.5">
        <div className="relative">
          <div
            className="rounded-full overflow-hidden transition-all duration-300"
            style={{
              width: isActive ? 28 : 24,
              height: isActive ? 28 : 24,
              opacity: isIdle ? 0.4 : 1,
              boxShadow: isActive ? `0 0 12px ${agent.color}30` : 'none',
            }}
          >
            <Facehash
              name={agent.name}
              size={isActive ? 28 : 24}
              variant={agent.name === 'Orchestrator' ? 'gradient' : 'solid'}
              colors={agent.name === 'Orchestrator' ? ['#94a3b8', '#64748b'] : [agent.color]}
              showInitial={false}
              enableBlink={isActive}
            />
          </div>
          {isActive && (
            <div
              className="absolute -inset-1.5 rounded-full"
              style={{
                border: `1.5px solid ${agent.color}`,
                animation: 'ping 2s ease-in-out infinite',
                opacity: 0.3,
              }}
            />
          )}
          {isDone && (
            <div
              className="absolute -right-0.5 -bottom-0.5 w-3 h-3 rounded-full flex items-center justify-center"
              style={{ background: 'var(--color-surface)', border: `1.5px solid ${agent.color}` }}
            >
              <svg width="6" height="6" viewBox="0 0 6 6" fill="none">
                <path d="M1 3L2.5 4.5L5 1.5" stroke={agent.color} strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 pt-0.5 overflow-hidden">
        <span
          className="text-[10px] font-semibold uppercase tracking-[1.5px] transition-colors duration-300 block truncate"
          style={{ color: nameColor(agent) }}
        >
          {agent.name}
        </span>
        <div
          className="overflow-hidden transition-all duration-300 ease-out"
          style={{ maxHeight: contentMaxHeight(agent.status), opacity: isIdle ? 0 : 1 }}
        >
          {isActive && (
            <div className="flex items-center gap-1.5 mt-1">
              <span
                className="text-[7px] uppercase tracking-[1px] px-1.5 py-0.5 rounded-[var(--radius-sm)] flex-shrink-0"
                style={{
                  color: agent.color,
                  background: withAlpha(agent.color, '15'),
                  border: `1px solid ${withAlpha(agent.color, '30')}`,
                }}
              >
                working
              </span>
            </div>
          )}
          {isActive && agent.activeTool && (
            <div
              className="text-[9px] mt-1 truncate font-mono"
              style={{ color: agent.color + 'aa' }}
            >
              {getToolLabel(agent.activeTool)}
            </div>
          )}
          {isDone && (
            <div className="text-[9px] mt-0.5 text-text-ghost">
              Completado
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
