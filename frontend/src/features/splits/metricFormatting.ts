

export const sgn = (v: number, d = 3) => `${v >= 0 ? '+' : ''}${v.toFixed(d)}`

export const pct = (a: number | null | undefined, b: number | null | undefined) =>
  a != null && b != null && b > 0 ? (a / b) * 100 : null

export const per = (a: number | null | undefined, b: number | null | undefined) =>
  a != null && b != null && b > 0 ? a / b : null

export function passerRating(cmp: number, att: number, yds: number, td: number, int: number): number | null {
  if (att <= 0) return null
  const clamp = (x: number) => Math.max(0, Math.min(2.375, x))
  const a = clamp(((cmp / att) - 0.3) * 5)
  const b = clamp(((yds / att) - 3) * 0.25)
  const c = clamp((td / att) * 20)
  const d = clamp(2.375 - (int / att) * 25)
  return ((a + b + c + d) / 6) * 100
}

// ── Player metrics ───────────────────────────────────────────────────────────

export const intStr = (v: number) => String(v)
