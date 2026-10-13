import { useEffect, useRef } from 'react'
import type { ScheduleWeek } from '../../types'
import Card from '../../components/Card'
import { weekLabel, shortWeekLabel, formatMonthDay } from './presentation'

export function WeekNavigator({
  schedule,
  activeWeek,
  season,
  onWeekChange,
}: {
  schedule: ScheduleWeek[]
  activeWeek: number | null
  season: number
  onWeekChange: (week: number) => void
}) {
  const activePill = useRef<HTMLButtonElement>(null)
  const activeGroup = schedule.find(group => group.week === activeWeek) ?? null
  const activeIndex = schedule.findIndex(group => group.week === activeWeek)
  const previous = activeIndex > 0 ? schedule[activeIndex - 1] : null
  const next = activeIndex >= 0 && activeIndex < schedule.length - 1 ? schedule[activeIndex + 1] : null
  const title = activeGroup ? weekLabel(activeGroup.week, activeGroup.games[0]?.game_type) : `${season} season`
  const firstGame = activeGroup?.games[0]
  const subtitle = activeGroup
    ? firstGame?.game_type === 'SB'
      ? [formatMonthDay(firstGame.gameday), firstGame.stadium].filter(Boolean).join(' - ')
      : formatMonthDay(firstGame?.gameday ?? null)
    : 'Select a week'

  useEffect(() => {
    activePill.current?.scrollIntoView({ inline: 'center', block: 'nearest' })
  }, [activeWeek])

  return (
    <Card>
      <div className="flex items-center gap-3 px-3 pb-2 pt-3">
        <button
          type="button"
          onClick={() => previous && onWeekChange(previous.week)}
          disabled={!previous}
          className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-full bg-surface-raise text-sm font-black text-ink transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-35"
          aria-label="Previous week"
        >
          &lt;
        </button>
        <div className="min-w-0 flex-1 text-center">
          <div className="truncate text-sm font-bold text-ink">{title}</div>
          <div className="truncate text-xs text-ink-dim">{subtitle}</div>
        </div>
        <button
          type="button"
          onClick={() => next && onWeekChange(next.week)}
          disabled={!next}
          className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-full bg-surface-raise text-sm font-black text-ink transition-colors hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-35"
          aria-label="Next week"
        >
          &gt;
        </button>
      </div>
      <div className="flex gap-1.5 overflow-x-auto px-3 pb-3 pt-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        {schedule.map(group => {
          const active = group.week === activeWeek
          return (
            <button
              key={`${group.week}-${group.games[0]?.game_type ?? 'REG'}`}
              ref={active ? activePill : undefined}
              type="button"
              onClick={() => onWeekChange(group.week)}
              className={`shrink-0 rounded-lg px-2.5 py-1.5 text-[11.5px] font-bold transition-colors ${
                active
                  ? 'bg-indigo-500 text-white'
                  : 'bg-surface-raise text-ink-mid hover:bg-indigo-500/35 hover:text-ink'
              }`}
            >
              {shortWeekLabel(group.week, group.games[0]?.game_type)}
            </button>
          )
        })}
      </div>
    </Card>
  )
}
