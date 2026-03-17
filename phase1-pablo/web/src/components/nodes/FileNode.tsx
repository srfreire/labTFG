import { type NodeProps, type Node } from '@xyflow/react';
import NodeHandles from './NodeHandles';
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
    status === 'running' ? '#f59e0b' : status === 'done' ? '#22c55e' : status === 'error' ? '#ef4444' : 'rgba(255,255,255,0.15)';

  const S = 46;

  return (
    <div style={{ position: 'relative', width: S, height: S }}>
      <NodeHandles />
      <svg
        width={S}
        height={S}
        viewBox={`0 0 ${S} ${S}`}
        style={{ position: 'absolute', top: 0, left: 0 }}
        className={status === 'running' ? 'animate-running-ring' : ''}
      >
        <polygon
          points={`${S/2},1 ${S-1},${S/2} ${S/2},${S-1} 1,${S/2}`}
          fill="#090909"
          stroke={borderColor}
          strokeWidth="1"
        />
      </svg>
      <div style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: S,
        height: S,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <FileTypeLogo label={label as string} size={20} />
      </div>
    </div>
  );
}
