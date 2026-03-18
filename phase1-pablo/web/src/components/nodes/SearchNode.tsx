import { type NodeProps, type Node } from '@xyflow/react';
import { Search } from 'lucide-react';
import NodeHandles from './NodeHandles';
import NodeTooltip from './NodeTooltip';

interface SearchNodeData {
  label: string;
  status: 'running' | 'done' | 'error';
  query: string;
  results?: string[];
  [key: string]: unknown;
}

type SearchNodeType = Node<SearchNodeData, 'search'>;

export default function SearchNode({ data }: NodeProps<SearchNodeType>) {
  const { label, status } = data;

  const borderColor =
    status === 'running' ? '#f59e0b' : status === 'done' ? '#22c55e' : status === 'error' ? '#ef4444' : 'var(--node-border)';

  return (
    <NodeTooltip label={label || 'Search'}>
      <div
        className={`w-[32px] h-[32px] rounded-full flex items-center justify-center${status === 'running' ? ' animate-running-ring' : ''}`}
        style={{
          border: `1px solid ${borderColor}`,
          background: 'var(--node-fill)',
          boxShadow: 'var(--node-shadow)',
        }}
      >
        <NodeHandles />
        <Search size={14} style={{ color: 'var(--node-icon)' }} />
      </div>
    </NodeTooltip>
  );
}
