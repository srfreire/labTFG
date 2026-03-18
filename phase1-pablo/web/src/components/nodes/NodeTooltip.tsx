import type { ReactNode } from 'react';

export default function NodeTooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="group/tip relative">
      {children}
      <div className="pointer-events-none absolute left-1/2 -translate-x-1/2 top-[calc(100%+6px)] opacity-0 group-hover/tip:opacity-100 transition-opacity duration-150 whitespace-nowrap bg-surface border border-border rounded-md px-2 py-0.5 text-[10px] text-text shadow-lg z-50">
        {label}
      </div>
    </div>
  );
}
