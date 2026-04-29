import { useCallback, useEffect, useReducer, useRef } from "react";
import {
  Stage,
  StageStatus,
  ServerMessage,
  ClientMessage,
  AgentState,
  MEMORY_STAGE_OF,
} from "../types";

/* ------------------------------------------------------------------ */
/*  State                                                              */
/* ------------------------------------------------------------------ */

// Note: graph nodes/edges are NOT held here — they live on `replay.instance`
// (driven by the agrex replay buffer in App.tsx). This reducer tracks only
// pipeline-stage progress and connection metadata.
interface WebSocketState {
  connected: boolean;
  stages: Record<Stage, StageStatus>;
  currentStage: Stage | null;
  reviewRequest: { stage: Stage; data: any } | null;
  isRunning: boolean;
  error: string | null;
  agents: AgentState[];
  runId: string | null;
}

function initStages(): Record<Stage, StageStatus> {
  const stages = {} as Record<Stage, StageStatus>;
  for (const s of Object.values(Stage)) {
    stages[s] = "pending";
  }
  return stages;
}

const INITIAL_STATE: WebSocketState = {
  connected: false,
  stages: initStages(),
  currentStage: null,
  reviewRequest: null,
  isRunning: false,
  error: null,
  agents: [],
  runId: null,
};

/* ------------------------------------------------------------------ */
/*  Reducer                                                            */
/* ------------------------------------------------------------------ */

type Action =
  | { type: "SET_CONNECTED"; connected: boolean }
  | { type: "SERVER_MSG"; msg: ServerMessage }
  | { type: "START_PIPELINE" }
  | { type: "CANCEL_PIPELINE" }
  | { type: "CLEAR_REVIEW" }
  | { type: "CLEAR_ERROR" };

function reducer(state: WebSocketState, action: Action): WebSocketState {
  switch (action.type) {
    case "SET_CONNECTED":
      return { ...state, connected: action.connected };

    case "SERVER_MSG":
      return handleServerMessage(state, action.msg);

    case "START_PIPELINE":
      return {
        ...state,
        isRunning: true,
        stages: initStages(),
        currentStage: null,
        reviewRequest: null,
        error: null,
        agents: [],
        runId: null,
      };

    case "CANCEL_PIPELINE":
      return {
        ...state,
        isRunning: false,
        currentStage: null,
        reviewRequest: null,
        agents: [],
      };

    case "CLEAR_REVIEW":
      return { ...state, reviewRequest: null };

    case "CLEAR_ERROR":
      return { ...state, error: null };

    default:
      return state;
  }
}

function handleServerMessage(
  state: WebSocketState,
  msg: ServerMessage,
): WebSocketState {
  switch (msg.type) {
    case "stage": {
      // A new work stage begins. We synthesize the lifecycle of the previous
      // stage's sub-stages (memory_*, review_*, get_env_spec) here because
      // backend events for those no longer travel on the wire — only the
      // four work stages emit `stage`, and reviews emit `marker`.
      const newStage = msg.label as Stage;
      const stages = { ...state.stages };
      const prev = state.currentStage;

      if (prev && prev !== newStage) {
        // Close the previous work stage.
        stages[prev] = "done";
        // Close any review_* still flagged "running" — entering a new work
        // stage means the prior review prompt was answered.
        for (const s of Object.values(Stage) as Stage[]) {
          if (s.startsWith("review_") && stages[s] === "running") {
            stages[s] = "done";
          }
        }
        // Close any memory_* lingering from a stage two-or-more steps back
        // (defensive — normally it was closed when its review marker fired).
        const memOfPrev = MEMORY_STAGE_OF[prev];
        for (const s of Object.values(Stage) as Stage[]) {
          if (
            s.startsWith("memory_") &&
            s !== memOfPrev &&
            stages[s] === "running"
          ) {
            stages[s] = "done";
          }
        }
        // Close GET_ENV_SPEC if we're now entering REASON.
        if (
          newStage === Stage.REASON &&
          stages[Stage.GET_ENV_SPEC] === "running"
        ) {
          stages[Stage.GET_ENV_SPEC] = "done";
        }
        // Light up the just-finished work stage's MEMORY_X — the backend
        // runs the Memory Agent synchronously between work and review, so
        // we trigger it here and close it on the matching review marker.
        if (memOfPrev) stages[memOfPrev] = "running";
      }

      stages[newStage] = "running";
      // Defensive reset: if a re-run loops back into a previously-touched
      // work stage, clear its sub-stage statuses so dots don't lie.
      const memOfNew = MEMORY_STAGE_OF[newStage];
      if (memOfNew) stages[memOfNew] = "pending";
      const reviewOfNew = `review_${newStage}` as Stage;
      if (stages[reviewOfNew] !== undefined) stages[reviewOfNew] = "pending";

      return { ...state, stages, currentStage: newStage };
    }

    case "marker": {
      // Review markers light up the matching REVIEW_X stage and close the
      // memory stage that ran synchronously just before the prompt.
      if (typeof msg.kind === "string" && msg.kind.startsWith("review_")) {
        const reviewStage = msg.kind as Stage;
        const stages = { ...state.stages };
        const work = msg.kind.slice("review_".length) as Stage;
        const memStage = MEMORY_STAGE_OF[work];
        if (memStage && stages[memStage] === "running") {
          stages[memStage] = "done";
        }
        stages[reviewStage] = "running";
        return { ...state, stages };
      }
      return state;
    }

    // Graph deltas (node_add / edge_add / node_update / graph_clear) flow
    // through to the agrex replay buffer in App.tsx — this hook no longer
    // mirrors them in its own state.

    case "review_request": {
      // GET_ENV_SPEC has no marker counterpart, so we light its sidebar dot
      // here (the backend emits a `review_request` for it). Other review
      // stages already have their dot lit by the `marker` arm above.
      const stages =
        msg.stage === Stage.GET_ENV_SPEC
          ? { ...state.stages, [Stage.GET_ENV_SPEC]: "running" as const }
          : state.stages;
      return {
        ...state,
        stages,
        reviewRequest: { stage: msg.stage, data: msg.data },
      };
    }

    case "rerun":
      // Rerun is informational; graph_clear handles visual reset
      return state;

    case "pipeline_done": {
      // Final sweep — close any stage still flagged "running" (the final
      // work stage, plus any lingering memory/review/get_env_spec dots that
      // synthesis may have left open).
      const stages = { ...state.stages };
      for (const s of Object.keys(stages) as Stage[]) {
        if (stages[s] === "running") {
          stages[s] = "done";
        }
      }
      return { ...state, isRunning: false, stages, currentStage: null };
    }

    case "error":
      return { ...state, error: msg.message };

    case "state_sync":
      // Reconnection snapshot: graph is restored via the replay buffer in
      // App.tsx; we only need the current stage marker here.
      return {
        ...state,
        currentStage: msg.stage,
      };

    case "agents":
      return {
        ...state,
        agents: msg.agents.map((a) => ({
          name: a.name,
          color: a.color,
          status: "idle" as const,
        })),
      };

    case "agent_status":
      return {
        ...state,
        agents: state.agents.map((a) =>
          a.name === msg.agent
            ? { ...a, status: msg.status, error: msg.error }
            : a,
        ),
      };

    case "agent_tool":
      return state;

    case "run_start":
      return { ...state, runId: msg.run_id };

    default:
      return state;
  }
}

