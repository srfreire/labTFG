import { type NodeProps, type Node } from '@xyflow/react';
import NodeHandles from './NodeHandles';
import FileTypeLogo from './FileTypeLogo';

interface OutputNodeData {
  label: string;
  status: 'running' | 'done' | 'error';
  stage?: string;
  path?: string;
  content?: string;
  currentStage?: string;
  dismissed?: boolean;
  [key: string]: unknown;
}

type OutputNodeType = Node<OutputNodeData, 'output'>;

/**
 * Glow when the pipeline is reviewing THIS output's stage,
 * unless the user has already clicked (dismissed) this output.
 */
function shouldGlow(status: string, outputStage?: string, currentStage?: string, dismissed?: boolean): boolean {
  if (dismissed || status !== 'done' || !currentStage) return false;
  if (!outputStage) return currentStage.startsWith('review_');
  return currentStage === `review_${outputStage}`;
}

export default function OutputNode({ data }: NodeProps<OutputNodeType>) {
  const { label, status, stage, currentStage, dismissed } = data;

  const glow = shouldGlow(status, stage, currentStage, dismissed);

  const borderColor =
    status === 'done' ? '#22c55e' : status === 'running' ? '#f59e0b' : status === 'error' ? '#ef4444' : 'rgba(255,255,255,0.2)';

  const S = 48;
  const H = Math.round(S * 2 / Math.sqrt(3));

  return (
    <div className="relative" style={{ width: S, height: H }}>
      <NodeHandles />
      <svg
        width={S}
        height={H}
        viewBox={`0 0 ${S} ${H}`}
        className="absolute top-0 left-0 overflow-visible"
        style={
          glow
            ? { animation: 'output-glow 2s ease-in-out infinite' }
            : status === 'running'
              ? { animation: 'running-drop 1.5s ease-in-out infinite' }
              : undefined
        }
      >
        <polygon
          points={`${S/2},1 ${S-1},${H*0.25} ${S-1},${H*0.75} ${S/2},${H-1} 1,${H*0.75} 1,${H*0.25}`}
          fill="#090909"
          stroke={borderColor}
          strokeWidth="1.5"
        />
      </svg>
      <div
        className="absolute inset-0 flex items-center justify-center"
        style={{ cursor: status === 'done' ? 'pointer' : 'default' }}
      >
        <FileTypeLogo label={label as string} size={22} />
      </div>
    </div>
  );
}
