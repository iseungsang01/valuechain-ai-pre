"use client";

import { useMemo } from "react";
import dagre from "dagre";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Building2, Factory, Store } from "lucide-react";
import type { SupplyChainGraph as SupplyChainGraphData, SupplyChainNode, NodeType } from "@/types";

interface SupplyChainGraphProps {
  graph: SupplyChainGraphData | null;
  isLoading: boolean;
  onEdgeClick?: (id: string) => void;
  onEdgeHover?: (id: string | null) => void;
  selectedEdgeId?: string | null;
}

const NODE_WIDTH = 200;
const NODE_HEIGHT = 92;

const nodeIcons: Record<NodeType, typeof Building2> = {
  TARGET: Building2,
  SUPPLIER: Factory,
  CUSTOMER: Store,
};

const nodeAccent: Record<NodeType, string> = {
  TARGET: "border-emerald-400/70 bg-emerald-500/10 shadow-emerald-500/20",
  SUPPLIER: "border-sky-400/60 bg-sky-500/10 shadow-sky-500/20",
  CUSTOMER: "border-violet-400/60 bg-violet-500/10 shadow-violet-500/20",
};

interface CompanyNodeData extends Record<string, unknown> {
  label: string;
  type: NodeType;
  reportedCogs?: number | null;
}

function CompanyNode({ data }: NodeProps) {
  const nodeData = data as CompanyNodeData;
  const Icon = nodeIcons[nodeData.type];
  return (
    <div
      className={`group relative w-[200px] rounded-xl border ${nodeAccent[nodeData.type]} px-4 py-3 shadow-lg backdrop-blur transition-transform duration-200 hover:scale-[1.02]`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-2 !w-2 !border-none !bg-white/40"
      />
      <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-zinc-300">
        <Icon className="h-3.5 w-3.5" />
        <span>{nodeData.type}</span>
      </div>
      <p className="mt-1 text-base font-semibold text-zinc-50">
        {nodeData.label}
      </p>
      {typeof nodeData.reportedCogs === "number" && (
        <p className="mt-1 text-[11px] text-zinc-400">
          COGS · {nodeData.reportedCogs.toLocaleString()} ₩
        </p>
      )}
      <Handle
        type="source"
        position={Position.Right}
        className="!h-2 !w-2 !border-none !bg-white/40"
      />
    </div>
  );
}

const nodeTypes = { company: CompanyNode };

const formatRevenue = (value: number) => {
  if (value >= 10000) return `${(value / 10000).toFixed(1)}조 ₩`;
  if (value >= 1) return `${value.toLocaleString()} ₩억`;
  return `${value.toLocaleString()} ₩`;
};

const computeLayout = (
  apiNodes: SupplyChainNode[],
  apiEdges: SupplyChainGraphData["edges"],
  selectedEdgeId?: string | null
): { nodes: Node[]; edges: Edge[] } => {
  if (apiNodes.length === 0) return { nodes: [], edges: [] };

  const targetNode = apiNodes.find(n => n.type === "TARGET");
  
  // 비중(%) 계산을 위한 총합 구하기
  let totalSupplierKrw = 0;
  let totalCustomerKrw = 0;
  
  if (targetNode) {
    for (const edge of apiEdges) {
      if (edge.target === targetNode.id) {
        totalSupplierKrw += Math.max(0, edge.estimated_revenue_krw);
      } else if (edge.source === targetNode.id) {
        totalCustomerKrw += Math.max(0, edge.estimated_revenue_krw);
      }
    }
  }

  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  dagreGraph.setGraph({ rankdir: "LR", nodesep: 60, ranksep: 120 });

  for (const node of apiNodes) {
    dagreGraph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of apiEdges) {
    dagreGraph.setEdge(edge.source, edge.target);
  }

  dagre.layout(dagreGraph);

  const nodes: Node[] = apiNodes.map((node) => {
    const positioned = dagreGraph.node(node.id);
    return {
      id: node.id,
      type: "company",
      position: {
        x: (positioned?.x ?? 0) - NODE_WIDTH / 2,
        y: (positioned?.y ?? 0) - NODE_HEIGHT / 2,
      },
      data: {
        label: node.name,
        type: node.type,
        reportedCogs: node.reported_cogs_krw ?? null,
      } satisfies CompanyNodeData,
    };
  });

  const edges: Edge[] = apiEdges.map((edge) => {
    const isSelected = edge.id === selectedEdgeId;
    const isOtherSelected = selectedEdgeId && !isSelected;
    
    const rawWidth = Math.log10(Math.max(0, edge.estimated_revenue_krw) + 10);
    const baseWidth = Math.min(Math.max(rawWidth, 1.5), 6);
    const strokeWidth = isSelected ? baseWidth + 1.5 : baseWidth;
    
    const strokeColor = isSelected ? "#ffffff" : (edge.has_conflict ? "#f59e0b" : "#52525b");
    const opacity = isOtherSelected ? 0.7 : 1;

    // 비중 계산
    let percentage = "";
    if (targetNode) {
      const val = Math.max(0, edge.estimated_revenue_krw);
      if (edge.target === targetNode.id && totalSupplierKrw > 0) {
        percentage = ` (${((val / totalSupplierKrw) * 100).toFixed(1)}%)`;
      } else if (edge.source === targetNode.id && totalCustomerKrw > 0) {
        percentage = ` (${((val / totalCustomerKrw) * 100).toFixed(1)}%)`;
      }
    }

    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      animated: edge.has_conflict,
      label: formatRevenue(edge.estimated_revenue_krw) + percentage,
      labelStyle: {
        fill: edge.has_conflict ? "#fbbf24" : "#e4e4e7",
        fontWeight: 500,
        fontSize: 11,
      },
      labelBgStyle: {
        fill: "rgba(9, 9, 11, 0.85)",
      },
      labelBgPadding: [6, 4],
      labelBgBorderRadius: 6,
      style: {
        stroke: strokeColor,
        strokeWidth,
        strokeDasharray: edge.has_conflict ? "6 4" : undefined,
        opacity,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        color: strokeColor,
      },
    };
  });

  return { nodes, edges };
};

