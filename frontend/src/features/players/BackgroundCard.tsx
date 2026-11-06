import type { PlayerProfile, CombineData } from '../../types'
import { Link } from 'react-router-dom'
import { teamLogoUrl, teamName } from '../../utils/teams'
import { AWARD_LABEL, type AwardKey } from '../../utils/awards'

function AwardBadge({ season, award }: { season: number; award: AwardKey }) {
  const isMvp = award === 'MVP'
  return <span className={`whitespace-nowrap rounded border px-2 py-1 text-[10px] font-bold uppercase tracking-wider ${isMvp ? 'border-gold/50 bg-gold/15 text-gold' : 'border-gold/40 bg-gold/10 text-gold'}`}>
    {isMvp ? '★ ' : ''}{AWARD_LABEL[award]} {season}
  </span>
}

function combineHasAny(c: CombineData | null): boolean {
  if (!c) return false
  return c.forty != null || c.vertical != null || c.bench != null
      || c.broad_jump != null || c.cone != null || c.shuttle != null
}

function ordinal(n: number): string {
  const s = ['th', 'st', 'nd', 'rd']
  const v = n % 100
  return n + (s[(v - 20) % 10] ?? s[v] ?? s[0])
}

function BigStat({ label, value, sub }: { label: string; value: string; sub?: string | null }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] font-bold text-ink-dim uppercase tracking-widest">{label}</span>
      <span className="text-2xl font-black text-ink tabular-nums leading-tight mt-0.5">{value}</span>
      {sub && <span className="text-[10px] text-ink-dim uppercase tracking-wider mt-0.5">{sub}</span>}
    </div>
  )
}

function EmptyCardBody({ headline, sub }: { headline: string; sub?: string }) {
  // Shared empty-state styling so the three cards visually agree. The
  // headline reads as the "answer" (e.g. "Undrafted", "No accolades")
  // and the sub-line explains why or what era it's about.
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center py-4">
      <div className="text-xl font-black text-ink-dim leading-none">{headline}</div>
      {sub && <div className="mt-2 text-[10px] text-ink-dim uppercase tracking-wider max-w-[80%]">{sub}</div>}
    </div>
  )
}

function DraftCardContent({ player }: { player: PlayerProfile }) {
  const draft = player.draft

  // Filled state: full draft hero
  if (draft) {
    return (
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-[10px] font-bold text-ink-dim uppercase tracking-widest mb-1">Drafted</div>
          <div className="text-3xl font-black text-ink leading-none">
            {ordinal(draft.round)} <span className="text-ink-mid">Round</span>
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-5xl font-black text-ink tabular-nums leading-none">#{draft.pick}</span>
            <span className="text-xs font-bold text-ink-dim uppercase tracking-wider">overall · {draft.season}</span>
          </div>
          {draft.college && (
            <div className="mt-3 text-xs text-ink-mid">
              <span className="text-ink-dim uppercase tracking-wider text-[10px] font-bold">College</span>
              <span className="ml-2 text-ink font-semibold">{draft.college}</span>
            </div>
          )}
        </div>
        <Link
          to={`/teams/${draft.team}`}
          className="shrink-0 flex flex-col items-center gap-1 hover:opacity-90 transition-opacity"
          title={`Drafted by ${teamName(draft.team)}`}
        >
          <img src={teamLogoUrl(draft.team)} className="w-16 h-16 object-contain" alt="" />
          <span className="text-[10px] font-bold text-ink-dim uppercase tracking-wider">{draft.team}</span>
        </Link>
      </div>
    )
  }

  // Empty state: figure out which kind of empty.
  // Pre-1980 → era explanation. Otherwise → Undrafted (UDFA).
  const entryYear = player.entry_year
  const isPre1980 = entryYear != null && entryYear < 1980
  const headline = isPre1980 ? 'Pre-1980' : 'Undrafted'
  const sub = isPre1980
    ? 'Draft data not tracked before 1980'
    : entryYear != null ? `Entered the league in ${entryYear}` : 'Signed as a free agent'

  return (
    <>
      <div className="text-[10px] font-bold text-ink-dim uppercase tracking-widest mb-3">Drafted</div>
      <EmptyCardBody headline={headline} sub={sub} />
    </>
  )
}

