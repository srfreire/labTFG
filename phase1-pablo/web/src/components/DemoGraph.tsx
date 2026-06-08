import { useEffect, useMemo, useRef } from "react";
import {
  createTracer,
  useAgrexReplay,
  type AgrexEvent,
  type AgrexNode,
} from "@ppazosp/agrex";
import Graph from "./Graph";

/* ── Demo data ──────────────────────────────────────────────────── */

interface DemoNode {
  id: string;
  kind: AgrexNode["type"];
  label: string;
  parent?: string;
  reads?: string[];
  writes?: string[];
  metadata?: Record<string, unknown>;
}

const FIRST_WAVE_MS = 200;
const WAVE_MS = 100;

const ws = (id: string, parent: string): DemoNode => ({ id, kind: "tool", label: "web_search", parent });
const rt = (id: string, parent: string): DemoNode => ({ id, kind: "tool", label: "run_tests", parent });
const wf = (id: string, parent: string, writes: string[]): DemoNode => ({
  id, kind: "tool", label: "write_file", parent, writes,
});
const file = (id: string, name: string): DemoNode => ({
  id, kind: "file", label: name, metadata: { path: name },
});
const out = (id: string, name: string, parent: string, stage: string): DemoNode => ({
  id, kind: "output", label: name, parent, metadata: { stage, path: name },
});
const ag = (id: string, label: string, parent?: string, reads?: string[]): DemoNode => ({
  id, kind: "agent", label, parent, reads,
});
const sub = (id: string, label: string, parent: string, paradigm: string): DemoNode => ({
  id, kind: "sub_agent", label, parent, metadata: { paradigm },
});

const WAVES: DemoNode[][] = [
  /*  0 */ [ag("researcher", "Researcher")],
  /*  1 */ [ws("ws1", "researcher"), ws("ws2", "researcher"), ws("ws3", "researcher"), ws("ws4", "researcher")],
  /*  2 */ [
    sub("dr1", "Deep Researcher", "researcher", "prospect theory"),
    sub("dr2", "Deep Researcher", "researcher", "game theory"),
    sub("dr3", "Deep Researcher", "researcher", "bounded rationality"),
  ],
  /*  3 */ [ws("dr1_ws1", "dr1"), ws("dr2_ws1", "dr2"), ws("dr3_ws1", "dr3")],
  /*  4 */ [ws("dr1_ws2", "dr1"), wf("dr2_wf", "dr2", ["dr2_f1"]), ws("dr3_ws2", "dr3")],
  /*  5 */ [wf("dr1_wf", "dr1", ["dr1_f1"]), file("dr2_f1", "game_theory.md"), wf("dr3_wf", "dr3", ["dr3_f1"])],
  /*  6 */ [file("dr1_f1", "prospect_theory.md"), file("dr3_f1", "bounded_rat.md")],
  /*  7 */ [
    wf("r_wf1", "researcher", ["r_f1"]),
    wf("r_wf2", "researcher", ["r_f2"]),
    wf("r_wf3", "researcher", ["r_f3"]),
  ],
  /*  8 */ [file("r_f1", "prospect_theory.md"), file("r_f2", "game_theory.md"), file("r_f3", "bounded_rat.md")],
  /*  9 */ [out("r_o1", "research.md", "researcher", "research")],

  /* 10 */ [
    ag("fm1", "Formalizer", "researcher", ["r_f1"]),
    ag("fm2", "Formalizer", "researcher", ["r_f2"]),
    ag("fm3", "Formalizer", "researcher", ["r_f3"]),
  ],
  /* 11 */ [],
  /* 12 */ [wf("fm1_wf", "fm1", ["fm1_f1"]), wf("fm2_wf", "fm2", ["fm2_f1"]), wf("fm3_wf", "fm3", ["fm3_f1"])],
  /* 13 */ [file("fm1_f1", "spec_prospect.json"), file("fm2_f1", "spec_game.json"), file("fm3_f1", "spec_bounded.json")],
  /* 14 */ [
    out("fm1_o1", "spec_prospect.json", "fm1", "formalize"),
    out("fm2_o1", "spec_game.json", "fm2", "formalize"),
    out("fm3_o1", "spec_bounded.json", "fm3", "formalize"),
  ],

  /* 15 */ [
    ag("rs1", "Reasoner", "researcher", ["fm1_f1"]),
    ag("rs2", "Reasoner", "researcher", ["fm2_f1"]),
    ag("rs3", "Reasoner", "researcher", ["fm3_f1"]),
  ],
  /* 16 */ [],
  /* 17 */ [wf("rs1_wf", "rs1", ["rs1_f1"]), wf("rs2_wf", "rs2", ["rs2_f1"]), wf("rs3_wf", "rs3", ["rs3_f1"])],
  /* 18 */ [file("rs1_f1", "model_prospect.json"), file("rs2_f1", "model_game.json"), file("rs3_f1", "model_bounded.json")],
  /* 19 */ [
    out("rs1_o1", "model_prospect.json", "rs1", "reason"),
    out("rs2_o1", "model_game.json", "rs2", "reason"),
    out("rs3_o1", "model_bounded.json", "rs3", "reason"),
  ],

  /* 20 */ [
    ag("bd1", "Builder", "researcher", ["rs1_f1"]),
    ag("bd2", "Builder", "researcher", ["rs2_f1"]),
    ag("bd3", "Builder", "researcher", ["rs3_f1"]),
  ],
  /* 21 */ [],
  /* 22 */ [rt("bd1_rt", "bd1"), rt("bd2_rt", "bd2"), rt("bd3_rt", "bd3")],
  /* 23 */ [wf("bd1_wf", "bd1", ["bd1_f1"]), wf("bd2_wf", "bd2", ["bd2_f1"]), wf("bd3_wf", "bd3", ["bd3_f1"])],
  /* 24 */ [file("bd1_f1", "agent_prospect.py"), file("bd2_f1", "agent_game.py"), file("bd3_f1", "agent_bounded.py")],
  /* 25 */ [
    out("bd1_o1", "agent_prospect.py", "bd1", "build"),
    out("bd2_o1", "agent_game.py", "bd2", "build"),
    out("bd3_o1", "agent_bounded.py", "bd3", "build"),
  ],
];

