import { useCallback, useEffect, useReducer, useRef } from "react";
import {
  Stage,
  StageStatus,
  GraphNode,
  GraphEdge,
  ServerMessage,
  ClientMessage,
} from "../types";

/* ------------------------------------------------------------------ */
/*  State                                                              */
/* ------------------------------------------------------------------ */

interface WebSocketState {
  connected: boolean;
  nodes: GraphNode[];
  edges: GraphEdge[];
  stages: Record<Stage, StageStatus>;
  currentStage: Stage | null;
  reviewRequest: { stage: Stage; data: any } | null;
  isRunning: boolean;
  error: string | null;
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
  nodes: [],
  edges: [],
  stages: initStages(),
  currentStage: null,
  reviewRequest: null,
  isRunning: false,
  error: null,
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
        nodes: [],
        edges: [],
        stages: initStages(),
        currentStage: null,
        reviewRequest: null,
        error: null,
      };

    case "CANCEL_PIPELINE":
      return {
        ...state,
        isRunning: false,
        currentStage: null,
        reviewRequest: null,
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
    case "stage_change":
      return {
        ...state,
        stages: { ...state.stages, [msg.stage]: msg.status },
        currentStage: msg.status === "running" ? msg.stage : state.currentStage,
      };

    case "node_add":
      return { ...state, nodes: [...state.nodes, msg.node] };

    case "edge_add":
      return { ...state, edges: [...state.edges, msg.edge] };

    case "node_update":
      return {
        ...state,
        nodes: state.nodes.map((n) =>
          n.id === msg.id ? { ...n, status: msg.status } : n,
        ),
      };

    case "review_request":
      return {
        ...state,
        reviewRequest: { stage: msg.stage, data: msg.data },
      };

    case "rerun":
      // Rerun is informational; graph_clear handles visual reset
      return state;

    case "graph_clear":
      return { ...state, nodes: [], edges: [] };

    case "pipeline_done":
      return { ...state, isRunning: false, currentStage: null };

    case "error":
      return { ...state, error: msg.message };

    case "state_sync":
      return {
        ...state,
        nodes: msg.nodes,
        edges: msg.edges,
        currentStage: msg.stage,
      };

    default:
      return state;
  }
}

/* ------------------------------------------------------------------ */
/*  Actions interface                                                  */
/* ------------------------------------------------------------------ */

interface WebSocketActions {
  send: (msg: ClientMessage) => void;
  startPipeline: (problem: string) => void;
  sendReviewResponse: (stage: Stage, data: any) => void;
  cancelPipeline: () => void;
  clearError: () => void;
}

/* ------------------------------------------------------------------ */
/*  Hook                                                               */
/* ------------------------------------------------------------------ */

const MAX_BACKOFF = 16_000;

export function useWebSocket(): WebSocketState & WebSocketActions {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const backoffRef = useRef(1000);
  // Track whether the hook is still mounted to avoid reconnects after unmount
  const mountedRef = useRef(true);

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
    (problem: string) => {
      dispatch({ type: "START_PIPELINE" });
      send({ type: "start", problem });
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
    cancelPipeline,
    clearError,
  };
}
