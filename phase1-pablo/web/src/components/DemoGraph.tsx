import { useState, useEffect, useMemo } from "react";
import Graph from "./Graph";
import type { GraphNode, GraphEdge } from "../types";

/* ── Mock data: each wave = nodes that appear simultaneously ──── */

type DemoWave = Array<{
  node: Omit<GraphNode, "status">;
  edge?: GraphEdge;
}>;

const n = (
  id: string,
  kind: GraphNode["kind"],
  label: string,
  meta: Record<string, unknown> = {},
) => ({ id, kind, label, meta });

const e = (
  source: string,
  target: string,
  edge_kind: GraphEdge["edge_kind"] = "spawn",
): GraphEdge => ({ source, target, edge_kind });

const ws = (id: string, parent: string) => ({
  node: n(id, "tool", "web_search", { toolType: "web_search" }),
  edge: e(parent, id),
});
const rf = (id: string, parent: string) => ({
  node: n(id, "tool", "read_file", { toolType: "read_file" }),
  edge: e(parent, id),
});
const wf = (id: string, parent: string) => ({
  node: n(id, "tool", "write_file", { toolType: "write_file" }),
  edge: e(parent, id),
});
const file = (id: string, label: string, parent: string) => ({
  node: n(id, "file", label, { path: label }),
  edge: e(parent, id, "write"),
});
const out = (id: string, label: string, parent: string, stage: string) => ({
  node: n(id, "output", label, { stage, path: label }),
  edge: e(parent, id),
});

const WAVES: DemoWave[] = [
  /* 0  */ [{ node: n("researcher", "agent", "Researcher") }],
  /* 1  */ [ws("ws1", "researcher"), ws("ws2", "researcher"), ws("ws3", "researcher")],
  /* 2  */ [
    { node: n("dr1", "sub_agent", "Deep Researcher", { paradigm: "prospect theory" }), edge: e("researcher", "dr1") },
    { node: n("dr2", "sub_agent", "Deep Researcher", { paradigm: "game theory" }), edge: e("researcher", "dr2") },
  ],
  /* 3  */ [ws("dr1_ws1", "dr1"), ws("dr2_ws1", "dr2"), { node: n("formalizer", "agent", "Formalizer"), edge: e("researcher", "formalizer") }],
  /* 4  */ [ws("dr1_ws2", "dr1"), wf("dr2_wf", "dr2"), rf("f_rf", "formalizer")],
  /* 5  */ [wf("dr1_wf", "dr1"), file("dr2_f1", "game_theory.md", "dr2_wf"), wf("f_wf", "formalizer")],
  /* 6  */ [file("dr1_f1", "prospect_theory.md", "dr1_wf"), file("f_f1", "formal_spec.json", "f_wf")],
  /* 7  */ [wf("r_wf1", "researcher"), wf("r_wf2", "researcher"), { node: n("reasoner", "agent", "Reasoner"), edge: e("researcher", "reasoner") }],
  /* 8  */ [file("r_f1", "prospect_theory.md", "r_wf1"), file("r_f2", "game_theory.md", "r_wf2"), rf("rs_rf", "reasoner")],
  /* 9  */ [wf("rs_wf", "reasoner"), out("r_o1", "research.md", "researcher", "research")],
  /* 10 */ [file("rs_f1", "model.json", "rs_wf"), out("f_o1", "spec.json", "formalizer", "formalize")],
  /* 11 */ [{ node: n("builder", "agent", "Builder"), edge: e("researcher", "builder") }, out("rs_o1", "model.json", "reasoner", "reason")],
  /* 12 */ [rf("b_rf", "builder"), { node: n("b_rt", "tool", "run_tests", { toolType: "run_tests" }), edge: e("builder", "b_rt") }, wf("b_wf", "builder")],
  /* 13 */ [file("b_f1", "agent.py", "b_wf"), out("b_o1", "agent.py", "builder", "build")],
];

/* Pre-flatten with wave index */
const FLAT = WAVES.flatMap((wave, wi) =>
  wave.map((item) => ({ ...item, wave: wi })),
);

/* Wave at which each agent/sub-agent turns "done" */
const AGENT_DONE_AT: Record<string, number> = {
  researcher: WAVES.length,
  dr1: 7,
  dr2: 6,
  formalizer: 11,
  reasoner: 12,
  builder: WAVES.length,
};

/* ── Component ──────────────────────────────────────────────────── */

export default function DemoGraph() {
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (step >= WAVES.length) return;
    const t = setTimeout(
      () => setStep((s) => s + 1),
      step === 0 ? 500 : 400,
    );
    return () => clearTimeout(t);
  }, [step]);

  const currentStep = Math.min(step, WAVES.length - 1);
  const allDone = step >= WAVES.length;

  const { nodes, edges } = useMemo(() => {
    const visible = FLAT.filter((item) => item.wave <= currentStep);

    const nodes: GraphNode[] = visible.map((item) => {
      let status: GraphNode["status"];
      if (allDone) {
        status = "done";
      } else if (item.wave === currentStep) {
        status = "running";
      } else if (item.node.id in AGENT_DONE_AT) {
        status =
          currentStep >= AGENT_DONE_AT[item.node.id] ? "done" : "running";
      } else {
        status = "done";
      }
      return { ...item.node, status } as GraphNode;
    });

    const nodeIds = new Set(nodes.map((nd) => nd.id));
    const edges: GraphEdge[] = visible
      .filter(
        (item) =>
          item.edge &&
          nodeIds.has(item.edge.source) &&
          nodeIds.has(item.edge.target),
      )
      .map((item) => item.edge!);

    return { nodes, edges };
  }, [currentStep, allDone]);

  return (
    <div className="w-full h-full">
      <Graph nodes={nodes} edges={edges} demo />
    </div>
  );
}
