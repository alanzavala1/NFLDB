export function sv(n: number | null | undefined) { return !n || n === 0 ? '—' : String(n) }

export function pct(a: number, b: number | null) { return b == null || b === 0 ? '—' : (a / b * 100).toFixed(1) + '%' }

export function avg(y: number, c: number) { return c === 0 ? '—' : (y / c).toFixed(1) }

export function ratio(y: number, a: number | null, d = 1) { return a != null && a > 0 ? (y / a).toFixed(d) : null }

export function sfmt(x: number, d = 3) { return `${x >= 0 ? '+' : ''}${x.toFixed(d)}` }

export function passerRating(cmp: number, att: number, yds: number, td: number, int_: number): number | null {
  if (att === 0) return null
  const clamp = (x: number) => Math.min(2.375, Math.max(0, x))
  const a = clamp((cmp / att - 0.3) / 0.2)
  const b = clamp((yds / att - 3) / 4)
  const c = clamp((td / att) / 0.05)
  const d = clamp(2.375 - (int_ / att) / 0.04)
  return ((a + b + c + d) / 6) * 100
}
