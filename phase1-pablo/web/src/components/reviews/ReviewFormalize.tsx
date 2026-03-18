import { useState } from 'react';
import MarkdownRenderer from '../shared/MarkdownRenderer';
import type { ReviewFormalizeData } from '../../types';

interface ReviewFormalizeProps {
  data: ReviewFormalizeData;
  onSubmit: (response: { selected: Record<string, number[]> }) => void;
}

export default function ReviewFormalize({ data, onSubmit }: ReviewFormalizeProps) {
  const [selections, setSelections] = useState<Record<string, Set<number>>>({});
  const [expandedParadigm, setExpandedParadigm] = useState<string | null>(
    data.paradigms.length > 0 ? data.paradigms[0].slug : null,
  );

  const toggleFormulation = (slug: string, id: number) => {
    setSelections((prev) => {
      const current = new Set(prev[slug] || []);
      if (current.has(id)) current.delete(id);
      else current.add(id);
      return { ...prev, [slug]: current };
    });
  };

  const isChecked = (slug: string, id: number) =>
    selections[slug]?.has(id) ?? false;

  const hasAnySelection = Object.values(selections).some((s) => s.size > 0);

  const handleSubmit = () => {
    const result: Record<string, number[]> = {};
    for (const [slug, ids] of Object.entries(selections)) {
      if (ids.size > 0) result[slug] = Array.from(ids);
    }
    onSubmit({ selected: result });
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        <h2 className="text-[11px] uppercase tracking-[2px] mb-4 text-text-muted">
          Review Formalize
        </h2>

        {data.paradigms.map((p) => (
          <div
            key={p.slug}
            className="bg-surface border border-border rounded-lg"
          >
            {/* Paradigm header (accordion) */}
            <div
              className="flex items-center justify-between p-3 cursor-pointer"
              onClick={() =>
                setExpandedParadigm((prev) => (prev === p.slug ? null : p.slug))
              }
            >
              <span className="text-[12px] text-white font-medium">
                {p.title || p.slug}
              </span>
              <span className="text-[10px] text-text-faint">
                {expandedParadigm === p.slug ? '[-]' : '[+]'}
              </span>
            </div>

            {/* Formulation cards */}
            {expandedParadigm === p.slug && (
              <div className="px-3 pb-3 space-y-2 border-t border-border-faint">
                {p.formulations.map((f) => (
                  <div
                    key={f.id}
                    className="flex gap-3 p-3 cursor-pointer"
                    style={{
                      border: `1px solid ${
                        isChecked(p.slug, f.id)
                          ? 'rgba(255,255,255,0.4)'
                          : 'rgba(255,255,255,0.08)'
                      }`,
                      background: isChecked(p.slug, f.id)
                        ? 'rgba(255,255,255,0.02)'
                        : 'transparent',
                    }}
                    onClick={() => toggleFormulation(p.slug, f.id)}
                  >
                    {/* Checkbox */}
                    <div
                      className="w-4 h-4 flex-shrink-0 flex items-center justify-center mt-0.5 rounded-sm"
                      style={{
                        border: '1px solid rgba(255,255,255,0.3)',
                        background: isChecked(p.slug, f.id) ? '#fff' : 'transparent',
                      }}
                    >
                      {isChecked(p.slug, f.id) && (
                        <span className="text-[10px] text-black font-bold leading-none">
                          &#10003;
                        </span>
                      )}
                    </div>

                    <div className="flex-1 min-w-0">
                      <span className="text-[10px] uppercase tracking-[1px] text-text-faint">
                        Formulation {f.id}
                      </span>
                      <div className="mt-1">
                        <MarkdownRenderer content={f.content} className="text-[11px]" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-border">
        <button
          className="text-[11px] uppercase tracking-[1px] font-medium bg-white text-black px-6 py-2 cursor-pointer rounded-lg disabled:opacity-30 disabled:cursor-not-allowed"
          disabled={!hasAnySelection}
          onClick={handleSubmit}
        >
          Continuar
        </button>
      </div>
    </div>
  );
}
