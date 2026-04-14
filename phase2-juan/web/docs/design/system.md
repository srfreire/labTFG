# Design System

> Direction: Industrial — scientific lab dashboard
> Framework: React (Vite)
> CSS: Tailwind v4 (`@theme` in `index.css`)
> Created: 2026-04-14
> Last updated: 2026-04-14

## Direction

Dense, dark, data-first. A virtual laboratory control panel where every pixel serves the operator. Monochrome base with saturated accent colors per agent role — green (Architect), amber (Tracker), purple (Analyst), pink (Reporter), slate (Orchestrator). Frosted glass panels float over a subtle grid background. Typography is tight, uppercase labels with generous letter-spacing for hierarchy.

## Tokens

### Colors

Dark-only (no light mode). All semantic colors defined via CSS custom properties in `@theme`.

| Token | Value | Usage |
|-------|-------|-------|
| `--color-bg` | `#0a0a0a` | Page background |
| `--color-surface` | `#090909` | Card/container background |
| `--color-surface-hover` | `rgba(255,255,255,0.05)` | Hovered surface |
| `--color-surface-frosted` | `rgba(9,9,9,0.96)` | Frosted glass panels |
| `--color-overlay` | `rgba(0,0,0,0.85)` | Modal overlay |
| `--color-border` | `rgba(255,255,255,0.1)` | Primary borders |
| `--color-border-subtle` | `rgba(255,255,255,0.08)` | Subtle dividers |
| `--color-border-faint` | `rgba(255,255,255,0.06)` | Faintest borders |
| `--color-text` | `#fff` | Primary text |
| `--color-text-muted` | `rgba(255,255,255,0.6)` | Secondary text |
| `--color-text-dim` | `rgba(255,255,255,0.4)` | Tertiary text |
| `--color-text-faint` | `rgba(255,255,255,0.3)` | Labels, captions |
| `--color-text-ghost` | `rgba(255,255,255,0.15)` | Placeholders, disabled |
| `--color-accent-green` | `#22c55e` | Success, Architect agent |
| `--color-accent-green-light` | `#4ade80` | Light green variant |
| `--color-accent-amber` | `#fbbf24` | Warning, Tracker agent |
| `--color-accent-amber-dark` | `#f59e0b` | Dark amber variant |
| `--color-accent-red` | `#ef4444` | Error, destructive |
| `--color-accent-blue` | `#4a9eff` | Links, info |
| `--color-scrollbar` | `#333` | Scrollbar thumb |

#### Agent Palette (`:root`)

| Token | Value | Agent |
|-------|-------|-------|
| `--color-architect` | `#4ade80` | Architect |
| `--color-tracker` | `#fbbf24` | Tracker |
| `--color-analyst` | `#a78bfa` | Analyst |
| `--color-reporter` | `#f472b6` | Reporter |
| `--color-orchestrator` | `#94a3b8` | Orchestrator |
| `--color-user` | `rgba(255,255,255,0.5)` | User messages |

#### Simulation Agent Palette

| Token | Value |
|-------|-------|
| `--color-sim-1` | `#4ade80` |
| `--color-sim-2` | `#fbbf24` |
| `--color-sim-3` | `#a78bfa` |
| `--color-sim-4` | `#f472b6` |
| `--color-sim-5` | `#38bdf8` |
| `--color-sim-6` | `#fb923c` |

### Typography

| Token | Value | Usage |
|-------|-------|-------|
| `--font-sans` | `'Satoshi', system-ui, sans-serif` | Body text |
| `--font-mono` | `'IBM Plex Mono', 'SF Mono', 'Monaco', monospace` | Code, data, labels |
| Body size | `15px` | Chat messages |
| Label size | `8-10px` | Uppercase tracking labels |
| Card title | `10px` | Uppercase, tracking `1px`, semibold |
| Heading | `17-20px` | App title, empty state |
| Weight normal | `400` | Body |
| Weight medium | `500` | Emphasis |
| Weight semibold | `600` | Headings, labels |
| Leading tight | `1.25` | Headings |
| Leading normal | `1.6` | Body/messages |
| Letter-spacing labels | `1-2px` | Uppercase micro-labels |

### Spacing

4px base scale, density-first.

