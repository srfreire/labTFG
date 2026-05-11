interface PlaceholderProps {
  title: string
  body: string
  /** ``absolute`` overlays a fitted parent (e.g. inside a ReactFlow);
   * ``fill`` takes full height (table/list panels). Default ``fill``. */
  variant?: 'absolute' | 'fill'
}

export function Placeholder({ title, body, variant = 'fill' }: PlaceholderProps) {
  const positioning =
    variant === 'absolute'
      ? 'absolute inset-0 pointer-events-none'
      : 'h-full'
  return (
    <div className={`${positioning} flex items-center justify-center flex-col gap-1 text-center px-6`}>
      <div className="text-[13px] font-medium text-text">{title}</div>
      <div className="text-[11px] text-text-muted">{body}</div>
    </div>
  )
}
