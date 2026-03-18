import { type NodeProps, type Node } from '@xyflow/react';
import NodeHandles from './NodeHandles';
import NodeTooltip from './NodeTooltip';
import FileTypeLogo from './FileTypeLogo';

interface FileNodeData {
  label: string;
  status: 'running' | 'done' | 'error';
  path: string;
  content?: string;
  [key: string]: unknown;
}

type FileNodeType = Node<FileNodeData, 'file'>;

export default function FileNode({ data }: NodeProps<FileNodeType>) {
  const { label, status } = data;

  const borderColor =
    status === 'running' ? '#f59e0b' : status === 'done' ? '#22c55e' : status === 'error' ? '#ef4444' : 'var(--node-border)';

  const S = 46;

  return (
    <NodeTooltip label={label}>
      <div className="relative w-[46px] h-[46px]">
        <NodeHandles />
        <svg
          width={S}
          height={S}
          viewBox={`0 0 ${S} ${S}`}
          className="absolute top-0 left-0 overflow-visible"
          style={{
            filter: `drop-shadow(0 2px 4px rgba(0,0,0,0.2))`,
            ...(status === 'running' ? { animation: 'running-drop 1.5s ease-in-out infinite' } : {}),
          }}
        >
          <path
            d="M 19.5,4.5 Q 23,1 26.5,4.5 L 41.5,19.5 Q 45,23 41.5,26.5 L 26.5,41.5 Q 23,45 19.5,41.5 L 4.5,26.5 Q 1,23 4.5,19.5 Z"
            fill="var(--node-fill)"
            stroke={borderColor}
            strokeWidth="1"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <FileTypeLogo label={label as string} size={20} />
        </div>
      </div>
    </NodeTooltip>
  );
}
