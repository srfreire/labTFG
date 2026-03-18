import { useState } from 'react';
import MarkdownRenderer from '../shared/MarkdownRenderer';
import type { ReviewReasonData } from '../../types';

interface ReviewReasonProps {
  data: ReviewReasonData;
  onSubmit: (response: {
    decisions: Record<string, { approved: boolean; feedback?: string }>;
  }) => void;
}

type Decision = { approved: true } | { approved: false; feedback: string };

export default function ReviewReason({ data, onSubmit }: ReviewReasonProps) {
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [feedbackDrafts, setFeedbackDrafts] = useState<Record<string, string>>({});

  const approve = (id: string) => {
    setDecisions((prev) => ({ ...prev, [id]: { approved: true } }));
  };

  const reject = (id: string) => {
    const feedback = feedbackDrafts[id]?.trim();
    if (!feedback) return;
    setDecisions((prev) => ({
      ...prev,
      [id]: { approved: false, feedback },
    }));
  };

  const isRejecting = (id: string) =>
    decisions[id]?.approved === false || (!(id in decisions) && feedbackDrafts[id] !== undefined);

  const allDecided = data.specs.every((s) => s.id in decisions);

  const handleSubmit = () => {
    const result: Record<string, { approved: boolean; feedback?: string }> = {};
    for (const [id, d] of Object.entries(decisions)) {
      result[id] = d.approved ? { approved: true } : { approved: false, feedback: (d as { feedback: string }).feedback };
    }
    onSubmit({ decisions: result });
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        <h2 className="text-[11px] uppercase tracking-[2px] mb-4 text-text-muted">
          Review Reason
        </h2>

        {data.specs.map((spec) => {
          const decided = spec.id in decisions;
          const wasApproved = decisions[spec.id]?.approved === true;

          return (
            <div
              key={spec.id}
              className="bg-surface p-3 space-y-2"
              style={{
                border: `1px solid ${decided ? (wasApproved ? 'rgba(100,255,100,0.3)' : 'rgba(255,100,100,0.3)') : 'rgba(255,255,255,0.1)'}`,
              }}
            >
              {/* Header */}
              <div className="flex items-center gap-2">
                <span className="text-[12px] text-white font-medium">{spec.name}</span>
                <span
                  className="text-[9px] uppercase tracking-[1px] px-2 py-0.5 border text-text-muted"
                  style={{ borderColor: 'rgba(255,255,255,0.15)' }}
                >
                  {spec.paradigm}
                </span>
              </div>

              {/* Description */}
              <div className="text-[11px] text-text-muted">
                <MarkdownRenderer content={spec.description} />
              </div>

              {/* Variables */}
              {spec.variables?.length > 0 && (
                <div className="space-y-1">
                  <span className="text-[9px] uppercase tracking-[1px] text-text-faint">
                    Variables
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {spec.variables.map((v: any, i: number) => (
                      <span
                        key={i}
                        className="text-[10px] px-2 py-0.5 border text-text-muted"
                        style={{ borderColor: 'rgba(255,255,255,0.15)' }}
                      >
                        {typeof v === 'string' ? v : v.name || JSON.stringify(v)}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Parameters */}
              {spec.parameters?.length > 0 && (
                <div className="space-y-1">
                  <span className="text-[9px] uppercase tracking-[1px] text-text-faint">
                    Parameters
                  </span>
                  <div className="flex flex-wrap gap-1">
                    {spec.parameters.map((p: any, i: number) => (
                      <span
                        key={i}
                        className="text-[10px] px-2 py-0.5 border text-text-muted"
                        style={{ borderColor: 'rgba(255,255,255,0.15)' }}
                      >
                        {typeof p === 'string' ? p : p.name || JSON.stringify(p)}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Decision logic */}
              {spec.decision_logic && (
                <div className="space-y-1">
                  <span className="text-[9px] uppercase tracking-[1px] text-text-faint">
                    Decision logic
                  </span>
                  <div className="text-[10px] text-text-muted">
                    {typeof spec.decision_logic === 'string'
                      ? spec.decision_logic
                      : JSON.stringify(spec.decision_logic, null, 2)}
                  </div>
                </div>
              )}

              {/* Action buttons */}
              {decided ? (
                <div
                  className="text-[10px] uppercase tracking-[1px] pt-1"
                  style={{ color: wasApproved ? 'rgba(100,255,100,0.7)' : 'rgba(255,100,100,0.7)' }}
                >
                  {wasApproved ? 'Aprobado' : 'Rechazado'}
                </div>
              ) : (
                <div className="flex items-start gap-2 pt-1">
                  <button
                    className="text-[11px] uppercase tracking-[1px] font-medium text-white border border-text-faint px-4 py-1.5 hover:bg-surface-hover"
                    onClick={() => approve(spec.id)}
                  >
                    Aprobar
                  </button>
                  <button
                    className="text-[11px] uppercase tracking-[1px] font-medium text-white px-4 py-1.5 hover:bg-[rgba(255,100,100,0.05)]"
                    style={{ border: '1px solid rgba(255,100,100,0.4)' }}
                    onClick={() =>
                      setFeedbackDrafts((prev) => ({ ...prev, [spec.id]: prev[spec.id] ?? '' }))
                    }
                  >
                    Rechazar
                  </button>
                </div>
              )}

              {/* Feedback textarea (shown when rejecting) */}
              {!decided && isRejecting(spec.id) && (
                <div className="space-y-2 pt-1">
                  <textarea
                    className="w-full text-[11px] text-white bg-surface border border-text-ghost p-3 resize-y min-h-[80px] outline-none font-mono"
                    placeholder="Feedback..."
                    value={feedbackDrafts[spec.id] || ''}
                    onChange={(e) =>
                      setFeedbackDrafts((prev) => ({ ...prev, [spec.id]: e.target.value }))
                    }
                  />
                  <button
                    className="text-[11px] uppercase tracking-[1px] font-medium text-white border border-text-faint px-4 py-1.5 hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed"
                    style={{ cursor: feedbackDrafts[spec.id]?.trim() ? 'pointer' : 'not-allowed' }}
                    disabled={!feedbackDrafts[spec.id]?.trim()}
                    onClick={() => reject(spec.id)}
                  >
                    Enviar feedback
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-border">
        <button
          className="text-[11px] uppercase tracking-[1px] font-medium text-white border border-text-faint px-6 py-2 hover:bg-surface-hover disabled:opacity-30 disabled:cursor-not-allowed"
          style={{ cursor: allDecided ? 'pointer' : 'not-allowed' }}
          disabled={!allDecided}
          onClick={handleSubmit}
        >
          Continuar
        </button>
      </div>
    </div>
  );
}
