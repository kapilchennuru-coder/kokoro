// Renders brand text with the "R" picked out in the brand's neon accent -
// used everywhere "OUTREACH"/"Outreach" appears as a wordmark.
export function Wordmark({ text = 'OUTREACH', className }: { text?: string; className?: string }) {
  const idx = text.search(/r/i)
  if (idx === -1) return <span className={className}>{text}</span>
  return (
    <span className={className}>
      {text.slice(0, idx)}
      <span className="neon-r">{text[idx]}</span>
      {text.slice(idx + 1)}
    </span>
  )
}