| Token | Value | Usage |
|-------|-------|-------|
| `space-0.5` | `2px` | Inline micro-gaps |
| `space-1` | `4px` | Tight padding |
| `space-1.5` | `6px` | Badge/pill padding |
| `space-2` | `8px` | Card inner gaps |
| `space-2.5` | `10px` | Component gaps |
| `space-3` | `12px` | Card padding |
| `space-4` | `16px` | Section gaps |
| `space-5` | `20px` | Panel padding |
| `space-6` | `24px` | Major sections |
| `space-8` | `32px` | Page padding |
| `space-10` | `40px` | Outer margins |

### Shape

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-sm` | `6px` | Badges, pills, code |
| `--radius-md` | `8px` | Buttons, inputs, inner cards |
| `--radius-lg` | `12px` | Cards, containers |
| `--radius-xl` | `16px` | Modals, chat bubbles |
| `--radius-2xl` | `20px` | Floating panels |
| `--radius-full` | `9999px` | Avatars, dots |

### Shadows

| Token | Value | Usage |
|-------|-------|-------|
| Panel shadow | `0 20px 25px -5px rgba(0,0,0,0.2), 0 8px 10px -6px rgba(0,0,0,0.2)` | Floating panels |
| Card shadow | `shadow-xl shadow-black/20` | Data cards (Tailwind) |
| Glow | `0 0 Npx <color>40` | Agent dots, active states |
| Popover shadow | `0 4px 20px rgba(0,0,0,0.5)` | Popovers, tooltips |

### Animation

| Token | Value | Usage |
|-------|-------|-------|
| `card-in` | `0.3s ease-out, translateY(8px)→0` | Card entrance |
| `msg-in` | `0.25s ease-out, translateY(4px)→0` | Message entrance |
| `slide-up` | `0.6s ease-out, translateY(12px)→0` | Sim agent entrance |
| `scale-in` | `0.2s ease-out, scale(0.96)→1` | Popover entrance |
| `typing-dot` | `1.4s ease-in-out infinite` | Thinking indicator |
| `bob` | `translateY(0)→-3px→0` | Gentle float |
| `ping` | `2s ease-in-out infinite, scale→1.5` | Active node ring |
| Ease out | `cubic-bezier(0.23, 1, 0.32, 1)` | All entries |
| Transition duration | `150ms` | Hover/focus states |
| Transition duration slow | `300ms` | Status changes |

## Component Patterns

### FloatingPanel
Frosted glass container used for sidebar and main chat area.
- `border-radius: var(--radius-2xl)`
- `background: rgba(9,9,9,0.8)`
- `backdrop-filter: blur(24px)`
- `border: 1px solid var(--color-border)`
- Panel shadow
- Uses: `--radius-2xl`, `--color-border`, panel shadow

### Button (Send)
Primary action button (send message).
- Background: `#fff` (white on dark)
- Text: `#000`
- Hover: `rgba(255,255,255,0.8)`
- Disabled: `bg-text-ghost`, `text-text-dim`
- Radius: `--radius-xl` (12px)
- Sizes: 48px (chat) / 56px (empty state)
- Uses: `--radius-xl`, `--color-text-ghost`, `--color-text-dim`

### Button (Control)
Small utility buttons (replay controls).
- Border: `1px solid var(--color-border)`
- Text: `var(--color-text-dim)`
- Hover: `bg-surface-hover`, `text-text-muted`
- Radius: `--radius-sm`
- Size: `9px` text, `px-2 py-1.5`
- Uses: `--radius-sm`, `--color-border`, `--color-surface-hover`

### Button (Prompt Chip)
Example prompt buttons in empty state.
- Border: `1px solid var(--color-border-subtle)`
- Text: `var(--color-text-dim)`
- Hover: text brightens, border strengthens, surface-hover bg
- Radius: `--radius-lg`
- Size: `12px` text, `px-3.5 py-2`
- Uses: `--radius-lg`, `--color-border-subtle`, `--color-surface-hover`

### Input (Chat)
Text input for chat messages.
- Background: transparent
- Border: `1px solid var(--color-text-ghost)`
- Focus: `border-color: var(--color-text-dim)`
- Disabled: `opacity: 0.4`, `cursor: not-allowed`
- Radius: `--radius-xl`
- Size: `15px` text, `py-3 px-5` / `py-3.5 px-5` (empty state)
- Uses: `--radius-xl`, `--color-text-ghost`, `--color-text-dim`

### Card (Data)
Generic key-value data card (Environment Spec).
- Background: `var(--color-surface)`
- Border: `1px solid <agent-color>20`
- Radius: `--radius-lg`
- Shadow: `shadow-xl shadow-black/20`
- Title: `10px` uppercase, agent color
- Inner cells: `border border-border-subtle`, `--radius-md`
- Uses: `--color-surface`, `--radius-lg`, `--radius-md`, `--color-border-subtle`

