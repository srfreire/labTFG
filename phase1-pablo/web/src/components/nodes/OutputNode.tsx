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
  [key: string]: unknown;
}

type OutputNodeType = Node<OutputNodeData, 'output'>;

/**
 * Glow only when the pipeline is reviewing THIS output's stage.
 * currentStage is "review_research" / "review_formalize" etc.
 * meta.stage is the production stage: "research" / "formalize" etc.
 */
function shouldGlow(status: string, outputStage?: string, currentStage?: string): boolean {
  if (status !== 'done' || !currentStage) return false;
  // If no stage tag on the output, glow during any review
  if (!outputStage) return currentStage.startsWith('review_');
  // Match: currentStage "review_research" → outputStage "research"
  return currentStage === `review_${outputStage}`;
}

export default function OutputNode({ data }: NodeProps<OutputNodeType>) {
  const { label, status, stage, currentStage } = data;

  const glow = shouldGlow(status, stage, currentStage);

  const borderColor =
    status === 'done' ? '#22c55e' : status === 'running' ? '#f59e0b' : status === 'error' ? '#ef4444' : 'rgba(255,255,255,0.2)';

  const S = 48;
  const H = Math.round(S * 2 / Math.sqrt(3));

  return (
    <div style={{ position: 'relative', width: S, height: H }}>
      <NodeHandles />
      <svg
        width={S}
        height={H}
        viewBox={`0 0 ${S} ${H}`}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          overflow: 'visible',
          ...(glow ? { animation: 'output-glow 2s ease-in-out infinite' } : {}),
        }}
      >
        <polygon
          points={`${S/2},1 ${S-1},${H*0.25} ${S-1},${H*0.75} ${S/2},${H-1} 1,${H*0.75} 1,${H*0.25}`}
          fill="#090909"
          stroke={borderColor}
          strokeWidth="1.5"
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
        <FileTypeLogo label={label as string} size={22} />
      </div>
    </div>
  );
}
