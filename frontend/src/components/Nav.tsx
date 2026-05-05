import { useNavigate } from 'react-router-dom'
import { CURRENT_NFL_SEASON } from '../api'

export default function Nav() {
  const navigate = useNavigate()
  return (
    <nav className="px-6 py-4 flex items-center">
      <button
        onClick={() => navigate(`/?season=${CURRENT_NFL_SEASON}`)}
        className="font-black text-xl tracking-tight select-none"
      >
        <span className="text-white">NFL</span><span className="text-indigo-500">DB</span>
      </button>
    </nav>
  )
}
