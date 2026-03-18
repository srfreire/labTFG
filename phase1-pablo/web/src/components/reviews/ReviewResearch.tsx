import { useState } from 'react';
import MarkdownRenderer from '../shared/MarkdownRenderer';
import type { ReviewResearchData } from '../../types';

interface ReviewResearchProps {
  data: ReviewResearchData;
  onSubmit: (response: { approved: string[] }) => void;
}

function formatSlug(slug: string): string {
  return slug
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function ReviewResearch({ data, onSubmit }: ReviewResearchProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string | null>(null);

  const toggle = (slug: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(slug)) next.delete(slug);
      else next.add(slug);
      return next;
    });
  };

  const toggleExpand = (slug: string) => {
    setExpanded((prev) => (prev === slug ? null : slug));
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        <h2 className="text-[11px] uppercase tracking-[2px] mb-4 text-text-muted">
          Review Research
        </h2>

        {data.paradigms.map((p) => (
          <div
            key={p.slug}
            className="bg-surface"
            style={{
              border: `1px solid ${selected.has(p.slug) ? 'rgba(255,255,255,0.4)' : 'rgba(255,255,255,0.1)'}`,
            }}
          >
            {/* Header row */}
            <div
              className="flex items-center gap-3 p-3 cursor-pointer"
              onClick={() => toggleExpand(p.slug)}
            >
              {/* Checkbox */}
              <div
                className="w-4 h-4 flex-shrink-0 flex items-center justify-center cursor-pointer"
                style={{
                  border: '1px solid rgba(255,255,255,0.3)',
                  background: selected.has(p.slug) ? '#fff' : 'transparent',
                }}
                onClick={(e) => {
                  e.stopPropagation();
                  toggle(p.slug);
                }}
              >
                {selected.has(p.slug) && (
                  <span className="text-[10px] text-black font-bold leading-none">
                    &#10003;
                  </span>
                )}
              </div>

              <div className="flex-1 min-w-0">
                <div className="text-[12px] text-white font-medium">
                  {p.title || formatSlug(p.slug)}
                </div>
                {p.summary && (
                  <div className="text-[10px] mt-1 leading-relaxed text-text-dim">
                    {p.summary.slice(0, 200)}
                    {p.summary.length > 200 && '...'}
                  </div>
                )}
              </div>

              <span className="text-[10px] flex-shrink-0 text-text-faint">
                {expanded === p.slug ? '[-]' : '[+]'}
              </span>
            </div>

            {/* Expanded content */}
            {expanded === p.slug && p.content && (
              <div className="px-3 pb-3 border-t border-border-faint">
                <div className="pt-3">
                  <MarkdownRenderer content={p.content} className="text-[11px]" />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-border">
        <button
          className="text-[11px] uppercase tracking-[1px] font-medium text-white border border-text-faint px-6 py-2 hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed"
          style={{ cursor: selected.size === 0 ? 'not-allowed' : 'pointer' }}
          disabled={selected.size === 0}
          onClick={() => onSubmit({ approved: Array.from(selected) })}
        >
          Continuar
        </button>
      </div>
    </div>
  );
}