/* ------------------------------------------------------------------ */
/*  Actions interface                                                  */
/* ------------------------------------------------------------------ */

interface WebSocketActions {
  send: (msg: ClientMessage) => void;
  startPipeline: (problem: string, untilStage?: Stage) => void;
  sendReviewResponse: (stage: Stage, data: any) => void;
  sendRouterPrompt: (message: string) => void;
  cancelPipeline: () => void;
  clearError: () => void;
}

/* ------------------------------------------------------------------ */
/*  Hook                                                               */
/* ------------------------------------------------------------------ */

const MAX_BACKOFF = 16_000;

export function useWebSocket(
  onServerMessage?: (msg: ServerMessage) => void,
): WebSocketState & WebSocketActions {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef = useRef(1000);
  // Track whether the hook is still mounted to avoid reconnects after unmount
  const mountedRef = useRef(true);
  // Stable ref to the latest callback, so the socket effect doesn't re-open
  // each render when the consumer passes a fresh closure.
  const onMessageRef = useRef(onServerMessage);
  onMessageRef.current = onServerMessage;

  /* ---------- connect / reconnect ---------- */

  const connect = useCallback(() => {
    // Prevent opening a new socket if one is already connecting or open
    if (
      wsRef.current &&
      (wsRef.current.readyState === WebSocket.OPEN ||
        wsRef.current.readyState === WebSocket.CONNECTING)
    ) {
      return;
    }

    const url = `ws://${window.location.host}/ws`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) return;
      backoffRef.current = 1000; // reset backoff on success
      dispatch({ type: "SET_CONNECTED", connected: true });
    };

    ws.onclose = () => {
      if (!mountedRef.current) return;
      dispatch({ type: "SET_CONNECTED", connected: false });
      scheduleReconnect();
    };

    ws.onerror = () => {
      // onclose will fire after onerror — reconnection handled there
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;
      try {
        const msg: ServerMessage = JSON.parse(event.data);
        dispatch({ type: "SERVER_MSG", msg });
        onMessageRef.current?.(msg);
      } catch {
        console.error("[useWebSocket] Failed to parse message:", event.data);
      }
    };
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return;
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);

    const delay = backoffRef.current;
    reconnectTimer.current = setTimeout(() => {
      if (mountedRef.current) connect();
    }, delay);

    // Exponential backoff: 1s -> 2s -> 4s -> 8s -> 16s (cap)
    backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF);
  }, [connect]);

  /* ---------- lifecycle ---------- */

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current);
        reconnectTimer.current = null;
      }
      if (wsRef.current) {
        wsRef.current.onclose = null; // prevent reconnect on intentional close
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  /* ---------- actions ---------- */

  const send = useCallback((msg: ClientMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    } else {
      console.warn("[useWebSocket] Cannot send — socket not open");
    }
  }, []);

  const startPipeline = useCallback(
    (problem: string, untilStage?: Stage) => {
      dispatch({ type: "START_PIPELINE" });
      send({ type: "start", problem, until_stage: untilStage });
    },
    [send],
  );

  const sendReviewResponse = useCallback(
    (stage: Stage, data: any) => {
      send({ type: "review_response", stage, data } as ClientMessage);
      dispatch({ type: "CLEAR_REVIEW" });
    },
    [send],
  );

  const sendRouterPrompt = useCallback(
    (message: string) => {
      send({ type: "router_prompt", message });
    },
    [send],
  );

  const cancelPipeline = useCallback(() => {
    send({ type: "cancel" });
    dispatch({ type: "CANCEL_PIPELINE" });
  }, [send]);

  const clearError = useCallback(() => {
    dispatch({ type: "CLEAR_ERROR" });
  }, []);

  return {
    ...state,
    send,
    startPipeline,
    sendReviewResponse,
    sendRouterPrompt,
    cancelPipeline,
    clearError,
  };
}
