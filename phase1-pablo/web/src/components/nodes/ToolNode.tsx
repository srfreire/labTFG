import { type NodeProps, type Node } from '@xyflow/react';
import {
  Globe,
  Eye,
  Pencil,
  FlaskConical,
  Microscope,
  Wrench,
} from 'lucide-react';
import type { ComponentType } from 'react';
import NodeHandles from './NodeHandles';

const TOOL_ICON_MAP: Record<string, ComponentType<{ size: number }>> = {
  web_search: Globe,
  read_file: Eye,
  write_file: Pencil,
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
  const { status, toolType } = data;
  const Icon = TOOL_ICON_MAP[toolType] ?? Wrench;

  const borderColor =
    status === 'running' ? '#f59e0b' : status === 'done' ? '#22c55e' : status === 'error' ? '#ef4444' : 'rgba(255,255,255,0.2)';

  return (
    <div
      className={status === 'running' ? 'animate-running-ring' : ''}
      style={{
        width: 36,
        height: 36,
        borderRadius: '50%',
        border: `1px solid ${borderColor}`,
        background: '#090909',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <NodeHandles />
      <Icon size={16} />
    </div>
  );
}
