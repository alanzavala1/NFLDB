

// ── Value labels ─────────────────────────────────────────────────────────────

const VALUE_LABELS: Record<string, string> = {
  '1': '1st Down', '2': '2nd Down', '3': '3rd Down', '4': '4th Down',
  short: 'Short', deep: 'Deep',
  left: 'Left', middle: 'Middle', right: 'Right',
  guard: 'Guard', tackle: 'Tackle', end: 'End',
  leading: 'Leading', tied: 'Tied', trailing: 'Trailing',
  shotgun: 'Shotgun', under_center: 'Under Center',
  red_zone: 'Red Zone', opp_territory: 'Opp Territory', own_territory: 'Own Territory',
  vs_pass: 'vs Pass', vs_run: 'vs Run',
  home: 'Home', away: 'Away',
  dome: 'Dome', outdoors: 'Outdoors', grass: 'Grass', turf: 'Turf',
  no_huddle: 'No-Huddle', huddle: 'Huddle', pressured: 'Under Pressure', clean: 'Clean Pocket',
  competitive: 'Competitive', garbage: 'Garbage Time',
  play_action: 'Play Action', no_pa: 'No Play Action',
  blitz: 'vs Blitz (5+)', standard_rush: 'Standard Rush',
  light_box: 'Light Box (≤6)', neutral_box: 'Neutral Box (7)', stacked_box: 'Stacked Box (8+)',
}

export function splitValueLabel(dim: string, value: string): string {
  if (dim === 'quarter') return value === 'OT' ? 'OT' : `Q${value}`
  return VALUE_LABELS[value] ?? value
}
