import { Facehash } from 'facehash'
import type { AgentState } from '../types'
import { TOOL_LABELS } from '../constants'

interface Props {
  agents: AgentState[]
}

function getToolLabel(tool: string): string {
  return TOOL_LABELS[tool] || tool
}

export function AgentPanel({ agents }: Props) {
  return (
    <div className="flex flex-col h-full border-r" style={{ borderColor: 'rgba(255,255,255,0.12)' }}>
      <div className="px-5 py-4">
        <div className="text-[9px] uppercase tracking-[3px] font-semibold" style={{ color: 'rgba(255,255,255,0.35)' }}>
          Pipeline
        </div>
      </div>
      <div className="flex-1 px-5 pb-5 overflow-y-auto">
        <div className="relative">
          {agents.map((agent, i) => (
            <PipelineNode key={agent.name} agent={agent} isLast={i === agents.length - 1} />
          ))}
        </div>
      </div>
    </div>
  )
}

function PipelineNode({ agent, isLast }: { agent: AgentState; isLast: boolean }) {
  const isActive = agent.status === 'working'
  const isDone = agent.status === 'done'
  const isIdle = agent.status === 'idle'

  const lineColor = isDone ? agent.color + '60' : 'rgba(255,255,255,0.15)'

  return (
    <div className="relative flex gap-4" style={{ paddingBottom: isLast ? 0 : 48 }}>
      {/* Vertical line */}
      {!isLast && (
        <div
          className="absolute left-[17px] top-[32px] transition-colors duration-500"
          style={{
            width: 2,
            height: 'calc(100% - 32px)',
            background: lineColor,
          }}
        />
      )}

      {/* Node dot + avatar */}
      <div className="relative flex-shrink-0 w-[34px] flex items-start justify-center pt-1">
        <div className="relative">
          <div
            className="rounded-full overflow-hidden transition-all duration-300"
            style={{
              width: isActive ? 34 : 28,
              height: isActive ? 34 : 28,
              opacity: isIdle ? 0.4 : 1,
              boxShadow: isActive ? `0 0 12px ${agent.color}30` : 'none',
            }}
          >
            <Facehash
              name={agent.name}
              size={isActive ? 34 : 28}
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
              style={{ background: '#000', border: `1.5px solid ${agent.color}` }}
            >
              <svg width="6" height="6" viewBox="0 0 6 6" fill="none">
                <path d="M1 3L2.5 4.5L5 1.5" stroke={agent.color} strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 pt-0.5">
        <div className="flex items-center gap-2">
          <span
            className="text-[11px] font-semibold uppercase tracking-[1.5px] transition-colors duration-300"
            style={{
              color: isActive ? agent.color : isDone ? 'rgba(255,255,255,0.7)' : 'rgba(255,255,255,0.3)',
            }}
          >
            {agent.name}
          </span>
          {isActive && (
            <span
              className="text-[8px] uppercase tracking-[1px] px-1.5 py-0.5"
              style={{
                color: agent.color,
                background: agent.color + '15',
                border: `1px solid ${agent.color}30`,
              }}
            >
              working
            </span>
          )}
        </div>
        {isActive && agent.activeTool && (
          <div
            className="text-[10px] mt-1 truncate font-mono"
            style={{ color: agent.color + 'aa' }}
          >
            {getToolLabel(agent.activeTool)}
          </div>
        )}
        {isDone && (
          <div className="text-[9px] mt-0.5" style={{ color: 'rgba(255,255,255,0.25)' }}>
            Completado
          </div>
        )}
      </div>
    </div>
  )
}
