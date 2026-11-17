import { yahooQuoteUrl } from '../utils/yahoo'

interface Props {
  /** Text shown (the ticker or the broker's symbol). */
  label: string
  /** Yahoo Finance ticker to link to; plain text when null. */
  ticker: string | null
  /** Hover text, e.g. the company name. */
  title?: string | null
}

/** A ticker that opens its Yahoo Finance page in a new window. */
export function TickerLink({ label, ticker, title }: Props) {
  const hover = title || undefined
  if (!ticker) {
    return (
      <span className="font-medium" title={hover}>
        {label}
      </span>
    )
  }
  return (
    <a
      href={yahooQuoteUrl(ticker)}
      target="_blank"
      rel="noopener noreferrer"
      title={hover}
      className="font-medium text-slate-900 hover:text-sky-700 hover:underline"
    >
      {label}
    </a>
  )
}
