import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ReactFlow,
  type Node,
  type Edge,
  type NodeTypes,
  useNodesState,
  useEdgesState,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import ELK, { type ElkNode } from 'elkjs/lib/elk.bundled.js';
import { AgentNode, SubAgentNode, ToolNode, FileNode, SearchNode } from './nodes';
import { type GraphNode, type GraphEdge, AGENT_COLORS } from '../types';

const elk = new ELK();

const nodeTypes: NodeTypes = {
  agent: AgentNode,
  sub_agent: SubAgentNode,
  tool: ToolNode,
  file: FileNode,
  search: SearchNode,
};

const ELK_OPTIONS: Record<string, string> = {
  'elk.algorithm': 'layered',
  'elk.direction': 'DOWN',
  'elk.spacing.nodeNode': '50',
  'elk.layered.spacing.nodeNodeBetweenLayers': '80',
};

const NODE_SIZES: Record<string, { width: number; height: number }> = {
  agent: { width: 80, height: 80 },
  sub_agent: { width: 56, height: 56 },
  tool: { width: 120, height: 36 },
  file: { width: 140, height: 32 },
  search: { width: 200, height: 32 },
};

function toFlowNode(node: GraphNode): Node {
  return {
    id: node.id,
    type: node.kind,
    data: {
      label: node.label,
      status: node.status,
      color: AGENT_COLORS[node.label.toLowerCase()] || '#fff',
      ...node.meta,
    },
    position: { x: 0, y: 0 },
  };
}

function toFlowEdge(edge: GraphEdge): Edge {
  return {
    id: `${edge.source}-${edge.target}`,
    source: edge.source,
    target: edge.target,
    animated: true,
    style: { stroke: 'rgba(255,255,255,0.3)' },
  };
}

async function layoutGraph(nodes: Node[], edges: Edge[]): Promise<Node[]> {
  if (nodes.length === 0) return [];

  const elkGraph: ElkNode = {
    id: 'root',
    layoutOptions: ELK_OPTIONS,
    children: nodes.map((n) => {
      const size = NODE_SIZES[n.type ?? 'agent'] ?? NODE_SIZES.agent;
      return {
        id: n.id,
        width: size.width,
        height: size.height,
      };
    }),
    edges: edges.map((e) => ({
      id: e.id,
      sources: [e.source],
      targets: [e.target],
    })),
  };

  const result = await elk.layout(elkGraph);

  const positionMap = new Map<string, { x: number; y: number }>();
  for (const child of result.children ?? []) {
    positionMap.set(child.id, { x: child.x ?? 0, y: child.y ?? 0 });
  }

  return nodes.map((n) => ({
    ...n,
    position: positionMap.get(n.id) ?? n.position,
  }));
}

interface GraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick?: (node: GraphNode) => void;
}

export default function Graph({ nodes, edges, onNodeClick }: GraphProps) {
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<Node>([]);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevCountRef = useRef(0);
  const graphNodesRef = useRef<GraphNode[]>(nodes);
  const [layoutReady, setLayoutReady] = useState(false);

  // Keep graphNodesRef in sync for click handler lookup
  useEffect(() => {
    graphNodesRef.current = nodes;
  }, [nodes]);

  // Convert and layout when node/edge count settles (debounced)
  useEffect(() => {
    const rfNodes = nodes.map(toFlowNode);
    const rfEdges = edges.map(toFlowEdge);

    // Always update edges immediately
    setFlowEdges(rfEdges);

    const countChanged = nodes.length !== prevCountRef.current;
    prevCountRef.current = nodes.length;

    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    if (countChanged && nodes.length > 0) {
      // Debounce layout when node count changes
      debounceRef.current = setTimeout(() => {
        layoutGraph(rfNodes, rfEdges).then((laid) => {
          setFlowNodes(laid);
          setLayoutReady(true);
        });
      }, 500);
    } else if (nodes.length > 0) {
      // Node data changed (status update) but count is same — update in place, no re-layout
      setFlowNodes((prev) => {
        const dataMap = new Map(rfNodes.map((n) => [n.id, n.data]));
        return prev.map((n) => {
          const newData = dataMap.get(n.id);
          return newData ? { ...n, data: newData } : n;
        });
      });
    } else {
      // Empty graph
      setFlowNodes([]);
      setLayoutReady(false);
    }

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [nodes, edges, setFlowNodes, setFlowEdges]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      if (!onNodeClick) return;
      const original = graphNodesRef.current.find((n) => n.id === node.id);
      if (original) onNodeClick(original);
    },
    [onNodeClick],
  );

  return (
    <div style={{ width: '100%', height: '100%', background: '#000' }}>
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        fitView={layoutReady}
        minZoom={0.3}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        style={{ background: '#000' }}
      />
    </div>
  );
}
