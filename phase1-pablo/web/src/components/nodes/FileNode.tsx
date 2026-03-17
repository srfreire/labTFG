import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import { FileText, FilePlus } from 'lucide-react';

interface FileNodeData {
  label: string;
  status: 'running' | 'done' | 'error';
  path: string;
  content?: string;
  [key: string]: unknown;
}

type FileNodeType = Node<FileNodeData, 'file'>;

export default function FileNode({ data }: NodeProps<FileNodeType>) {
  const { label, path } = data;

  const isWrite = path.includes('write');
  const Icon = isWrite ? FilePlus : FileText;

  // Show only filename, not full path
  const filename = label.split('/').pop() ?? label;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        height: 32,
        padding: '0 8px',
        border: '1px solid rgba(255,255,255,0.15)',
        background: '#090909',
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: '#555' }} />
      <Icon size={14} />
      <span style={{ fontSize: 9, color: 'rgba(255,255,255,0.7)' }}>{filename}</span>
    </div>
  );
}
