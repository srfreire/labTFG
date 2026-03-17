import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { Bot } from 'lucide-react';

interface AgentNodeData {
  label: string;
  status: 'running' | 'done' | 'error';
  color: string;
  output?: string;
  [key: string]: unknown;
}

type AgentNodeType = Node<AgentNodeData, 'agent'>;

export default function AgentNode({ data }: NodeProps<AgentNodeType>) {
  const { label, status, color } = data;

  const borderColor = status === 'error' ? '#ef4444' : color;
  const opacity = status === 'done' ? 0.7 : 1;

  return (
    <div
      className={status === 'running' ? 'animate-pulse-glow' : ''}
      style={{
        width: 80,
        height: 80,
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
      <Bot size={24} color={color} />
      <span
        style={{
          fontSize: 10,
          textTransform: 'uppercase',
          letterSpacing: '1px',
          color: '#fff',
          marginTop: 4,
        }}
      >
        {label}
      </span>
      <Handle type="source" position={Position.Bottom} style={{ background: borderColor }} />
    </div>
  );
}
