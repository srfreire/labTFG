import { useState } from 'react';
import CodeBlock from '../shared/CodeBlock';
import type { ReviewBuildData } from '../../types';

interface ReviewBuildProps {
  data: ReviewBuildData;
  onSubmit: (response: {
    decisions: Record<string, { approved: boolean; feedback?: string }>;
  }) => void;
}

export default function ReviewBuild({ data, onSubmit }: ReviewBuildProps) {
  const [feedback, setFeedback] = useState('');
  const [showFeedback, setShowFeedback] = useState(false);

  const handleApprove = () => {
    const decisions: Record<string, { approved: boolean }> = {};
    for (const m of data.models) {
      decisions[m.slug] = { approved: true };
    }
    onSubmit({ decisions });
  };

  const handleReject = () => {
    const text = feedback.trim();
    if (!text) return;
    const decisions: Record<string, { approved: boolean; feedback?: string }> = {};
    for (const m of data.models) {
      decisions[m.slug] = { approved: false, feedback: text };
    }
    onSubmit({ decisions });
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <h2 className="text-[13px] uppercase tracking-[2px] mb-4 text-text-muted">
          Review Build
        </h2>

        {data.models.map((model) => (
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
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="p-4 space-y-3 border-t border-border">
        <div className="flex gap-2">
          <button
            className="text-[13px] uppercase tracking-[1px] font-medium bg-white text-black px-6 py-2 rounded-lg"
            onClick={handleApprove}
          >
            Aprobar
          </button>

          {!showFeedback && (
            <button
              className="text-[13px] uppercase tracking-[1px] font-medium text-accent-red px-6 py-2 rounded-lg bg-accent-red/6 hover:bg-accent-red/12"
              style={{ border: '1px solid rgba(239,68,68,0.25)' }}
              onClick={() => setShowFeedback(true)}
            >
              Rechazar
            </button>
          )}
        </div>

        {showFeedback && (
          <div className="space-y-2">
            <textarea
              className="w-full text-[13px] text-white bg-surface border border-text-ghost p-3 resize-y min-h-[80px] outline-none font-mono rounded-lg"
              placeholder="Feedback..."
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
            />
            <button
              className="text-[13px] uppercase tracking-[1px] font-medium bg-white text-black px-6 py-2 cursor-pointer rounded-lg disabled:opacity-30 disabled:cursor-not-allowed"
              disabled={!feedback.trim()}
              onClick={handleReject}
            >
              Enviar feedback
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
