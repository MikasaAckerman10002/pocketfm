import type {
  AskResponse,
  NewCaseResponse,
  PublicPersona,
  PublicView,
  SolveResponse,
} from './types'

async function req<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) {
    const detail = await res.json().catch(() => null)
    throw new Error(detail?.detail ?? `Request failed (${res.status})`)
  }
  return res.json()
}

// When built with base="/detective/" and served from the main app, API calls must
// use the /detective/api prefix. In dev mode (Vite proxy) the prefix is rewritten
// back to /api, so both environments work without changing anything else.
const API = '/detective/api'

export const getPersonas = () => req<PublicPersona[]>(`${API}/personas`)

export const getSession = (session_id: string) =>
  req<{ view: PublicView }>(`${API}/session/${session_id}`)

export const newCase = (persona_id: string) =>
  req<NewCaseResponse>(`${API}/case/new`, { persona_id })

export const enterRoom = (session_id: string, room_id: string) =>
  req<{ view: PublicView }>(`${API}/room/enter`, { session_id, room_id })

export const askHotspot = (session_id: string, hotspot_id: string, question: string) =>
  req<AskResponse>(`${API}/hotspot/ask`, { session_id, hotspot_id, question })

export const speak = (
  session_id: string,
  text: string,
  speaker: 'persona' | 'npc',
  npc_name?: string,
) => req<{ audio_url: string | null }>(`${API}/speak`, { session_id, text, speaker, npc_name })

export const solveCase = (
  session_id: string,
  suspect: string,
  motive: string,
  weapon: string,
) => req<SolveResponse>(`${API}/solve`, { session_id, suspect, motive, weapon })
