import type { ReactNode } from 'react'

/**
 * Render a strategy's explanation. The format is deliberately tiny (blocks
 * separated by blank lines; "## " heading; "- " bullet lines) and is
 * rendered as text, never as HTML.
 */
export function StrategyExplanation({ text }: { text: string }) {
  const blocks = text
    .split(/\n\s*\n/)
    .map((b) => b.trim())
    .filter(Boolean)

  const nodes: ReactNode[] = blocks.map((block, i) => {
    if (block.startsWith('## ')) {
      return (
        <h3 key={i} className="mt-4 mb-1 text-sm font-semibold text-slate-800">
          {block.slice(3)}
        </h3>
      )
    }
    const lines = block.split('\n').map((l) => l.trim())
    if (lines.every((l) => l.startsWith('- '))) {
      return (
        <ul key={i} className="my-2 list-disc space-y-1 pl-5">
          {lines.map((l, j) => (
            <li key={j}>{l.slice(2)}</li>
          ))}
        </ul>
      )
    }
    return (
      <p key={i} className="my-2">
        {lines.join(' ')}
      </p>
    )
  })

  if (nodes.length === 0) return <p className="text-slate-500">No explanation is available for this strategy.</p>
  return <div className="text-sm leading-relaxed text-slate-700">{nodes}</div>
}
