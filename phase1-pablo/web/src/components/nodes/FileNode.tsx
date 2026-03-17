import { type NodeProps, type Node } from '@xyflow/react';
import { FileText } from 'lucide-react';
import NodeHandles from './NodeHandles';

interface FileNodeData {
  label: string;
  status: 'running' | 'done' | 'error';
  path: string;
  content?: string;
  isOutput?: boolean;
  [key: string]: unknown;
}

type FileNodeType = Node<FileNodeData, 'file'>;

function FileIcon({ label, size, color }: { label: string; size: number; color: string }) {
  const name = (label || '').toLowerCase();
  const inner = name.endsWith('.py')
    ? <><g transform="translate(4,10) scale(0.5)" stroke="none"><path fillRule="evenodd" clipRule="evenodd" d="M13.016 2C10.82 2 9.038 3.725 9.038 5.852V8.519h6.885v.74H5.978C3.781 9.259 2 10.984 2 13.111v5.778c0 2.127 1.781 3.852 3.978 3.852h2.295v-3.26c0-2.127 1.781-3.852 3.978-3.852h7.344c1.86 0 3.366-1.459 3.366-3.26V5.853C22.962 3.725 21.18 2 18.984 2h-5.968zm-.918 4.741c.76 0 1.377-.597 1.377-1.333 0-.737-.616-1.334-1.377-1.334-.76 0-1.377.597-1.377 1.334 0 .736.616 1.333 1.377 1.333z" fill={color} /><path fillRule="evenodd" clipRule="evenodd" d="M18.983 30c2.197 0 3.978-1.725 3.978-3.852v-2.667h-6.885v-.74h9.946C28.219 22.74 30 21.016 30 18.889v-5.778C30 10.984 28.219 9.26 26.022 9.26h-2.295v3.26c0 2.127-1.781 3.851-3.978 3.851h-7.345c-1.859 0-3.366 1.46-3.366 3.26v6.518c0 2.128 1.781 3.852 3.978 3.852h5.968zm.918-4.741c-.76 0-1.377.597-1.377 1.333 0 .737.617 1.334 1.377 1.334.76 0 1.377-.597 1.377-1.334 0-.736-.616-1.333-1.377-1.333z" fill={color} /></g></>
    : name.endsWith('.json')
    ? <text x="12" y="18" textAnchor="middle" fill={color} stroke="none" fontSize="8" fontFamily="monospace" fontWeight="bold">{'{}'}</text>
    : name.endsWith('.md')
    ? <text x="12" y="18" textAnchor="middle" fill={color} stroke="none" fontSize="7" fontFamily="monospace" fontWeight="bold">md</text>
    : <><line x1="16" y1="13" x2="8" y2="13" stroke={color} /><line x1="16" y1="17" x2="8" y2="17" stroke={color} /></>;

  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      {inner}
    </svg>
  );
}

export default function FileNode({ data }: NodeProps<FileNodeType>) {
  const { label, status, isOutput } = data;

  const borderColor =
    status === 'running' ? '#f59e0b' : status === 'done' ? '#22c55e' : status === 'error' ? '#ef4444' : 'rgba(255,255,255,0.15)';

  if (isOutput) {
    const S = 48;
    const H = Math.round(S * 2 / Math.sqrt(3));
    return (
      <div style={{ position: 'relative', width: S, height: H }}>
        <NodeHandles />
        <svg width={S} height={H} viewBox={`0 0 ${S} ${H}`} style={{ position: 'absolute', top: 0, left: 0 }}>
          <polygon
            points={`${S/2},1 ${S-1},${H*0.25} ${S-1},${H*0.75} ${S/2},${H-1} 1,${H*0.75} 1,${H*0.25}`}
            fill="#090909"
            stroke={borderColor}
            strokeWidth="1"
            className={status === 'done' ? 'animate-output-glow' : status === 'running' ? 'animate-running-ring' : ''}
          />
        </svg>
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: S,
          height: H,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: status === 'done' ? 'pointer' : 'default',
        }}>
          <span style={{ fontSize: 12, fontFamily: 'monospace', fontWeight: 'bold', color: '#fff' }}>
            {(label as string).toLowerCase().endsWith('.py') ? '.py' : (label as string).toLowerCase().endsWith('.json') ? '{}' : 'md'}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={status === 'running' ? 'animate-running-ring' : ''}
      style={{
        width: 32,
        height: 32,
        borderRadius: '50%',
        border: `1px solid ${borderColor}`,
        background: '#090909',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <NodeHandles />
      <FileIcon label={label as string} size={14} color="rgba(255,255,255,0.7)" />
    </div>
  );
}
