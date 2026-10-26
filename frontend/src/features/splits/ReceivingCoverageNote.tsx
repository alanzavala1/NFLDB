import { Link } from 'react-router-dom'
import type { SplitModel } from './createSplitModel'
import { receivingViewHasGaps } from './receivingModel'

export function ReceivingCoverageNote({ model }: { model: SplitModel }) {
  if (!model.isReceiving) return null
  return <aside aria-label="Receiving coverage" className="mb-4 rounded-xl border border-surface-line bg-surface-card p-4 text-sm text-ink-mid">
    <p className="font-semibold text-ink">Receiving data coverage</p>
    <p className="mt-1 leading-relaxed">Regular season, for seasons with at least 25 recorded pass plays as the intended receiver. Totals cover the supplied games in those qualifying seasons. Select — ⓘ for a missing stat’s explanation.</p>
    {model.isCareer && <p className="mt-1 leading-relaxed">Combined totals keep a stat unavailable if any included season lacks it. Choose a single season to see its available numbers.</p>}
    {model.entities.map((entity, index) => {
      const seasons = model.receivingSeasons[index] ?? []
      const gaps = seasons.filter(item => item.status !== 'prepared' || item.game_coverage?.status === 'partial')
      return <div key={entity.key}>
        {gaps.length > 0 && <details className="mt-3" open>
          <summary className="cursor-pointer font-semibold text-ink">{entity.label} · coverage notes</summary>
          <ul className="mt-2 space-y-2 pl-4 list-disc">
            {gaps.map(item => <li key={item.season}>
              <span className="font-semibold">{item.season}: </span>
              {item.status !== 'prepared' ? 'Receiving splits have not been verified. These numbers are not included as complete totals.' : <>
                {!!item.game_coverage?.missing_game_ids.length && <span>{item.game_coverage.missing_game_ids.length} completed {item.game_coverage.missing_game_ids.length === 1 ? 'game lacks' : 'games lack'} play data. Totals may be incomplete. </span>}
                {!!item.game_coverage?.unconfirmed_game_ids.length && <span>Play data is present for {item.game_coverage.unconfirmed_game_ids.length} {item.game_coverage.unconfirmed_game_ids.length === 1 ? 'game' : 'games'} whose final scores are not confirmed by the stored schedule. </span>}
              </>}
            </li>)}
          </ul>
        </details>}
        <p className="mt-2 text-xs"><Link className="text-indigo-300 underline underline-offset-2" to={`/players/${entity.key}`}>{entity.label} game logs →</Link></p>
      </div>
    })}
  </aside>
}

export function ReceivingViewNote({ model, dimension }: { model: SplitModel; dimension: string }) {
  if (!model.isReceiving || dimension === 'season') return null
  const notes = model.entities.map((entity, index) => {
    const seasons = model.receivingSeasons[index] ?? []
    const issues = seasons.filter(item => receivingViewHasGaps([item], dimension))
    const contextGaps = seasons.filter(item => item.views[dimension]?.status !== 'complete')
    const definitions = [...new Set(seasons.map(item => item.views[dimension]?.definition)
      .filter(text => text && text !== 'Existing situational split definition'))]
    if (!issues.length && !contextGaps.length && !definitions.length) return null
    return <div key={entity.key}>
      {issues.map(item => {
        const view = item.views[dimension]
        const counts = view ? Object.entries(view.excluded).filter(([, value]) => value != null && value !== 0)
          .map(([field, value]) => {
            const labels = { att: ['target', 'targets'], cmp: ['catch', 'catches'], yards: ['yard', 'yards'],
              td: ['TD', 'TDs'], yac: ['YAC', 'YAC'], first_downs: ['first down', 'first downs'] }
            return `${value!.toLocaleString()} ${labels[field as keyof typeof labels][Math.abs(value!) === 1 ? 0 : 1]}`
          }) : []
        return <p key={item.season}><span className="font-semibold text-ink">{entity.label} · {item.season}: </span>
          {!view ? 'Coverage is unverified for this season.' : <>{view.status === 'unavailable' ? 'View unavailable.' : 'Partial play context.'} {counts.length
            ? `${counts.join(', ')} excluded from this view; retained in season totals.`
            : 'No recorded production excluded for this player; unavailable stats remain unknown.'}</>}
        </p>
      })}
      {(contextGaps.length > 0 || definitions.length > 0) && <details className="mt-1">
        <summary className="w-fit cursor-pointer text-indigo-300">{entity.label} · definition and coverage</summary>
        {definitions.map(text => <p className="mt-1" key={text}>{text}</p>)}
        {contextGaps.map(item => item.views[dimension]?.reason ? <p className="mt-1" key={item.season}>{item.season}: {item.views[dimension].reason}{!issues.includes(item) && ' No recorded production excluded for this player.'}</p> : null)}
        <p className="mt-1">Context coverage describes all supplied plays. Excluded counts above apply only to this player. Shown totals include only plays classified into this view.</p>
      </details>}
    </div>
  })
  return notes.some(Boolean) ? <div className="space-y-2 px-4 py-3 text-xs leading-relaxed text-ink-mid" aria-label={`${dimension} receiving coverage`}>{notes}</div> : null
}
