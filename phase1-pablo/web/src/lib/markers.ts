import type { Stage } from "../types";

export interface StageMarker {
  cursor: number;
  stage: Stage;
}

export interface ReviewMarker {
  cursor: number;
  stage: Stage;
  approved: boolean | null; // null = decision absent (incomplete run)
}

export function extractMarkers(events: readonly Record<string, any>[]): {
  stageMarkers: StageMarker[];
  reviewMarkers: ReviewMarker[];
} {
  const stageMarkers: StageMarker[] = [];
  const reviewMarkers: ReviewMarker[] = [];
  const pendingReview: { index: number; stage: Stage }[] = [];

  for (let i = 0; i < events.length; i++) {
    const ev = events[i];
    if (ev.type === "stage_change" && ev.status === "running") {
      stageMarkers.push({ cursor: i, stage: ev.stage });
    } else if (ev.type === "review_request") {
      pendingReview.push({ index: i, stage: ev.stage });
    } else if (ev.type === "review_decision") {
      const match = pendingReview.pop();
      const approved = isAllApproved(ev.approved);
      reviewMarkers.push({
        cursor: match ? match.index : i,
        stage: ev.stage,
        approved,
      });
    }
  }
  for (const { index, stage } of pendingReview) {
    reviewMarkers.push({ cursor: index, stage, approved: null });
  }
  reviewMarkers.sort((a, b) => a.cursor - b.cursor);
  return { stageMarkers, reviewMarkers };
}

function isAllApproved(approved: unknown): boolean | null {
  if (!approved || typeof approved !== "object") return null;
  const vals = Object.values(approved as Record<string, unknown>);
  if (vals.length === 0) return null;
  if (vals.every((v) => v === true)) return true;
  if (vals.every((v) => v === false)) return false;
  return null; // mixed
}
