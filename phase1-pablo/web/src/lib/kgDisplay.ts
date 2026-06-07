const HIDDEN_KG_PROPERTY_KEYS = new Set([
  "run_count",
  "last_run_at",
  "created_at",
  "updated_at",
  "embedding",
  "embedding_model",
  "embedding_dim",
  "vector",
]);

function isLongNumericArray(value: unknown): boolean {
  return (
    Array.isArray(value) &&
    value.length > 16 &&
    value.every((item) => typeof item === "number")
  );
}

export function shouldShowKgProperty(key: string, value: unknown): boolean {
  const normalized = key.toLowerCase();
  if (HIDDEN_KG_PROPERTY_KEYS.has(normalized)) return false;
  if (normalized.startsWith("_")) return false;
  if (normalized.endsWith("_embedding")) return false;
  if (normalized.endsWith("_vector")) return false;
  if (isLongNumericArray(value)) return false;
  return true;
}

export function formatKgPropertyValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