function CareerCardContent({ player }: { player: PlayerProfile }) {
  const draft = player.draft
  const career: Array<{ label: string; value: string }> = []

  // PFR-sourced fields (Pro Bowls, All-Pros, weighted career AV) only exist
  // for drafted players — the upstream draft_picks dataset is keyed on the
  // draft. UDFAs (Romo, Kurt Warner, Wes Welker) won't have these.
  if (draft) {
    if (draft.car_av   != null && draft.car_av   > 0) career.push({ label: 'AV',         value: String(Math.round(draft.car_av)) })
    if (draft.probowls != null && draft.probowls > 0) career.push({ label: 'Pro Bowls', value: String(draft.probowls) })
    if (draft.allpro   != null && draft.allpro   > 0) career.push({ label: 'All-Pro',   value: String(draft.allpro) })
  }

  // Games played: prefer PFR's count, fall back to our own ingest count so
  // UDFAs and any player missing from draft_picks still get a Games tile.
  const games = (draft?.games != null && draft.games > 0) ? draft.games : player.games_played
  if (games > 0) career.push({ label: 'Games', value: String(games) })

  // Major awards (MVP, OPOY, DPOY, OROY, DROY, CPOY) come straight from
  // the player_awards backend table (PlayerProfile.awards). The previous
  // hardcoded frontend lookup is gone — this is just a render of API data.
  const awards = player.awards ?? []

  const hasContent = career.length > 0 || awards.length > 0

  return (
    <>
      <div className="text-[10px] font-bold text-ink-dim uppercase tracking-widest mb-3">Career Achievements</div>
      {hasContent ? (
        <div className="flex flex-col gap-3">
          {career.length > 0 && (
            <div className={`grid gap-3 ${career.length >= 3 ? 'grid-cols-4' : 'grid-cols-2'}`}>
              {career.map(c => <BigStat key={c.label} label={c.label} value={c.value} />)}
            </div>
          )}
          {awards.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pt-1">
              {awards.map(a => <AwardBadge key={`${a.season}-${a.award}`} season={a.season} award={a.award as AwardKey} />)}
            </div>
          )}
        </div>
      ) : (
        <EmptyCardBody headline="—" sub="No accolades on record" />
      )}
    </>
  )
}

function CombineCardContent({ player }: { player: PlayerProfile }) {
  const combine = player.combine
  const hasAny = combineHasAny(combine)
  const entryYear = player.entry_year
  const isPre2000 = entryYear != null && entryYear < 2000

  return (
    <>
      <div className="text-[10px] font-bold text-ink-dim uppercase tracking-widest mb-3">Combine</div>
      {hasAny && combine ? (
        <div className="grid grid-cols-3 gap-3">
          {combine.forty      != null && <BigStat label="40 yd"   value={combine.forty.toFixed(2)} sub="seconds" />}
          {combine.vertical   != null && <BigStat label="Vert"    value={`${combine.vertical}″`} />}
          {combine.bench      != null && <BigStat label="Bench"   value={String(combine.bench)} sub="reps" />}
          {combine.broad_jump != null && <BigStat label="Broad"   value={`${combine.broad_jump}″`} />}
          {combine.cone       != null && <BigStat label="3-cone"  value={combine.cone.toFixed(2)} sub="seconds" />}
          {combine.shuttle    != null && <BigStat label="Shuttle" value={combine.shuttle.toFixed(2)} sub="seconds" />}
        </div>
      ) : (
        <EmptyCardBody
          headline="—"
          sub={isPre2000 ? 'Combine data not tracked before 2000' : 'Did not participate / unavailable'}
        />
      )}
    </>
  )
}

export default function BackgroundCard({ player }: { player: PlayerProfile }) {
  // Always render the same three-card grid skeleton so the PlayerPage layout
  // is identical for every player. Each card shows its filled state when
  // data exists, and a tidy empty state with an explanation otherwise.
  return (
    <div className="mb-6 grid gap-3 grid-cols-1 md:grid-cols-3">
      <div className="relative flex min-h-[180px] flex-col overflow-hidden rounded-xl border border-surface-line bg-surface-card p-5">
        <DraftCardContent player={player} />
      </div>
      <div className="bg-surface-card border border-surface-line rounded-xl p-5 flex flex-col min-h-[180px]">
        <CareerCardContent player={player} />
      </div>
      <div className="bg-surface-card border border-surface-line rounded-xl p-5 flex flex-col min-h-[180px]">
        <CombineCardContent player={player} />
      </div>
    </div>
  )
}
