/** Shared frontend utilities. */

/**
 * Extract Q-values from a model state dict.
 * Looks for common key names: q_values, Q, q_table.
 */
export function extractQValues(state: Record<string, unknown> | null): Record<string, number> | null {
  if (!state) return null
  for (const key of ['q_values', 'Q', 'q_table']) {
    const val = state[key]
    if (val && typeof val === 'object' && !Array.isArray(val)) {
      const entries = Object.entries(val as Record<string, unknown>).filter(([, v]) => typeof v === 'number')
      if (entries.length > 0) return Object.fromEntries(entries) as Record<string, number>
    }
  }
  return null
}
