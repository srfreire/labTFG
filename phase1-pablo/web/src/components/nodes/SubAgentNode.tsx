import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { Bot } from 'lucide-react';

interface SubAgentNodeData {
  label: string;
  status: 'running' | 'done' | 'error';
  color: string;
  paradigm?: string;
  output?: string;
  [key: string]: unknown;
}

type SubAgentNodeType = Node<SubAgentNodeData, 'sub_agent'>;

export default function SubAgentNode({ data }: NodeProps<SubAgentNodeType>) {
  const { label, status, color, paradigm } = data;

  const borderColor = status === 'error' ? '#ef4444' : color;
  const opacity = status === 'done' ? 0.7 : 1;

  return (
    <div
      className={status === 'running' ? 'animate-pulse-glow' : ''}
      style={{
        width: 56,
        height: 56,
        borderRadius: '50%',
        border: `2px solid ${borderColor}`,
        background: '#090909',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        opacity,
      }}
    >
      <Handle type="target" position={Position.Top} style={{ background: borderColor }} />
      <Bot size={18} color={color} />
      <span
        style={{
          fontSize: 9,
          textTransform: 'uppercase',
          letterSpacing: '1px',
          color: '#fff',
          marginTop: 2,
        }}
      >
        {label}
      </span>
      {paradigm && (
        <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.4)' }}>
          {paradigm}
        </span>
      )}
      <Handle type="source" position={Position.Bottom} style={{ background: borderColor }} />
    </div>
  );
}
