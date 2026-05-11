import { useState } from 'react'
import { X } from 'lucide-react'
import { useKnowledgeGraph } from '../../hooks/useKnowledgeGraph'
import { GraphTab } from './GraphTab'

interface KnowledgePanelProps {
  onClose: () => void
}

type Tab = 'graph' | 'memories' | 'provenance'

export function KnowledgePanel({ onClose }: KnowledgePanelProps) {
  const [tab, setTab] = useState<Tab>('graph')
  const [runId, setRunId] = useState('')
  const { data, loading, error, refetch } = useKnowledgeGraph({
    runId: runId || undefined,
    enabled: tab === 'graph',
  })

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center px-4 py-3 border-b border-border-subtle shrink-0">
        <div className="text-[13px] font-semibold text-text">Knowledge</div>
        <button
          onClick={onClose}
          className="ml-auto p-1 rounded-[var(--radius-sm)] text-text-faint hover:text-text transition-colors"
          aria-label="Close knowledge panel"
        >
          <X size={14} />
        </button>
      </div>

      <div className="flex border-b border-border-subtle shrink-0">
        <TabButton active={tab === 'graph'} onClick={() => setTab('graph')}>Graph</TabButton>
        <TabButton active={tab === 'memories'} onClick={() => setTab('memories')}>Memories</TabButton>
        <TabButton active={tab === 'provenance'} onClick={() => setTab('provenance')}>Provenance</TabButton>
      </div>

      <div className="flex-1 min-h-0 overflow-hidden">
        {tab === 'graph' && (
          <GraphTab
            data={data}
            loading={loading}
            error={error}
            runId={runId}
            onRunIdChange={setRunId}
            onRefresh={refetch}
          />
        )}
        {tab === 'memories' && (
          <div className="p-6 text-[11px] text-text-muted">
            Memories tab — próximamente (P7-005).
          </div>
        )}
        {tab === 'provenance' && (
          <div className="p-6 text-[11px] text-text-muted">
            Provenance tab — próximamente (P7-005). Selecciona un nodo del Graph
            para ver su cadena de origen.
          </div>
        )}
      </div>
    </div>
  )
}

interface TabButtonProps {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}

function TabButton({ active, onClick, children }: TabButtonProps) {
  return (
    <button
      onClick={onClick}
      className="flex-1 px-3 py-2 text-[11px] uppercase tracking-wider transition-colors"
      style={{
        color: active ? 'var(--color-text)' : 'var(--color-text-faint)',
        borderBottom: active ? '2px solid var(--color-text)' : '2px solid transparent',
      }}
    >
      {children}
    </button>
  )
}
