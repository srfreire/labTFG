import {
  ResponsiveContainer,
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts'
import type { ChartSpec } from '../types'
function pivotSeries(spec: ChartSpec, sortNumeric = true): Record<string, number | string>[] {
  const dataMap = new Map<number | string, Record<string, number | string>>()
  for (const s of spec.series) {
    for (const d of s.data) {
      const existing = dataMap.get(d.x) || { x: d.x }
      existing[s.name] = d.y
      dataMap.set(d.x, existing)
    }
  }
  const data = Array.from(dataMap.values())
  return sortNumeric ? data.sort((a, b) => Number(a.x) - Number(b.x)) : data
}
const AXIS_STROKE = 'rgba(255,255,255,0.3)'
const AXIS_TICK = { fontSize: 10, fill: 'rgba(255,255,255,0.4)' }
const GRID_STROKE = 'rgba(255,255,255,0.06)'

type AxisLabelPosition = 'insideBottom' | 'insideLeft'

function axisLabel(value: string, position: AxisLabelPosition, extra?: Record<string, unknown>) {
  return { value, position, fontSize: 10, fill: 'rgba(255,255,255,0.4)', ...extra }
}

const tooltipStyle = {
  contentStyle: {
    background: 'var(--color-surface-frosted)',
    border: '1px solid var(--color-border)',
    borderRadius: 'var(--radius-md)',
    fontSize: 12,
    color: 'var(--color-text-muted)',
  },
}

function LineChartView({ spec }: { spec: ChartSpec }) {
  const data = pivotSeries(spec)

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data}>
        <CartesianGrid stroke={GRID_STROKE} />
        <XAxis dataKey="x" stroke={AXIS_STROKE} tick={AXIS_TICK} label={axisLabel(spec.x_label, 'insideBottom', { offset: -5 })} />
        <YAxis stroke={AXIS_STROKE} tick={AXIS_TICK} label={axisLabel(spec.y_label, 'insideLeft', { angle: -90 })} />
        <Tooltip {...tooltipStyle} cursor={false} />
        {spec.series.length > 1 && (
          <Legend wrapperStyle={{ fontSize: 11, color: 'rgba(255,255,255,0.6)' }} />
        )}
        {spec.series.map(s => (
          <Line
            key={s.name}
            type="monotone"
            dataKey={s.name}
            stroke={s.color || 'var(--color-accent-green-light)'}
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3, stroke: s.color || 'var(--color-accent-green-light)', strokeWidth: 1 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

function BarChartView({ spec }: { spec: ChartSpec }) {
  const data = pivotSeries(spec, false)

  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data}>
        <CartesianGrid stroke={GRID_STROKE} />
        <XAxis dataKey="x" stroke={AXIS_STROKE} tick={{ ...AXIS_TICK, fontSize: 9 }} label={axisLabel(spec.x_label, 'insideBottom', { offset: -5 })} />
        <YAxis stroke={AXIS_STROKE} tick={AXIS_TICK} label={axisLabel(spec.y_label, 'insideLeft', { angle: -90 })} />
        <Tooltip {...tooltipStyle} cursor={false} />
        {spec.series.length > 1 && (
          <Legend wrapperStyle={{ fontSize: 11, color: 'rgba(255,255,255,0.6)' }} />
        )}
        {spec.series.map(s => (
          <Bar
            key={s.name}
            dataKey={s.name}
            fill={s.color || 'var(--color-accent-green-light)'}
            radius={[3, 3, 0, 0]}
            opacity={0.85}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

function HeatmapView({ spec }: { spec: ChartSpec }) {
  const data = pivotSeries(spec, false)

  return (
    <ResponsiveContainer width="100%" height={Math.max(200, data.length * 28)}>
      <BarChart data={data} layout="vertical">
        <CartesianGrid stroke={GRID_STROKE} />
        <XAxis type="number" stroke={AXIS_STROKE} tick={AXIS_TICK} label={axisLabel(spec.y_label, 'insideBottom', { offset: -5 })} />
        <YAxis type="category" dataKey="x" stroke={AXIS_STROKE} tick={{ ...AXIS_TICK, fontSize: 8 }} width={100} />
        <Tooltip {...tooltipStyle} cursor={false} />
        {spec.series.length > 1 && (
          <Legend wrapperStyle={{ fontSize: 11, color: 'rgba(255,255,255,0.6)' }} />
        )}
        {spec.series.map(s => (
          <Bar
            key={s.name}
            dataKey={s.name}
            fill={s.color || 'var(--color-accent-purple)'}
            radius={[0, 3, 3, 0]}
            opacity={0.85}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  )
}

const CHART_RENDERERS = {
  line: LineChartView,
  bar: BarChartView,
  heatmap: HeatmapView,
}

export function ChartCard({ spec }: { spec: ChartSpec }) {
  const Renderer = CHART_RENDERERS[spec.type] || LineChartView

  return (
    <div
      className="mt-3 border p-3 rounded-lg animate-card-in shadow-xl shadow-black/20"
      style={{
        background: 'var(--color-surface)',
        borderColor: 'color-mix(in srgb, var(--color-analyst) 20%, transparent)',
      }}
    >
      <div
        className="text-[10px] uppercase tracking-[1px] mb-2 font-semibold"
        style={{ color: 'var(--color-analyst)' }}
      >
        {spec.title}
      </div>
      <Renderer spec={spec} />
    </div>
  )
}
