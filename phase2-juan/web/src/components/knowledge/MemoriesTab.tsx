import { useState } from 'react'
import { useKnowledgeMemories } from '../../hooks/useKnowledgeMemories'

const NAMESPACES = ['', 'paradigm', 'formulation', 'model', 'meta'] as const
const MAX_PAGE_SIZE = 200
const DEFAULT_PAGE_SIZE = 50

export function MemoriesTab() {
  const [namespace, setNamespace] = useState<string>('')
  const [runId, setRunId] = useState('')
  const [since, setSince] = useState('')
  const [appliedFilters, setAppliedFilters] = useState({ namespace: '', runId: '', since: '' })
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data, loading, error } = useKnowledgeMemories({
    namespace: appliedFilters.namespace || undefined,
    runId: appliedFilters.runId || undefined,
    since: appliedFilters.since ? toIsoZ(appliedFilters.since) : undefined,
    page,
    pageSize,
  })

  function applyFilters(e: React.FormEvent) {
    e.preventDefault()
    setAppliedFilters({ namespace, runId: runId.trim(), since: since.trim() })
    setPage(1)
  }

  const total = data?.total ?? 0
  const lastPage = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="flex flex-col h-full min-h-0">
      <form
        className="grid grid-cols-2 gap-2 px-3 py-2 border-b border-border-subtle shrink-0"
        onSubmit={applyFilters}
      >
        <select
          value={namespace}
          onChange={e => setNamespace(e.target.value)}
          className="bg-transparent border border-border-subtle rounded-[var(--radius-sm)] px-2 py-1 text-[11px] text-text focus:outline-none"
        >
          {NAMESPACES.map(ns => (
            <option key={ns} value={ns} className="bg-surface text-text">
              {ns || 'all namespaces'}
            </option>
          ))}
        </select>
        <input
          type="number"
          min={1}
          max={MAX_PAGE_SIZE}
          value={pageSize}
          onChange={e => setPageSize(clamp(Number(e.target.value), 1, MAX_PAGE_SIZE))}
          className="bg-transparent border border-border-subtle rounded-[var(--radius-sm)] px-2 py-1 text-[11px] text-text focus:outline-none"
          title="page size (max 200)"
        />
        <input
          type="text"
          placeholder="run_id (UUID)"
          value={runId}
          onChange={e => setRunId(e.target.value)}
          className="bg-transparent border border-border-subtle rounded-[var(--radius-sm)] px-2 py-1 text-[11px] text-text focus:outline-none"
        />
        <input
          type="datetime-local"
          value={since}
          onChange={e => setSince(e.target.value)}
          className="bg-transparent border border-border-subtle rounded-[var(--radius-sm)] px-2 py-1 text-[11px] text-text focus:outline-none"
          title="since"
        />
        <button
          type="submit"
          className="col-span-2 text-[10px] uppercase tracking-wider px-2 py-1 rounded-[var(--radius-sm)] border border-border-subtle text-text-muted hover:text-text"
        >
          Apply
        </button>
      </form>

      <div className="flex-1 min-h-0 overflow-auto">
        {error && (
          <Placeholder
            title="Memories unavailable"
            body="¿Está Postgres accesible y el backend levantado?"
          />
        )}
        {!error && data && data.items.length === 0 && (
          <Placeholder
            title="No memories yet"
            body="Lanza un experimento para escribir memorias del pipeline."
          />
        )}
        {!error && data && data.items.length > 0 && (
          <table className="w-full text-[10px] text-text-muted">
            <thead className="sticky top-0 bg-surface text-text-faint">
              <tr>
                <th className="text-left px-2 py-1 font-normal">created_at</th>
                <th className="text-left px-2 py-1 font-normal">namespace</th>
                <th className="text-left px-2 py-1 font-normal">type</th>
                <th className="text-left px-2 py-1 font-normal">content</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map(m => {
                const expanded = expandedId === m.id
                return (
                  <tr
                    key={m.id}
                    onClick={() => setExpandedId(expanded ? null : m.id)}
                    className="border-t border-border-subtle hover:bg-[color:var(--color-surface-elevated)] cursor-pointer"
                  >
                    <td className="px-2 py-1 align-top whitespace-nowrap">
                      {m.created_at?.slice(0, 19) ?? '—'}
                    </td>
                    <td className="px-2 py-1 align-top">{m.namespace}</td>
                    <td className="px-2 py-1 align-top">{m.memory_type}</td>
                    <td className="px-2 py-1 align-top">
                      {expanded ? (
                        <div className="whitespace-pre-wrap text-text">{m.content}</div>
                      ) : (
                        <div className="truncate max-w-[200px]">{m.content}</div>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      <div className="flex items-center gap-2 px-3 py-2 border-t border-border-subtle shrink-0 text-[10px] text-text-faint">
        <span>{loading ? 'Loading…' : `${total} memories`}</span>
        <div className="ml-auto flex items-center gap-1">
          <button
            type="button"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="px-2 py-0.5 rounded-[var(--radius-sm)] border border-border-subtle disabled:opacity-30 enabled:hover:text-text"
          >
            Prev
          </button>
          <span>
            {page} / {lastPage}
          </span>
          <button
            type="button"
            onClick={() => setPage(p => Math.min(lastPage, p + 1))}
            disabled={page >= lastPage}
            className="px-2 py-0.5 rounded-[var(--radius-sm)] border border-border-subtle disabled:opacity-30 enabled:hover:text-text"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  )
}

function Placeholder({ title, body }: { title: string; body: string }) {
  return (
    <div className="h-full flex items-center justify-center flex-col gap-1 text-center px-6">
      <div className="text-[13px] font-medium text-text">{title}</div>
      <div className="text-[11px] text-text-muted">{body}</div>
    </div>
  )
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n))
}

function toIsoZ(local: string): string {
  // <input type="datetime-local"> returns "YYYY-MM-DDTHH:MM" (no tz).
  // Treat as UTC for backend compatibility (FastAPI accepts Z-suffix).
  return `${local}:00Z`
}
