import { type NodeProps, type Node } from '@xyflow/react';
import { Facehash } from 'facehash';
import NodeHandles from './NodeHandles';
import { colorForName } from './faceColors';

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
  const borderColor =
    status === 'running' ? '#f59e0b' : status === 'done' ? '#22c55e' : status === 'error' ? '#ef4444' : (color || 'rgba(255,255,255,0.2)');

  return (
    <div
      className={`relative leading-none overflow-hidden${status === 'running' ? ' animate-running-ring' : ''}`}
      style={{ border: `2px solid ${borderColor}` }}
    >
      <NodeHandles />
      <Facehash
        name={label}
        size={80}
        colors={[colorForName(label)]}
        variant="solid"
        intensity3d="none"
        interactive={false}
        showInitial={false}
        enableBlink
        className="block"
      />
    </div>
  );
}
