// Fixed color per role name
const NAME_COLORS: Record<string, string> = {
  'Researcher':      '#4a9eff',
  'Deep Researcher': '#8b5cf6',
  'Formalizer':      '#f59e0b',
  'Reasoner':        '#10b981',
  'Builder':         '#ec4899',
};

const FALLBACK_PALETTE = [
  '#06b6d4', '#f97316', '#a3e635', '#e879f9',
  '#facc15', '#2dd4bf', '#fb7185', '#818cf8',
];

let fallbackIdx = 0;

export function colorForName(name: string): string {
  if (NAME_COLORS[name]) return NAME_COLORS[name];
  const color = FALLBACK_PALETTE[fallbackIdx % FALLBACK_PALETTE.length];
  NAME_COLORS[name] = color;
  fallbackIdx++;
  return color;
}
