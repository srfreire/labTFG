import { useState, useEffect, useMemo, useRef } from "react";
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
const rt = (id: string, parent: string) => ({
  node: n(id, "tool", "run_tests", { toolType: "run_tests" }),
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
const agent = (id: string, label: string, parent: string) => ({
  node: n(id, "agent", label),
  edge: e(parent, id),
});
const sub = (id: string, label: string, parent: string, paradigm: string) => ({
  node: n(id, "sub_agent", label, { paradigm }),
  edge: e(parent, id),
});

const WAVES: DemoWave[] = [
  /* 0  */ [{ node: n("researcher", "agent", "Researcher") }],
  /* 1  */ [ws("ws1", "researcher"), ws("ws2", "researcher"), ws("ws3", "researcher"), ws("ws4", "researcher")],
  /* 2  */ [
    sub("dr1", "Deep Researcher", "researcher", "prospect theory"),
    sub("dr2", "Deep Researcher", "researcher", "game theory"),
    sub("dr3", "Deep Researcher", "researcher", "bounded rationality"),
  ],
  /* 3  */ [ws("dr1_ws1", "dr1"), ws("dr2_ws1", "dr2"), ws("dr3_ws1", "dr3")],
  /* 4  */ [ws("dr1_ws2", "dr1"), wf("dr2_wf", "dr2"), ws("dr3_ws2", "dr3")],
  /* 5  */ [wf("dr1_wf", "dr1"), file("dr2_f1", "game_theory.md", "dr2_wf"), wf("dr3_wf", "dr3")],
  /* 6  */ [file("dr1_f1", "prospect_theory.md", "dr1_wf"), file("dr3_f1", "bounded_rat.md", "dr3_wf")],
  /* 7  */ [wf("r_wf1", "researcher"), wf("r_wf2", "researcher"), wf("r_wf3", "researcher")],
  /* 8  */ [file("r_f1", "prospect_theory.md", "r_wf1"), file("r_f2", "game_theory.md", "r_wf2"), file("r_f3", "bounded_rat.md", "r_wf3")],
  /* 9  */ [out("r_o1", "research.md", "researcher", "research")],

  /* 10 */ [agent("fm1", "Formalizer", "researcher"), agent("fm2", "Formalizer", "researcher"), agent("fm3", "Formalizer", "researcher")],
  /* 11 */ [rf("fm1_rf", "fm1"), rf("fm2_rf", "fm2"), rf("fm3_rf", "fm3")],
  /* 12 */ [wf("fm1_wf", "fm1"), wf("fm2_wf", "fm2"), wf("fm3_wf", "fm3")],
  /* 13 */ [file("fm1_f1", "spec_prospect.json", "fm1_wf"), file("fm2_f1", "spec_game.json", "fm2_wf"), file("fm3_f1", "spec_bounded.json", "fm3_wf")],
  /* 14 */ [out("fm1_o1", "spec_prospect.json", "fm1", "formalize"), out("fm2_o1", "spec_game.json", "fm2", "formalize"), out("fm3_o1", "spec_bounded.json", "fm3", "formalize")],

  /* 15 */ [agent("rs1", "Reasoner", "researcher"), agent("rs2", "Reasoner", "researcher"), agent("rs3", "Reasoner", "researcher")],
  /* 16 */ [rf("rs1_rf", "rs1"), rf("rs2_rf", "rs2"), rf("rs3_rf", "rs3")],
  /* 17 */ [wf("rs1_wf", "rs1"), wf("rs2_wf", "rs2"), wf("rs3_wf", "rs3")],
  /* 18 */ [file("rs1_f1", "model_prospect.json", "rs1_wf"), file("rs2_f1", "model_game.json", "rs2_wf"), file("rs3_f1", "model_bounded.json", "rs3_wf")],
  /* 19 */ [out("rs1_o1", "model_prospect.json", "rs1", "reason"), out("rs2_o1", "model_game.json", "rs2", "reason"), out("rs3_o1", "model_bounded.json", "rs3", "reason")],

  /* 20 */ [agent("bd1", "Builder", "researcher"), agent("bd2", "Builder", "researcher"), agent("bd3", "Builder", "researcher")],
  /* 21 */ [rf("bd1_rf", "bd1"), rf("bd2_rf", "bd2"), rf("bd3_rf", "bd3")],
  /* 22 */ [rt("bd1_rt", "bd1"), rt("bd2_rt", "bd2"), rt("bd3_rt", "bd3")],
  /* 23 */ [wf("bd1_wf", "bd1"), wf("bd2_wf", "bd2"), wf("bd3_wf", "bd3")],
  /* 24 */ [file("bd1_f1", "agent_prospect.py", "bd1_wf"), file("bd2_f1", "agent_game.py", "bd2_wf"), file("bd3_f1", "agent_bounded.py", "bd3_wf")],
  /* 25 */ [out("bd1_o1", "agent_prospect.py", "bd1", "build"), out("bd2_o1", "agent_game.py", "bd2", "build"), out("bd3_o1", "agent_bounded.py", "bd3", "build")],
];

/* Pre-flatten with wave index */
const FLAT = WAVES.flatMap((wave, wi) =>
  wave.map((item) => ({ ...item, wave: wi })),
);

/* Wave at which each agent/sub-agent turns "done" */
const AGENT_DONE_AT: Record<string, number> = {
  researcher: WAVES.length,
  dr1: 7, dr2: 6, dr3: 7,
  fm1: 15, fm2: 15, fm3: 15,
  rs1: 20, rs2: 20, rs3: 20,
  bd1: WAVES.length, bd2: WAVES.length, bd3: WAVES.length,
};

/* ── Component ──────────────────────────────────────────────────── */

export default function DemoGraph({ onComplete }: { onComplete?: () => void }) {
  const [step, setStep] = useState(0);
  const firedRef = useRef(false);

  useEffect(() => {
    if (step >= WAVES.length) {
      if (!firedRef.current) {
        firedRef.current = true;
        onComplete?.();
      }
      return;
    }
    const t = setTimeout(
      () => setStep((s) => s + 1),
      step === 0 ? 200 : 100,
    );
    return () => clearTimeout(t);
  }, [step, onComplete]);

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
