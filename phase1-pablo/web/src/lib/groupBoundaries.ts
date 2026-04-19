/**
 * Compute cursor positions (1..events.length) that end an "agent action" group.
 * A group ends when either:
 *   - an agent_status event transitions an agent to "idle", OR
 *   - a stage_change event fires.
 * The final cursor position is always included so stepForward from the last
 * group lands at the end of the stream.
 */
export function groupBoundaries(events: readonly Record<string, any>[]): number[] {
  const out: number[] = [];
  for (let i = 0; i < events.length; i++) {
    const ev = events[i];
    const ends =
      (ev.type === "agent_status" && ev.status === "idle") ||
      ev.type === "stage_change";
    if (ends) out.push(i + 1);
  }
  if (events.length > 0 && (out.length === 0 || out[out.length - 1] !== events.length)) {
    out.push(events.length);
  }
  return out;
}
