import { type NodeProps, type Node } from '@xyflow/react';
import { Package } from 'lucide-react';
import NodeHandles from './NodeHandles';

interface OutputNodeData {
  label: string;
  status: 'running' | 'done' | 'error';
  stage?: string;
  [key: string]: unknown;
}

type OutputNodeType = Node<OutputNodeData, 'output'>;

export default function OutputNode({ data }: NodeProps<OutputNodeType>) {
  const { label, status } = data;

  const borderColor =
    status === 'done' ? '#22c55e' : status === 'error' ? '#ef4444' : 'rgba(255,255,255,0.2)';

  return (
    <div
      className={status === 'done' ? 'animate-output-glow' : ''}
      style={{
        width: 48,
        height: 48,
        borderRadius: '50%',
        border: `2px solid ${borderColor}`,
        background: '#090909',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <NodeHandles />
      <Package size={16} color={status === 'done' ? '#22c55e' : 'rgba(255,255,255,0.4)'} />
      <span style={{
        fontSize: 5,
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        color: status === 'done' ? '#22c55e' : 'rgba(255,255,255,0.3)',
        marginTop: 1,
      }}>
        {label}
      </span>
    </div>
  );
}