### Card (Tracker)
Trajectory summary per agent.
- Same base as DataCard
- Border tinted with amber (`--color-accent-amber`)
- Agent rows: bordered, tinted with agent color
- Metric pills: `11px`, `px-2.5 py-1`, rounded, color-tinted bg
- Uses: `--color-surface`, `--color-accent-amber`, `--radius-md`

### Card (Analyst)
Pattern/comparison analysis results.
- Same base as DataCard
- Border tinted with purple (`--color-analyst`)
- Pattern badges: type-colored, `10px`, `--radius-sm`
- Comparison rows: 2-column values, best highlighted green
- Uses: `--color-surface`, `--color-analyst`, `--radius-md`, `--color-accent-green-light`

### DecisionTraceCard
Split pre/post decision context display.
- Background: `#0f172a` (slightly blue-tinted dark)
- Border: `1px solid var(--color-border-subtle)`
- Radius: `--radius-lg`
- Font: `--font-mono`, `11px`
- Pre column: yellow label (`#fbbf24`)
- Post column: blue label (`#38bdf8`)
- Q-value pills: green for chosen (`#166534` bg), slate for others (`#1e293b` bg)
- Footer: reward with green/red color
- Uses: `--font-mono`, `--radius-lg`, `--color-border-subtle`

### ReplayTracePopover
Compact popover with Q-value bars.
- Same base bg as DecisionTraceCard (`#0f172a`)
- Critical event border tint: `#38bdf840`
- Q-value bars: horizontal, green gradient for chosen
- Context row: dark inner bg (`#0a0f1a`)
- Close button: `×`, `14px`
- Shadow: `0 4px 20px rgba(0,0,0,0.5)`
- Uses: `--font-mono`, `--radius-lg`

### ChartCard
Recharts wrapper for line/bar/heatmap.
- Same base as DataCard
- Purple-tinted border (`--color-analyst`)
- Chart area: 240px height
- Grid lines: `rgba(255,255,255,0.06)`
- Axis text: `rgba(255,255,255,0.4)`, 10px
- Tooltip: dark frosted bg, rounded-8, 12px
- Uses: `--color-surface`, `--color-analyst`, `--radius-lg`

### SimulationGrid
Interactive replay grid with timeline.
- Container: `var(--color-bg)` background
- Cells: `rgba(255,255,255,0.02)` bg
- Agent dots: 65% cell size, colored, glow shadow
- Resource dots: 30% cell size, green, 60% opacity
- Trail dots: 20% cell size, `--color-border-subtle`
- Timeline: 3px height, colored markers per event type
- Critical event badges: `8px`, colored, tinted bg
- Uses: `--color-bg`, `--color-border`, `--radius-sm`, `--color-accent-*`

### AgentPanel (PipelineNode)
Vertical pipeline with avatar nodes.
- Vertical connecting line: `2px` wide
- Active node: `28px` avatar, ping ring animation
- Done node: `24px` avatar, checkmark badge
- Idle node: `24px`, `opacity: 0.4`
- Working badge: `7px` uppercase, agent-colored bg tint
- Tool label: `9px` mono, agent color at 67% opacity
- Uses: `--font-mono`, `--radius-sm`, `--radius-full`

### MessageBubble
Chat message with avatar and markdown.
- User: right-aligned, `18px 18px 4px 18px` radius, `var(--color-border)` bg
- Agent: left-aligned, `4px 18px 18px 18px` radius, `var(--color-surface-hover)` bg
- Agent border: `1px solid <color>20`
- Avatar: `28px` Facehash, rounded-full
- Author label: `11px`, agent color
- Text: `15px`, `leading-[1.6]`, markdown-aware
- Uses: `--color-border`, `--color-surface-hover`, `--radius-xl`

### Badge (Status)
Small status indicators.
- Sizes: `7-9px` text, uppercase, tracking `1px`
- Pattern: `color: <agent-color>`, `bg: <color>15`, `border: <color>30`
- Radius: `--radius-sm`
- Uses: `--radius-sm`

### Badge (Critical Event)
Event type indicators in timeline.
- Size: `8px`, colored per event type
- Border: `<color>30`
- Background: `<color>10`
- Radius: `--radius-sm`
- Uses: `--radius-sm`, `--color-accent-*`
