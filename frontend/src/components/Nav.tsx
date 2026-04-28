import { useNavigate } from 'react-router-dom'

export default function Nav() {
  const navigate = useNavigate()

  function goHome() {
    navigate('/?season=2025')
  }

  return (
    <nav className="border-b border-gray-800 px-6 py-4 flex items-center gap-4">
      <button onClick={goHome} className="text-white font-bold text-lg tracking-tight hover:text-indigo-400">
        NFL Platform
      </button>
    </nav>
  )
}
