// The Outreach mark: a ringing connection node (circle, center point, two
// signal arcs) rather than a literal O+R+phone glyph crammed into one small
// shape - it stays crisp down to favicon scale, where a fused letterform
// loses its detail. Chosen from three concepts reviewed 2026-08-10.

import { Wordmark } from './Wordmark'

type BrandMarkVariant = 'full' | 'mark' | 'text'

function strokeWeights(size: number) {
  // Stroke widths are tuned per size tier (not a pure linear scale) so the
  // ring stays visually consistent as it shrinks - thin at 64px would all
  // but disappear by 16px if scaled proportionally.
  if (size >= 40) return { ring: 2.6, dot: 1.8, arc: 2.0 }
  if (size >= 28) return { ring: 2.9, dot: 2.0, arc: 2.3 }
  if (size >= 20) return { ring: 3.3, dot: 2.2, arc: 2.6 }
  return { ring: 3.8, dot: 2.6, arc: 3.1 }
}

function ConnectionRingIcon({ size }: { size: number }) {
  const { ring, dot, arc } = strokeWeights(size)
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <circle cx="16" cy="16" r="9" stroke="currentColor" strokeWidth={ring} />
      <circle cx="16" cy="16" r={dot} fill="currentColor" />
      <path d="M24.2 9.3a13.2 13.2 0 0 1 3 8.4" stroke="currentColor" strokeWidth={arc} strokeLinecap="round" opacity={0.6} />
      <path d="M26.8 5a19 19 0 0 1 4.5 12" stroke="currentColor" strokeWidth={arc} strokeLinecap="round" opacity={0.35} />
    </svg>
  )
}

export function BrandMark({
  size = 22,
  variant = 'mark',
  className,
}: {
  size?: number
  variant?: BrandMarkVariant
  className?: string
}) {
  if (variant === 'text') {
    return (
      <span className={className} style={{ fontWeight: 700, letterSpacing: '-0.01em' }}>
        <Wordmark />
      </span>
    )
  }

  if (variant === 'mark') {
    return (
      <span className={className} style={{ display: 'inline-flex' }}>
        <ConnectionRingIcon size={size} />
      </span>
    )
  }

  return (
    <span className={className} style={{ display: 'inline-flex', alignItems: 'center', gap: Math.round(size * 0.4) }}>
      <ConnectionRingIcon size={size} />
      <span style={{ fontWeight: 700, letterSpacing: '-0.01em', fontSize: Math.round(size * 0.62) }}>
        <Wordmark />
      </span>
    </span>
  )
}