// Long-running agents stay 'running' until their done wave; other nodes flip
// 'done' the wave after they appear (instant work).
const AGENT_DONE_AT: Record<string, number> = {
  researcher: WAVES.length,
  dr1: 7, dr2: 6, dr3: 7,
  fm1: 15, fm2: 15, fm3: 15,
  rs1: 20, rs2: 20, rs3: 20,
  bd1: WAVES.length, bd2: WAVES.length, bd3: WAVES.length,
};

/* ── Trace builder ──────────────────────────────────────────────── */

function buildDemoTrace(): AgrexEvent[] {
  let now = 0;
  const trace = createTracer({ clock: () => now });
  const transient: string[] = [];

  for (let wi = 0; wi <= WAVES.length; wi++) {
    if (wi > 0) now += wi === 1 ? FIRST_WAVE_MS : WAVE_MS;

    for (const id of transient) trace.done(id);
    transient.length = 0;

    for (const [id, doneWave] of Object.entries(AGENT_DONE_AT)) {
      if (doneWave === wi) trace.done(id);
    }

    if (wi === WAVES.length) break;

    for (const node of WAVES[wi]) {
      const init = {
        ...(node.parent ? { parent: node.parent } : {}),
        ...(node.reads ? { reads: node.reads } : {}),
        ...(node.writes ? { writes: node.writes } : {}),
        ...(node.metadata ? { metadata: node.metadata } : {}),
      };
      switch (node.kind) {
        case "agent":
          trace.agent(node.id, node.label, init);
          break;
        case "sub_agent":
          trace.subAgent(node.id, node.label, init);
          break;
        case "tool":
          trace.tool(node.id, node.label, init);
          break;
        case "file":
          trace.file(node.id, node.label, init);
          break;
        default:
          // `output` (and any future kinds without a helper) — escape hatch
          trace.node({
            id: node.id,
            type: node.kind,
            label: node.label,
            status: "running",
            ...(node.parent ? { parentId: node.parent } : {}),
            ...(node.metadata ? { metadata: node.metadata } : {}),
          });
      }
      if (node.kind !== "agent" && node.kind !== "sub_agent") {
        transient.push(node.id);
      }
    }
  }

  return trace.events();
}

/* ── Component ──────────────────────────────────────────────────── */

export default function DemoGraph({ onComplete }: { onComplete?: () => void }) {
  const events = useMemo(buildDemoTrace, []);
  const replay = useAgrexReplay({});
  const completedRef = useRef(false);

  // Load + play once on mount. Replay's methods close over a stable internal
  // store, so the captured `replay` from first render still hits the right
  // instance.
  useEffect(() => {
    void replay.load(events).then(() => replay.play());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (completedRef.current) return;
    if (events.length > 0 && replay.cursor >= events.length) {
      completedRef.current = true;
      onComplete?.();
    }
  }, [replay.cursor, events.length, onComplete]);

  return (
    // Demo graph is decorative. `pointer-events: none` alone isn't enough
    // because ReactFlow sets `pointer-events: all` on its node/handle
    // elements (nested override wins). `inert` disables the whole subtree
    // — no hover, click, focus, or keyboard — regardless of child CSS.
    <div className="w-full h-full select-none" inert>
      <Graph replay={replay} demo />
    </div>
  );
}
