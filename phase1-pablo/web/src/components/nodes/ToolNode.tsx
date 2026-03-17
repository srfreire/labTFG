import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import {
  Search,
  FileText,
  FilePlus,
  FlaskConical,
  Microscope,
  Wrench,
} from 'lucide-react';
import type { ComponentType } from 'react';

const TOOL_ICON_MAP: Record<string, ComponentType<{ size: number }>> = {
  web_search: Search,
  read_file: FileText,
  write_file: FilePlus,
  run_tests: FlaskConical,
  launch_deep_research: Microscope,
};

interface ToolNodeData {
  label: string;
  status: 'running' | 'done' | 'error';
  toolType: string;
  args?: Record<string, unknown>;
  [key: string]: unknown;
}

type ToolNodeType = Node<ToolNodeData, 'tool'>;

export default function ToolNode({ data }: NodeProps<ToolNodeType>) {
  const { label, status, toolType } = data;
  const Icon = TOOL_ICON_MAP[toolType] ?? Wrench;

  const dotColor =
    status === 'running' ? '#f59e0b' : status === 'done' ? '#22c55e' : '#ef4444';

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        height: 36,
        padding: '0 10px',
        borderRadius: 4,
        border: '1px solid rgba(255,255,255,0.2)',
        background: '#090909',
        position: 'relative',
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: '#555' }} />

      <Icon size={14} />
      <span style={{ fontSize: 9, color: '#fff' }}>{label}</span>

      {/* status dot */}
      <span
        className={status === 'running' ? 'animate-pulse-glow' : ''}
        style={{
          position: 'absolute',
          top: 4,
          right: 4,
          width: 6,
          height: 6,
          borderRadius: '50%',
          background: dotColor,
        }}
      />

      <Handle type="source" position={Position.Right} style={{ background: '#555' }} />
    </div>
  );
}
