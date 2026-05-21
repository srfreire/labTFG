import { useState } from 'react';
import CodeBlock from '../shared/CodeBlock';
import type { ReviewBuildData } from '../../types';

interface ReviewBuildProps {
  data: ReviewBuildData;
  onSubmit: (response: {
    decisions: Record<
      string,
      { approved?: boolean; feedback?: string; rerun_reasoner?: boolean }
    >;
  }) => void;
}

export default function ReviewBuild({ data, onSubmit }: ReviewBuildProps) {
  const [decisions, setDecisions] = useState<
    Record<
      string,
      { approved?: boolean; feedback?: string; rerun_reasoner?: boolean }
    >
  >({});
  const [feedbackDrafts, setFeedbackDrafts] = useState<Record<string, string>>({});
  const [rejecting, setRejecting] = useState<Record<string, boolean>>({});

  const approve = (slug: string) => {
    setDecisions((prev) => ({ ...prev, [slug]: { approved: true } }));
    setRejecting((prev) => ({ ...prev, [slug]: false }));
  };

  const reject = (slug: string) => {
    const text = feedbackDrafts[slug]?.trim();
    if (!text) return;
    setDecisions((prev) => ({
      ...prev,
      [slug]: { approved: false, feedback: text },
    }));
  };

  const rerunReasoner = (slug: string) => {
    const text = feedbackDrafts[slug]?.trim();
    setDecisions((prev) => ({
      ...prev,
      [slug]: text
        ? { rerun_reasoner: true, feedback: text }
        : { rerun_reasoner: true },
    }));
    setRejecting((prev) => ({ ...prev, [slug]: false }));
  };

  const allDecided = data.models.every((m) => m.slug in decisions);

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <h2 className="text-[13px] uppercase tracking-[2px] mb-4 text-text-muted">
          Review Build
        </h2>

        {data.models.map((model) => {
          const decision = decisions[model.slug];
          const isApproved = decision?.approved === true;
          const isReasonerRerun = !!decision?.rerun_reasoner;
          const hasProblems = model.status === 'invalid' || !!model.problems?.length;

          return (
          <div
            key={model.slug}
            className="bg-surface border border-border space-y-2 rounded-lg"
          >
            {/* Header */}
            <div className="flex items-center justify-between p-3 pb-0">
              <span className="text-[14px] text-white font-medium">{model.slug}</span>
              <span
                className="text-[12px] uppercase tracking-[1px]"
                style={{
                  color: model.passed ? 'rgba(100,255,100,0.8)' : 'rgba(255,100,100,0.8)',
                }}
              >
                {model.passed ? 'passed' : 'failed'}
              </span>
            </div>

            {hasProblems && (
              <div className="mx-3 border border-accent-red/25 bg-accent-red/6 p-3 text-[12px] text-text-muted rounded-lg">
                <span className="block text-[11px] uppercase tracking-[1px] text-accent-red mb-2">
                  Validation problems
                </span>
                <ul className="space-y-1">
                  {(model.problems ?? [{ detail: 'Build marked invalid.' }]).map(
                    (problem, i) => (
                      <li key={i}>
                        {String(
                          problem.detail ??
                            problem.message ??
                            JSON.stringify(problem),
                        )}
                      </li>
                    ),
                  )}
                </ul>
              </div>
            )}

            {/* Code */}
            <div className="px-3">
              <span className="text-[11px] uppercase tracking-[1px] text-text-faint">
                Code
              </span>
              <CodeBlock code={model.code} language="python" />
            </div>

            {/* Test results */}
            <div className="px-3 pb-3">
              <span className="text-[11px] uppercase tracking-[1px] text-text-faint">
                Test results
              </span>
              <div
                className="mt-1 text-[13px]"
                style={{
                  color: model.passed ? 'rgba(100,255,100,0.7)' : 'rgba(255,100,100,0.7)',
                }}
              >
                {model.passed ? (
                  <span>{model.test_results || 'All tests passed'}</span>
                ) : (
                  <CodeBlock code={model.test_results || 'Tests failed'} />
                )}
              </div>
            </div>

            <div className="px-3 pb-3 space-y-2">
              {decision ? (
                <div
                  className="text-[12px] uppercase tracking-[1px]"
                  style={{
                    color: isApproved
                      ? 'rgba(100,255,100,0.7)'
                      : isReasonerRerun
                        ? 'rgba(251,191,36,0.8)'
                        : 'rgba(255,100,100,0.7)',
                  }}
                >
                  {isApproved
                    ? 'Aprobado'
                    : isReasonerRerun
                      ? 'Rehacer razonamiento'
                      : 'Rechazado'}
                </div>
              ) : (
                <div className="flex flex-wrap gap-2">
                  <button
                    className="text-[13px] uppercase tracking-[1px] font-medium bg-white text-black px-4 py-1.5 rounded-lg"
                    onClick={() => approve(model.slug)}
                  >
                    Aprobar
                  </button>
                  <button
                    className="text-[13px] uppercase tracking-[1px] font-medium text-accent-red px-4 py-1.5 rounded-lg bg-accent-red/6 hover:bg-accent-red/12"
                    style={{ border: '1px solid rgba(239,68,68,0.25)' }}
                    onClick={() =>
                      setRejecting((prev) => ({ ...prev, [model.slug]: true }))
                    }
                  >
                    Rechazar
                  </button>
                  {hasProblems && (
                    <button
                      className="text-[13px] uppercase tracking-[1px] font-medium text-[#fbbf24] px-4 py-1.5 rounded-lg bg-[#fbbf24]/6 hover:bg-[#fbbf24]/12"
                      style={{ border: '1px solid rgba(251,191,36,0.25)' }}
                      onClick={() => rerunReasoner(model.slug)}
                    >
                      Rehacer razonamiento
                    </button>
                  )}
                </div>
              )}

              {!decision && rejecting[model.slug] && (
                <div className="space-y-2">
                  <textarea
                    className="w-full text-[13px] text-white bg-surface border border-text-ghost p-3 resize-y min-h-[80px] outline-none font-mono rounded-lg"
                    placeholder="Feedback..."
                    value={feedbackDrafts[model.slug] || ''}
                    onChange={(e) =>
                      setFeedbackDrafts((prev) => ({
                        ...prev,
                        [model.slug]: e.target.value,
                      }))
                    }
                  />
                  <button
                    className="text-[13px] uppercase tracking-[1px] font-medium bg-white text-black px-4 py-1.5 cursor-pointer rounded-lg disabled:opacity-30 disabled:cursor-not-allowed"
                    disabled={!feedbackDrafts[model.slug]?.trim()}
                    onClick={() => reject(model.slug)}
                  >
                    Enviar feedback
                  </button>
                </div>
              )}
            </div>
          </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="p-4 border-t border-border">
        <button
          className="text-[13px] uppercase tracking-[1px] font-medium bg-white text-black px-6 py-2 cursor-pointer rounded-lg disabled:opacity-30 disabled:cursor-not-allowed"
          disabled={!allDecided}
          onClick={() => onSubmit({ decisions })}
        >
          Continuar
        </button>
      </div>
    </div>
  );
}
