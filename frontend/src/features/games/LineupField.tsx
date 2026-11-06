import { teamPrimaryColor } from '../../utils/teams'

export function LineupField({ awayTeam, homeTeam }: { awayTeam: string; homeTeam: string }) {
  return (
    <svg className="turf" viewBox="0 0 500 860" preserveAspectRatio="none" aria-hidden="true">
      <rect x="0" y="0" width="500" height="860" fill="#122a1d" />
      <rect x="0" y="0" width="500" height="860" fill="url(#vign-lineup)" />
      <defs>
        <radialGradient id="vign-lineup" cx="50%" cy="50%" r="75%"><stop offset="0%" stopColor="#16311f" /><stop offset="100%" stopColor="#0f2318" /></radialGradient>
        <pattern id="ezstripe-lineup" width="14" height="14" patternTransform="rotate(45)" patternUnits="userSpaceOnUse"><rect width="14" height="14" fill="none" /><rect width="7" height="14" fill="rgba(255,255,255,.045)" /></pattern>
      </defs>
      <g fill="rgba(255,255,255,.022)"><rect x="0" y="140" width="500" height="72" /><rect x="0" y="284" width="500" height="72" /><rect x="0" y="428" width="500" height="72" /><rect x="0" y="572" width="500" height="72" /></g>
      <rect x="0" y="0" width="500" height="70" fill={teamPrimaryColor(awayTeam)} opacity=".16" /><rect x="0" y="0" width="500" height="70" fill="url(#ezstripe-lineup)" />
      <rect x="0" y="790" width="500" height="70" fill={teamPrimaryColor(homeTeam)} opacity=".16" /><rect x="0" y="790" width="500" height="70" fill="url(#ezstripe-lineup)" />
      <text x="250" y="45" textAnchor="middle" fontSize="26" fontWeight="900" letterSpacing="14" fill="rgba(255,255,255,.28)">{awayTeam}</text>
      <text x="250" y="835" textAnchor="middle" fontSize="26" fontWeight="900" letterSpacing="14" fill="rgba(255,255,255,.26)">{homeTeam}</text>
      <g stroke="rgba(255,255,255,.30)" strokeWidth="2.5"><line x1="0" y1="70" x2="500" y2="70" /><line x1="0" y1="790" x2="500" y2="790" /></g>
      <g stroke="rgba(255,255,255,.13)" strokeWidth="1.4">{[142, 214, 286, 358, 502, 574, 646, 718].map(y => <line key={y} x1="0" y1={y} x2="500" y2={y} />)}</g>
      <line x1="0" y1="430" x2="500" y2="430" stroke="rgba(255,255,255,.28)" strokeWidth="2.2" />
      <g stroke="rgba(255,255,255,.10)" strokeWidth="1.2">
        {Array.from({ length: 41 }, (_, i) => 78 + i * 17).map(y => <g key={y}><line x1="190" y1={y} x2="210" y2={y} /><line x1="290" y1={y} x2="310" y2={y} /></g>)}
      </g>
      <g fill="rgba(255,255,255,.20)" fontSize="15" fontWeight="800">{[147, 219, 291, 363, 435, 507, 579, 651, 723].map((y, i) => <text key={y} x="14" y={y}>{['1 0', '2 0', '3 0', '4 0', '5 0', '4 0', '3 0', '2 0', '1 0'][i]}</text>)}</g>
      <g fill="rgba(255,255,255,.20)" fontSize="15" fontWeight="800" textAnchor="end">{[147, 219, 291, 363, 435, 507, 579, 651, 723].map((y, i) => <text key={y} x="486" y={y}>{['1 0', '2 0', '3 0', '4 0', '5 0', '4 0', '3 0', '2 0', '1 0'][i]}</text>)}</g>
    </svg>
  )
}
