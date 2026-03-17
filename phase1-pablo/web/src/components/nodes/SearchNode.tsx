import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { Search } from 'lucide-react';

interface SearchNodeData {
  label: string;
  status: 'running' | 'done' | 'error';
  query: string;
  results?: string[];
  [key: string]: unknown;
}

type SearchNodeType = Node<SearchNodeData, 'search'>;

export default function SearchNode({ data }: NodeProps<SearchNodeType>) {
  const { query, results } = data;

  // Truncate query for display
  const displayQuery = query.length > 30 ? query.slice(0, 27) + '...' : query;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        height: 32,
        padding: '0 8px',
        maxWidth: 200,
        border: '1px solid rgba(255,255,255,0.15)',
        background: '#090909',
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: '#555' }} />
      <Search size={14} style={{ flexShrink: 0 }} />
      <span
        style={{
          fontSize: 9,
          color: 'rgba(255,255,255,0.7)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
        }}
      >
        {displayQuery}
      </span>
      {results && (
        <span
          style={{
            fontSize: 8,
            color: 'rgba(255,255,255,0.4)',
            flexShrink: 0,
            marginLeft: 'auto',
          }}
        >
          {results.length}
        </span>
      )}
    </div>
  );
}
