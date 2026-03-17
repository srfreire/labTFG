import { type NodeProps, type Node } from '@xyflow/react';
import { Search } from 'lucide-react';
import NodeHandles from './NodeHandles';

interface SearchNodeData {
  label: string;
  status: 'running' | 'done' | 'error';
  query: string;
  results?: string[];
  [key: string]: unknown;
}

type SearchNodeType = Node<SearchNodeData, 'search'>;

export default function SearchNode({ data }: NodeProps<SearchNodeType>) {
  const { status } = data;

  const borderColor =
    status === 'running' ? '#f59e0b' : status === 'done' ? '#22c55e' : status === 'error' ? '#ef4444' : 'rgba(255,255,255,0.15)';

  return (
    <div
      className={status === 'running' ? 'animate-running-ring' : ''}
      style={{
        width: 32,
        height: 32,
        borderRadius: '50%',
        border: `1px solid ${borderColor}`,
        background: '#090909',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <NodeHandles />
      <Search size={14} color="rgba(255,255,255,0.7)" />
    </div>
  );
}
