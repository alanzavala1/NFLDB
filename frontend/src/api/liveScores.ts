import { client, requireData } from './client'

export async function fetchLiveScoreboard(signal?: AbortSignal) {
  const { data } = await client.GET('/api/live/scoreboard', { signal })
  return requireData(data)
}