function GraphInner({ graph, isLoading, onEdgeClick, onEdgeHover, selectedEdgeId }: SupplyChainGraphProps) {
  const { nodes, edges } = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] };
    console.log("Data collection resulted in graph structure:", graph);
    return computeLayout(graph.nodes, graph.edges, selectedEdgeId);
  }, [graph, selectedEdgeId]);

  if (!graph) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 px-8 text-center text-sm text-zinc-500">
        <div
          className={`grid grid-cols-3 gap-3 opacity-60 ${
            isLoading ? "animate-pulse" : ""
          }`}
        >
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div
              key={i}
              className="h-12 w-24 rounded-lg border border-white/10 bg-white/5"
            />
          ))}
        </div>
        <p>
          {isLoading
            ? "Synthesizing the quarterly supply chain network..."
            : "Run an analysis to render the supply chain graph here."}
        </p>
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onEdgeClick={(_, edge) => onEdgeClick?.(edge.id)}
      onEdgeMouseEnter={(_, edge) => onEdgeHover?.(edge.id)}
      onEdgeMouseLeave={() => onEdgeHover?.(null)}
      fitView
      fitViewOptions={{ padding: 0.25 }}
      proOptions={{ hideAttribution: true }}
      panOnScroll
      zoomOnScroll={false}
      zoomOnPinch
      defaultEdgeOptions={{ type: "smoothstep" }}
    >
      <Background
        variant={BackgroundVariant.Dots}
        gap={28}
        size={1}
        color="#27272a"
      />
      <MiniMap
        pannable
        zoomable
        nodeColor={(node) => {
          const data = (node.data ?? {}) as Partial<CompanyNodeData>;
          switch (data.type) {
            case "TARGET":
              return "#34d399";
            case "SUPPLIER":
              return "#38bdf8";
            case "CUSTOMER":
              return "#a78bfa";
            default:
              return "#52525b";
          }
        }}
        style={{
          backgroundColor: "rgba(9, 9, 11, 0.85)",
          border: "1px solid rgba(255,255,255,0.08)",
        }}
      />
      <Controls
        position="bottom-right"
        showInteractive={false}
        className="!rounded-lg !border !border-white/10 !bg-zinc-950/80 !shadow-none"
      />
    </ReactFlow>
  );
}

export function SupplyChainGraph(props: SupplyChainGraphProps) {
  return (
    <section
      aria-label="Supply chain graph"
      className="relative h-full w-full overflow-hidden rounded-2xl border border-white/10 bg-zinc-950/70"
    >
      <ReactFlowProvider>
        <GraphInner {...props} />
      </ReactFlowProvider>
    </section>
  );
}
